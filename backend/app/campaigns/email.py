"""Consent-safe campaign email preview, confirmation, delivery and event logging."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import secrets
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.campaigns.matching import recommend_clients_for_campaign
from app.campaigns.repository import (
    CAMPAIGN_ID_PATTERN,
    CampaignStorageUnavailable,
    RequestScope,
    get_campaign,
    require_active,
)
from app.config import get_settings
from app.integrations.gwm_email import EmailTransport, build_email_transport


CONFIRMATION_PATTERN = re.compile(r"^CONFIRM EMAIL ([A-Z2-9]{6})$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PrepareCampaignEmailArguments(StrictModel):
    campaign_id: str | None = Field(default=None, pattern=CAMPAIGN_ID_PATTERN, max_length=69)
    recipient_ids: list[str] | None = Field(default=None, min_length=1, max_length=100)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=10_000)

    @field_validator("recipient_ids")
    @classmethod
    def validate_recipient_ids(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized = [item.strip() for item in value]
        if any(not item or len(item) > 64 for item in normalized):
            raise ValueError("recipient IDs must be non-empty and at most 64 characters")
        if len(normalized) != len(set(normalized)):
            raise ValueError("recipient IDs must be unique")
        return normalized

    @field_validator("subject", "body")
    @classmethod
    def strip_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("email content must not be blank")
        return value


class ConfirmCampaignEmailArguments(StrictModel):
    pass


@contextmanager
def _write_connection():
    import psycopg
    from psycopg.rows import dict_row

    database_url = get_settings().database_url
    if not database_url:
        raise CampaignStorageUnavailable("Campaign database is not configured")
    try:
        with psycopg.connect(
            database_url, row_factory=dict_row, connect_timeout=5
        ) as connection:
            connection.execute("SET LOCAL statement_timeout = '10s'")
            yield connection
    except psycopg.Error as exc:
        raise CampaignStorageUnavailable(
            "Campaign email storage is temporarily unavailable"
        ) from exc


def _context(metadata: dict | None) -> tuple[RequestScope, str, str | None]:
    pulse_scope = metadata.get("pulse_scope") if isinstance(metadata, dict) else None
    fa_id = pulse_scope.get("fa_id") if isinstance(pulse_scope, dict) else None
    tenant_id = pulse_scope.get("tenant_id") if isinstance(pulse_scope, dict) else None
    session_id = metadata.get("session_id") if isinstance(metadata, dict) else None
    latest_message = metadata.get("latest_user_message") if isinstance(metadata, dict) else None
    if not isinstance(fa_id, str) or not fa_id.strip():
        raise ValueError("Adviser request context is required")
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ValueError("Tenant request context is required")
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("Chat session context is required")
    return RequestScope(fa_id.strip(), tenant_id.strip()), session_id.strip(), latest_message


def _campaign_id(arguments: PrepareCampaignEmailArguments, metadata: dict | None) -> str:
    selected = metadata.get("campaign_id") if isinstance(metadata, dict) else None
    campaign_id = selected or arguments.campaign_id
    if not isinstance(campaign_id, str) or re.fullmatch(CAMPAIGN_ID_PATTERN, campaign_id) is None:
        raise ValueError("A selected campaign or valid campaign ID is required")
    return campaign_id


def _confirmation_hash(batch_id: str, code: str) -> str:
    return hashlib.sha256(f"{batch_id}:{code}".encode("utf-8")).hexdigest()


def _confirmation_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(6))


def _eligible_recipient_ids(campaign_id: str, scope: RequestScope) -> set[str]:
    recommendation = recommend_clients_for_campaign(campaign_id, scope, limit=100)
    return {item["contact_id"] for item in recommendation["clients"]}


def _load_recipients(
    connection: Any,
    scope: RequestScope,
    requested_ids: list[str],
    eligible_ids: set[str],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    rows = connection.execute(
        """
        SELECT contact_id, name, email, opt_in_email
        FROM mock_client
        WHERE tenant_id = %s AND fa_id = %s AND contact_id = ANY(%s::text[])
        ORDER BY contact_id
        """,
        (scope.tenant_id, scope.fa_id, requested_ids),
    ).fetchall()
    by_id = {row["contact_id"]: row for row in rows}
    included: list[dict[str, str]] = []
    excluded: list[dict[str, str]] = []
    for contact_id in requested_ids:
        row = by_id.get(contact_id)
        if row is None:
            excluded.append({"contact_id": contact_id, "reason": "not accessible to this adviser"})
        elif contact_id not in eligible_ids:
            excluded.append({"contact_id": contact_id, "reason": "does not match campaign criteria"})
        elif not row["opt_in_email"]:
            excluded.append({"contact_id": contact_id, "name": row["name"], "reason": "email consent is not recorded"})
        else:
            included.append({
                "contact_id": contact_id,
                "name": row["name"],
                "email": row["email"],
            })
    return included, excluded


def prepare_campaign_email(
    arguments: PrepareCampaignEmailArguments,
    metadata: dict | None,
) -> dict:
    scope, session_id, _ = _context(metadata)
    campaign_id = _campaign_id(arguments, metadata)
    campaign = get_campaign(campaign_id, scope)
    require_active(campaign)
    eligible_ids = _eligible_recipient_ids(campaign_id, scope)
    requested_ids = arguments.recipient_ids or sorted(eligible_ids)
    batch_id = "email-" + uuid4().hex
    code = _confirmation_code()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

    with _write_connection() as connection:
        included, excluded = _load_recipients(
            connection, scope, requested_ids, eligible_ids
        )
        if not included:
            return {
                "type": "campaign_email_preview",
                "data_source": "synthetic",
                "prepared": False,
                "error_code": "no_consenting_recipients",
                "error": "No selected campaign matches have recorded email consent",
                "excluded_recipients": excluded,
            }
        connection.execute(
            """
            UPDATE campaign_email_send
            SET status = 'superseded'
            WHERE tenant_id = %s AND fa_id = %s AND session_id = %s
              AND campaign_id = %s AND status = 'prepared'
            """,
            (scope.tenant_id, scope.fa_id, session_id, campaign_id),
        )
        connection.execute(
            """
            INSERT INTO campaign_email_send (
                tenant_id, send_batch_id, campaign_id, fa_id, session_id,
                subject, body_template, recipient_ids, recipient_snapshot,
                confirmation_hash, expires_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
            """,
            (
                scope.tenant_id, batch_id, campaign_id, scope.fa_id, session_id,
                arguments.subject, arguments.body,
                [item["contact_id"] for item in included], json.dumps(included),
                _confirmation_hash(batch_id, code), expires_at,
            ),
        )
    return {
        "type": "campaign_email_preview",
        "data_source": "synthetic",
        "delivery_mode": get_settings().email_delivery_mode,
        "prepared": True,
        "send_batch_id": batch_id,
        "campaign_id": campaign_id,
        "campaign_name": campaign.name,
        "subject": arguments.subject,
        "body": arguments.body,
        "recipients": included,
        "excluded_recipients": excluded,
        "confirmation_phrase": f"CONFIRM EMAIL {code}",
        "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
        "requires_adviser_confirmation": True,
        "sent": False,
    }


def _personalize(body: str, name: str) -> str:
    return body.replace("{{client_name}}", name).replace("{client_name}", name)


def confirm_campaign_email(
    metadata: dict | None,
    transport: EmailTransport | None = None,
) -> dict:
    scope, session_id, latest_message = _context(metadata)
    match = CONFIRMATION_PATTERN.fullmatch((latest_message or "").strip())
    if match is None:
        return {
            "type": "campaign_email_result",
            "sent": False,
            "error_code": "confirmation_required",
            "error": "Enter the exact confirmation phrase shown in the latest preview",
        }
    code = match.group(1)
    now = datetime.now(timezone.utc)
    with _write_connection() as connection:
        batch = connection.execute(
            """
            SELECT * FROM campaign_email_send
            WHERE tenant_id = %s AND fa_id = %s AND session_id = %s
              AND status IN ('prepared', 'sending', 'sent', 'partial', 'failed')
            ORDER BY created_at DESC
            LIMIT 1
            FOR UPDATE
            """,
            (scope.tenant_id, scope.fa_id, session_id),
        ).fetchone()
        if batch is None or not secrets.compare_digest(
            batch["confirmation_hash"], _confirmation_hash(batch["send_batch_id"], code)
        ):
            return {
                "type": "campaign_email_result",
                "sent": False,
                "error_code": "invalid_confirmation",
                "error": "The confirmation phrase is invalid or no longer current",
            }
        if batch["status"] in {"sent", "partial", "failed"}:
            return _result_payload(batch, list(batch["provider_results"]), repeated=True)
        if batch["status"] == "sending":
            return {
                "type": "campaign_email_result",
                "sent": False,
                "error_code": "delivery_in_progress",
                "error": "This email batch is already being processed",
            }
        if batch["expires_at"] <= now:
            connection.execute(
                "UPDATE campaign_email_send SET status = 'invalidated' WHERE tenant_id = %s AND send_batch_id = %s",
                (scope.tenant_id, batch["send_batch_id"]),
            )
            return {
                "type": "campaign_email_result",
                "sent": False,
                "error_code": "preview_expired",
                "error": "The email preview expired; prepare and review a new preview",
            }

        campaign = get_campaign(batch["campaign_id"], scope)
        require_active(campaign)
        eligible_ids = _eligible_recipient_ids(batch["campaign_id"], scope)
        recipients, excluded = _load_recipients(
            connection, scope, list(batch["recipient_ids"]), eligible_ids
        )
        if excluded or len(recipients) != len(batch["recipient_ids"]):
            connection.execute(
                "UPDATE campaign_email_send SET status = 'invalidated' WHERE tenant_id = %s AND send_batch_id = %s",
                (scope.tenant_id, batch["send_batch_id"]),
            )
            return {
                "type": "campaign_email_result",
                "sent": False,
                "error_code": "recipients_changed",
                "error": "Recipient eligibility or consent changed; review a new preview",
                "excluded_recipients": excluded,
            }
        connection.execute(
            "UPDATE campaign_email_send SET status = 'sending' WHERE tenant_id = %s AND send_batch_id = %s",
            (scope.tenant_id, batch["send_batch_id"]),
        )
        sender = transport or build_email_transport(get_settings())
        results = []
        for recipient in recipients:
            outcome = sender.send(
                recipient=recipient["email"],
                subject=batch["subject"],
                message=_personalize(batch["body_template"], recipient["name"]),
            )
            results.append({
                "contact_id": recipient["contact_id"],
                "name": recipient["name"],
                "success": outcome.success,
                "provider_status": outcome.provider_status,
                "message": outcome.provider_message,
            })
        successful = [result for result in results if result["success"]]
        status: Literal["sent", "partial", "failed"] = (
            "sent" if len(successful) == len(results)
            else "partial" if successful
            else "failed"
        )
        for result in successful:
            connection.execute(
                """
                INSERT INTO mock_campaign_contact_event (
                    tenant_id, contact_event_id, campaign_id, fa_id, contact_id,
                    contacted_at, engagement_status, send_batch_id, channel, delivery_mode
                ) VALUES (%s, %s, %s, %s, %s, %s, 0, %s, 'email', %s)
                ON CONFLICT (tenant_id, send_batch_id, contact_id) DO NOTHING
                """,
                (
                    scope.tenant_id, "email-event-" + uuid4().hex,
                    batch["campaign_id"], scope.fa_id, result["contact_id"], now,
                    batch["send_batch_id"], sender.delivery_mode,
                ),
            )
        connection.execute(
            """
            UPDATE campaign_email_send
            SET status = %s, provider_results = %s::jsonb, sent_at = %s
            WHERE tenant_id = %s AND send_batch_id = %s
            """,
            (status, json.dumps(results), now, scope.tenant_id, batch["send_batch_id"]),
        )
        batch = {**batch, "status": status, "sent_at": now}
        return _result_payload(batch, results)


def _result_payload(batch: dict, results: list[dict], repeated: bool = False) -> dict:
    successful = [item for item in results if item.get("success")]
    failed = [item for item in results if not item.get("success")]
    return {
        "type": "campaign_email_result",
        "data_source": "synthetic",
        "send_batch_id": batch["send_batch_id"],
        "campaign_id": batch["campaign_id"],
        "status": batch["status"],
        "sent": bool(successful),
        "successful_count": len(successful),
        "failed_count": len(failed),
        "results": results,
        "repeated_confirmation": repeated,
        "contact_events_recorded": len(successful),
    }


def render_campaign_email(payload: dict) -> str:
    if payload.get("error"):
        excluded = payload.get("excluded_recipients", [])
        detail = "".join(
            f"\n- `{item['contact_id']}`: {item['reason']}" for item in excluded
        )
        return f"## Campaign email not sent\n\n{payload['error']}{detail}"
    if payload.get("type") == "campaign_email_preview":
        recipients = "\n".join(
            f"- {item['name']} (`{item['contact_id']}`) — {item['email']}"
            for item in payload["recipients"]
        )
        excluded = "\n".join(
            f"- `{item['contact_id']}` — {item['reason']}"
            for item in payload.get("excluded_recipients", [])
        )
        excluded_section = f"\n\n### Excluded recipients\n\n{excluded}" if excluded else ""
        mode = "simulated" if payload["delivery_mode"] == "mock" else "GWM Core Email API"
        return (
            "## Review campaign email\n\n"
            f"**Campaign:** {payload['campaign_name']} (`{payload['campaign_id']}`)\n\n"
            f"**Delivery:** {mode}\n\n"
            f"**Subject:** {payload['subject']}\n\n"
            "### Message\n\n"
            f"{payload['body']}\n\n"
            f"### Recipients ({len(payload['recipients'])})\n\n{recipients}"
            f"{excluded_section}\n\n"
            "Review or ask me to revise the subject, message, or recipients. "
            "To approve this exact preview, enter:\n\n"
            f"`{payload['confirmation_phrase']}`\n\n"
            f"This confirmation expires at {payload['expires_at']}."
        )
    results = payload.get("results", [])
    lines = "\n".join(
        f"- {item['name']} (`{item['contact_id']}`): "
        f"{'sent' if item['success'] else 'failed'} — {item['message']}"
        for item in results
    )
    repeated = " This is the saved result; no email was sent again." if payload.get("repeated_confirmation") else ""
    return (
        "## Campaign email result\n\n"
        f"**Status:** {payload['status']}\n\n"
        f"**Successful:** {payload['successful_count']}  \n"
        f"**Failed:** {payload['failed_count']}  \n"
        f"**Contact events recorded:** {payload['contact_events_recorded']}\n\n"
        f"{lines}{repeated}"
    )
