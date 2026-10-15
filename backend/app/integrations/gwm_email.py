"""Email transport boundary for the GWM Core Email API and local demos."""

from dataclasses import dataclass
import json
from typing import Protocol
from urllib import error, request

from app.config import Settings


@dataclass(frozen=True)
class DeliveryResult:
    success: bool
    provider_message: str
    provider_status: str | None = None


class EmailTransport(Protocol):
    delivery_mode: str

    def send(self, *, recipient: str, subject: str, message: str) -> DeliveryResult: ...


class MockEmailTransport:
    """Deterministic local transport; it never connects to an email provider."""

    delivery_mode = "mock"

    def send(self, *, recipient: str, subject: str, message: str) -> DeliveryResult:
        return DeliveryResult(True, "Simulated delivery accepted", "mock-accepted")


class GWMEmailTransport:
    """Minimal server-side adapter for GWMCoreEmailAPI SendEmail."""

    delivery_mode = "gwm"

    def __init__(self, settings: Settings) -> None:
        base_url = (settings.gwm_email_base_url or "").rstrip("/")
        sender = (settings.gwm_email_sender or "").strip()
        if not base_url or not sender:
            raise ValueError("GWM email base URL and sender must be configured")
        self.url = base_url + settings.gwm_email_send_path
        self.sender = sender
        self.api_key = (
            settings.gwm_email_api_key.get_secret_value().strip()
            if settings.gwm_email_api_key
            else None
        )
        self.timeout = settings.gwm_email_timeout_seconds

    def send(self, *, recipient: str, subject: str, message: str) -> DeliveryResult:
        payload = json.dumps({
            "senderEmail": self.sender,
            "recipientEmail": recipient,
            "subject": subject,
            "message": message,
            "base64Attachment": None,
            "contentIDs": None,
            "cc": None,
        }).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        outbound = request.Request(self.url, data=payload, headers=headers, method="POST")
        try:
            with request.urlopen(outbound, timeout=self.timeout) as response:
                body = response.read(64_000).decode("utf-8")
                parsed = json.loads(body) if body else {}
                status = str(parsed.get("statusCode", response.status))
                message_text = str(parsed.get("message", "Delivery accepted"))
                return DeliveryResult(200 <= response.status < 300, message_text, status)
        except error.HTTPError as exc:
            return DeliveryResult(False, "Email provider rejected the request", str(exc.code))
        except (error.URLError, TimeoutError, json.JSONDecodeError):
            return DeliveryResult(False, "Email provider outcome is unknown", "unknown")


def build_email_transport(settings: Settings) -> EmailTransport:
    if settings.email_delivery_mode == "mock":
        return MockEmailTransport()
    if settings.email_delivery_mode == "gwm":
        return GWMEmailTransport(settings)
    raise ValueError("EMAIL_DELIVERY_MODE must be 'mock' or 'gwm'")
