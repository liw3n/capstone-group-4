import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app import hosting

PASSWORD = "synthetic-password-for-tests"


def make_app(monkeypatch, tmp_path, *, authenticated=True):
    (tmp_path / "index.html").write_text("<html>PULSE</html>")
    (tmp_path / "app.js").write_text("// synthetic asset")
    settings = Settings(_env_file=None, demo_auth_enabled=authenticated,
                        demo_auth_username="tester", demo_auth_password=PASSWORD,
                        frontend_dist=str(tmp_path))
    monkeypatch.setattr(hosting, "get_settings", lambda: settings)
    app = FastAPI()

    @app.post("/api/example")
    def mutation():
        return {"saved": True}

    hosting.install_hosting(app)
    return TestClient(app), settings


def test_auth_covers_assets_and_api(monkeypatch, tmp_path):
    client, _ = make_app(monkeypatch, tmp_path)
    for path in ("/", "/app.js", "/docs", "/openapi.json", "/api/missing"):
        response = client.get(path)
        assert response.status_code == 401
        assert response.headers["www-authenticate"].startswith("Basic")
        assert client.get(path, auth=("tester", "wrong")).status_code == 401
    for authorization in ("Basic !!!", "Basic /w==", "Bearer xyz"):
        assert client.get("/", headers={"Authorization": authorization}).status_code == 401
    assert client.get("/", auth=("tester", PASSWORD)).status_code == 200
    assert client.get("/live").json() == {"status": "ok"}


def test_writes_require_same_origin(monkeypatch, tmp_path):
    client, _ = make_app(monkeypatch, tmp_path)
    auth = ("tester", PASSWORD)
    for origin in (None, "https://attacker.invalid", "null"):
        headers = {"Origin": origin} if origin else {}
        assert client.post("/api/example", auth=auth, headers=headers).status_code == 403
    result = client.post("/api/example", auth=auth, headers={"Origin": "http://testserver"})
    assert result.json() == {"saved": True}
    assert result.headers["cache-control"] == "no-store"


def test_spa_fallback_preserves_api_and_asset_errors(monkeypatch, tmp_path):
    client, _ = make_app(monkeypatch, tmp_path, authenticated=False)
    assert "PULSE" in client.get("/workspace/nested").text
    for path in ("/api/missing", "/chat/missing", "/campaign-drafts/missing", "/assets/missing.js", "/missing.js"):
        assert client.get(path).status_code == 404
    assert client.post("/api/example").status_code == 200


def test_readiness_failure_is_redacted(monkeypatch, tmp_path):
    client, _ = make_app(monkeypatch, tmp_path)

    async def unavailable(settings):
        raise RuntimeError("secret database address")

    monkeypatch.setattr(hosting, "check_dependencies", unavailable)
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}

    async def available(settings):
        return None

    monkeypatch.setattr(hosting, "check_dependencies", available)
    assert client.get("/ready").status_code == 200


def test_hosted_settings_fail_closed():
    base = dict(_env_file=None, pulse_hosted_demo=True, demo_auth_enabled=True,
                demo_auth_username="tester", demo_auth_password=PASSWORD,
                database_url="postgresql://synthetic", groq_api_key="synthetic",
                frontend_dist="/synthetic", PULSE_CAMPAIGN_PREVIEW_SECRET="a" * 32,
                PULSE_CAMPAIGN_RETRIEVAL_SECRET="b" * 32)
    assert Settings(**base).email_delivery_mode == "mock"
    for field, value in (("demo_auth_enabled", False), ("email_delivery_mode", "gwm"),
                         ("demo_auth_password", "short"), ("PULSE_CAMPAIGN_PREVIEW_SECRET", ""),
                         ("mcp_server_url", "https://outside.invalid/mcp")):
        with pytest.raises(ValidationError):
            Settings(**{**base, field: value})
