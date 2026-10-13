from fastapi.testclient import TestClient

from app import main
from app.campaigns.repository import RequestScope


client = TestClient(main.app)


def campaign_payload(**updates):
    payload = {
        "id": "campaign-api-test",
        "name": "Synthetic campaign",
        "status": "active",
        "startDate": "2026-10-12",
        "endDate": "2026-12-31",
        "description": "Synthetic internal brief",
        "clientMessage": "Synthetic educational outreach message.",
        "origin": "advisor",
        "audienceSource": "contacts",
        "teamIds": [],
        "advisorIds": [],
        "criteria": {"ageGroups": [], "genders": [], "cashBands": []},
        "includeIds": [],
        "excludeIds": [],
        "leadIds": [],
        "leadStats": {"uploaded": 0, "added": 0, "removed": 0},
        "createdBy": "Demo Adviser",
        "createdAt": "2026-10-12T00:00:00Z",
        "actions": {},
        "emailLog": [],
        "leadContacts": [],
    }
    payload.update(updates)
    return payload


def test_list_alias_passes_adviser_scope_to_storage(monkeypatch):
    calls = []
    monkeypatch.setattr(
        main,
        "list_campaign_records",
        lambda role, scope: calls.append((role, scope)) or [campaign_payload()],
    )

    response = client.get(
        "/api/campaigns", params={"role": "advisor", "fa_id": "adv-demo"}
    )

    assert response.status_code == 200
    assert response.json()[0]["id"] == "campaign-api-test"
    assert calls == [("advisor", RequestScope("adv-demo"))]


def test_adviser_list_requires_scope():
    response = client.get("/campaigns", params={"role": "advisor"})
    assert response.status_code == 400
    assert response.json() == {"detail": "fa_id is required for adviser campaigns"}


def test_create_rejects_role_origin_mismatch(monkeypatch):
    monkeypatch.setattr(
        main,
        "create_campaign_record",
        lambda *_args: (_ for _ in ()).throw(AssertionError("storage must not be called")),
    )
    response = client.post(
        "/api/campaigns?role=marketing", json=campaign_payload(origin="advisor")
    )
    assert response.status_code == 400


def test_create_validates_date_order_before_storage(monkeypatch):
    monkeypatch.setattr(
        main,
        "create_campaign_record",
        lambda *_args: (_ for _ in ()).throw(AssertionError("storage must not be called")),
    )
    response = client.post(
        "/campaigns?role=advisor&fa_id=adv-demo",
        json=campaign_payload(startDate="2026-12-31", endDate="2026-10-12"),
    )
    assert response.status_code == 422


def test_state_update_is_scoped_and_returns_not_found(monkeypatch):
    calls = []

    def missing(role, scope, campaign_id, payload):
        calls.append((role, scope, campaign_id, payload))
        return None

    monkeypatch.setattr(main, "update_campaign_state", missing)
    state = {
        "includeIds": [],
        "excludeIds": [],
        "leadIds": [],
        "leadStats": {"uploaded": 0, "added": 0, "removed": 0},
        "actions": {},
        "emailLog": [],
        "leadContacts": [],
    }
    response = client.patch(
        "/api/campaigns/missing/state?role=advisor&fa_id=adv-demo", json=state
    )
    assert response.status_code == 404
    assert calls[0][:3] == ("advisor", RequestScope("adv-demo"), "missing")


def test_campaign_path_identifier_is_validated_before_storage(monkeypatch):
    monkeypatch.setattr(
        main,
        "get_campaign_record",
        lambda *_args: (_ for _ in ()).throw(AssertionError("storage must not be called")),
    )
    response = client.get(
        "/api/campaigns/bad%20id", params={"role": "advisor", "fa_id": "adv-demo"}
    )
    assert response.status_code == 422


def test_state_update_maps_consent_rejection_to_conflict(monkeypatch):
    def reject(*_args):
        raise ValueError("Every email recipient must have email consent")

    monkeypatch.setattr(main, "update_campaign_state", reject)
    state = {
        "includeIds": [], "excludeIds": [], "leadIds": [],
        "leadStats": {"uploaded": 0, "added": 0, "removed": 0},
        "actions": {}, "emailLog": [], "leadContacts": [],
    }
    response = client.patch(
        "/api/campaigns/camp-1/state?role=advisor&fa_id=adv-demo", json=state
    )
    assert response.status_code == 409


def test_engagement_status_update_passes_client_campaign_status_and_adviser(monkeypatch):
    calls = []

    def update(fa_id, campaign_id, contact_id, status):
        calls.append((fa_id, campaign_id, contact_id, status))
        return {
            "campaign_id": campaign_id,
            "contact_id": contact_id,
            "fa_id": fa_id,
            "status": status,
        }

    monkeypatch.setattr(main, "update_engagement_status", update)
    response = client.post(
        "/api/campaign/update-engagement-status?fa_id=adv-demo",
        json={"campaign_id": "camp-1", "contact_id": "client-001", "status": 2},
    )

    assert response.status_code == 201
    assert response.json() == {
        "campaign_id": "camp-1",
        "contact_id": "client-001",
        "fa_id": "adv-demo",
        "status": 2,
    }
    assert calls == [("adv-demo", "camp-1", "client-001", 2)]


def test_engagement_status_update_requires_adviser_id(monkeypatch):
    monkeypatch.setattr(
        main,
        "update_engagement_status",
        lambda *_args: (_ for _ in ()).throw(AssertionError("storage must not be called")),
    )
    response = client.post(
        "/campaigns/update-engagement-status",
        json={"campaign_id": "camp-1", "contact_id": "client-001", "status": 1},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "fa_id is required"}


def test_engagement_status_get_returns_status(monkeypatch):
    calls = []

    def get_status(fa_id, campaign_id, contact_id):
        calls.append((fa_id, campaign_id, contact_id))
        return {
            "campaign_id": campaign_id,
            "contact_id": contact_id,
            "fa_id": fa_id,
            "status": 1,
        }

    monkeypatch.setattr(main, "get_engagement_status", get_status)
    response = client.get(
        "/api/campaigns/engagement-status",
        params={
            "campaign_id": "camp-1",
            "fa_id": "adv-demo",
            "contact_id": "client-001",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == 1
    assert calls == [("adv-demo", "camp-1", "client-001")]


def test_engagement_status_get_returns_null_when_unset(monkeypatch):
    monkeypatch.setattr(main, "get_engagement_status", lambda *_args: None)
    response = client.get(
        "/campaigns/engagement-status",
        params={
            "campaign_id": "camp-1",
            "fa_id": "adv-demo",
            "contact_id": "client-001",
        },
    )

    assert response.status_code == 200
    assert response.json() is None
