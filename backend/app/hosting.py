"""Same-origin demo hosting. Shared access gate is not adviser authentication."""
import asyncio
import base64
import binascii
import secrets
from pathlib import Path

import psycopg
from starlette.exceptions import HTTPException
from fastmcp import Client
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.staticfiles import StaticFiles

from app.config import get_settings


class DemoAccessMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        settings = get_settings()
        if settings.demo_auth_enabled and not (
            request.url.path in {"/live", "/ready"} and request.method in {"GET", "HEAD"}
        ):
            user, password = "", ""
            try:
                scheme, token = request.headers.get("authorization", "").split(" ", 1)
                if scheme.lower() == "basic":
                    user, password = base64.b64decode(token, validate=True).decode("utf-8").split(":", 1)
            except (ValueError, UnicodeError, binascii.Error):
                pass
            valid_user = secrets.compare_digest(user.encode(), settings.demo_auth_username.encode())
            valid_password = secrets.compare_digest(password.encode(), settings.demo_auth_password.get_secret_value().encode())
            if not (valid_user and valid_password):
                return JSONResponse({"detail": "Demo credentials required"}, 401,
                                    headers={"WWW-Authenticate": 'Basic realm="PULSE demo", charset="UTF-8"', "Cache-Control": "no-store"})
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                # Basic credentials are attached automatically by browsers. Require
                # same-origin writes; command-line clients must supply Origin too.
                origin = request.headers.get("origin")
                expected = f"{request.url.scheme}://{request.url.netloc}"
                if origin != expected or request.headers.get("sec-fetch-site") == "cross-site":
                    return JSONResponse({"detail": "Same-origin request required"}, 403)
        response = await call_next(request)
        if settings.demo_auth_enabled:
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
        return response


async def check_dependencies(settings):
    async with await psycopg.AsyncConnection.connect(
        settings.database_url, connect_timeout=2
    ) as connection:
        await connection.execute("SET LOCAL statement_timeout = '1s'")
        await connection.execute("SELECT 1")
    async with Client(settings.mcp_server_url, timeout=1.5) as client:
        # This FastMCP release does not expose the optional ping method.
        # Tool discovery exercises the protocol used by the chat registry.
        await client.list_tools()


class FrontendFiles(StaticFiles):
    async def get_response(self, path, scope):
        # Never turn a mistyped API path or missing asset into an HTML success.
        if path.split("/", 1)[0] in {"api", "chat", "contacts", "campaign", "campaigns", "campaign-drafts", "health", "live", "ready", "mcp", "docs", "redoc", "openapi.json"}:
            raise HTTPException(404, "Not found")
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or "." in path or path.startswith("assets/"):
                raise
            return await super().get_response("index.html", scope)


def install_hosting(app):
    settings = get_settings()
    app.add_middleware(DemoAccessMiddleware)

    @app.get("/live", include_in_schema=False)
    async def live():
        return {"status": "ok"}

    @app.get("/ready", include_in_schema=False)
    async def ready():
        try:
            await asyncio.wait_for(check_dependencies(get_settings()), timeout=4)
        except Exception:
            return JSONResponse({"status": "unavailable"}, 503)
        return {"status": "ok"}

    if settings.frontend_dist:
        root = Path(settings.frontend_dist)
        if not (root / "index.html").is_file():
            raise RuntimeError("Frontend build is missing")
        app.mount("/", FrontendFiles(directory=root, html=True), name="frontend")
