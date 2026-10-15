"""Server-side adapters for external services."""

from .gwm_email import DeliveryResult, EmailTransport, build_email_transport

__all__ = ["DeliveryResult", "EmailTransport", "build_email_transport"]
