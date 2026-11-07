"""Consent-safe campaign email preview, confirmation, delivery and event logging."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import secrets
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.campaigns import clock
from app.campaigns.matching import recommend_clients_for_campaign
from app.campaigns.repository import (
    CAMPAIGN_ID_PATTERN,
    CampaignStorageUnavailable,
    RequestScope,
    _storage_tenant_id,
    get_campaign,
    list_active_campaigns,
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
    subject: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, min_length=1, max_length=10_000)
    signoff_name: str | None = Field(default=None, min_length=2, max_length=100)

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
    def strip_content(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("email content must not be blank")
        return value

    @field_validator("signoff_name")
    @classmethod
    def validate_signoff_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if any(character in "<>\r\n" or ord(character) < 32 for character in value):
            raise ValueError("sign-off name contains unsupported characters")
        value = " ".join(value.split())
        if not any(character.isalpha() for character in value):
            raise ValueError("sign-off name must contain a letter")
        return value

    @model_validator(mode="after")
    def require_draft_change(self):
        if self.subject is None and self.body is None and self.signoff_name is None:
            raise ValueError("email content or a sign-off change is required")
        return self


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


def _campaign_id(
    arguments: PrepareCampaignEmailArguments, metadata: dict | None
) -> str | None:
    selected = metadata.get("campaign_id") if isinstance(metadata, dict) else None
    campaign_id = selected or arguments.campaign_id
    if campaign_id is None:
        return None
    if not isinstance(campaign_id, str) or re.fullmatch(CAMPAIGN_ID_PATTERN, campaign_id) is None:
        raise ValueError("A valid campaign ID is required")
    return campaign_id


def _latest_email_preview(scope: RequestScope, session_id: str) -> dict | None:
    with _write_connection() as connection:
        row = connection.execute(
            """
            SELECT campaign_id, subject, body_template, message_body, signoff_name
            FROM campaign_email_send
            WHERE tenant_id = %s AND fa_id = %s AND session_id = %s
              AND status IN ('prepared', 'superseded', 'sent', 'partial', 'failed')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (_storage_tenant_id(scope), scope.fa_id, session_id),
        ).fetchone()
    return dict(row) if row else None


def latest_email_draft_context(
    scope: RequestScope, session_id: str, campaign_id: str
) -> dict | None:
    """Return the latest reviewed draft for one scoped campaign."""
    preview = _latest_email_preview(scope, session_id)
    if preview is None or str(preview["campaign_id"]) != campaign_id:
        return None
    return {
        "subject": str(preview["subject"]),
        "message_body": str(preview["message_body"] or preview["body_template"]),
        "signoff_name": str(preview["signoff_name"]),
    }


def _campaign_required(scope: RequestScope) -> dict:
    campaigns = list_active_campaigns(scope, clock.current_date())
    return {
        "type": "campaign_email_clarification",
        "prepared": False,
        "error_code": "campaign_required",
        "message": (
            "Which campaign should I use for this email? Tell me its name or ID, "
            "and I can prepare a reviewable email preview."
        ),
        "campaign_suggestions": [campaign.name for campaign in campaigns[:5]],
    }


def _with_adviser_signoff(body: str, signoff_name: str) -> tuple[str, str]:
    """Return unsigned content and the server-managed reviewed body."""
    resolved = (
        body.strip()
        .replace("{{advisor_name}}", signoff_name)
        .replace("{advisor_name}", signoff_name)
        .replace("{{advisor_email}}", "")
        .replace("{advisor_email}", "")
    )
    trailing_names = (
        r"(?:your\s+financial\s+adviser|your\s+financial\s+advisor|"
        + re.escape(signoff_name)
        + r")"
    )
    message_body = re.sub(
        r"(?:\n\s*)+(?:(?:(?:kind|warm|best)\s+regards|regards|best|sincerely)"
        r",?\s*(?:\n\s*)+)?"
        + trailing_names
        + r"(?:\s*\n\s*(?:financial\s+adviser|financial\s+advisor))?\s*$",
        "",
        resolved,
        flags=re.IGNORECASE,
    ).rstrip()
    reviewed_body = (
        f"{message_body}\n\nKind regards,\n\n"
        f"{signoff_name}\nFinancial Adviser"
    )
    return message_body, reviewed_body


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
    valid_ids: list[str] = []
    canonical_ids: dict[str, str] = {}
    for contact_id in requested_ids:
        try:
            canonical = str(UUID(contact_id))
        except (ValueError, TypeError, AttributeError):
            continue
        canonical_ids[contact_id] = canonical
        valid_ids.append(canonical)

    rows = connection.execute(
        """
        SELECT contact_id, full_name, email, opt_in_email,
               assigned_to_user_id, created_by_user_id, is_deleted
        FROM contact
        WHERE tenant_id = %s AND contact_id = ANY(%s::uuid[])
        ORDER BY contact_id
        """,
        (_storage_tenant_id(scope), valid_ids),
    ).fetchall()
    by_id = {str(row["contact_id"]): row for row in rows}
    included: list[dict[str, str]] = []
    excluded: list[dict[str, str]] = []
    for contact_id in requested_ids:
        canonical = canonical_ids.get(contact_id)
        row = by_id.get(canonical) if canonical else None
        if row is None:
            excluded.append({"contact_id": contact_id, "reason": "not accessible to this adviser"})
        elif row["is_deleted"] or not (
            str(row["assigned_to_user_id"] or "") == scope.fa_id
            or str(row["created_by_user_id"]) == scope.fa_id
        ):
            excluded.append({"contact_id": contact_id, "reason": "not accessible to this adviser"})
        elif canonical not in eligible_ids:
            excluded.append({
                "contact_id": contact_id,
                "name": row["full_name"],
                "reason": "does not match campaign criteria",
            })
        elif not row["opt_in_email"]:
            excluded.append({
                "contact_id": contact_id,
                "name": row["full_name"],
                "reason": "email consent is not recorded",
            })
        elif not row["email"] or not str(row["email"]).strip():
            excluded.append({
                "contact_id": contact_id,
                "name": row["full_name"],
                "reason": "email address is missing",
            })
        else:
            included.append({
                "contact_id": canonical,
                "name": row["full_name"],
                "email": str(row["email"]),
            })
    return included, excluded


_SYNTHETIC_CLIENT_ID_PATTERN = re.compile(r"^client[-_]?0*(\d+)$", re.IGNORECASE)


def _recipient_display_name(item: dict) -> str:
    """Return an adviser-safe name without exposing raw contact identifiers."""
    name = item.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    contact_id = item.get("contact_id")
    if isinstance(contact_id, str):
        match = _SYNTHETIC_CLIENT_ID_PATTERN.fullmatch(contact_id.strip())
        if match:
            return f"Client {int(match.group(1))}"
    return "Unavailable recipient"


def prepare_campaign_email(
    arguments: PrepareCampaignEmailArguments,
    metadata: dict | None,
) -> dict:
    scope, session_id, _ = _context(metadata)
    previous = _latest_email_preview(scope, session_id)
    campaign_id = _campaign_id(arguments, metadata)
    if campaign_id is None and previous is not None:
        campaign_id = str(previous["campaign_id"])
    if campaign_id is None:
        return _campaign_required(scope)
    campaign = get_campaign(campaign_id, scope)
    require_active(campaign)
    previous_for_campaign = (
        previous
        if previous is not None and str(previous["campaign_id"]) == campaign_id
        else None
    )
    subject = arguments.subject or (
        str(previous_for_campaign["subject"]) if previous_for_campaign else None
    )
    message_body = arguments.body or (
        str(previous_for_campaign["message_body"] or previous_for_campaign["body_template"])
        if previous_for_campaign
        else None
    )
    if subject is None or message_body is None:
        return {
            "type": "campaign_email_clarification",
            "prepared": False,
            "error_code": "email_content_required",
            "message": (
                "Please provide both the email subject and message before I prepare "
                "the first reviewable preview for this campaign."
            ),
            "campaign_suggestions": [],
        }
    signoff_name = arguments.signoff_name or (
        str(previous_for_campaign["signoff_name"])
        if previous_for_campaign and previous_for_campaign["signoff_name"]
        else None
    )
    if signoff_name is None:
        return {
            "type": "campaign_email_clarification",
            "prepared": False,
            "error_code": "signoff_name_required",
            "message": "What name would you like me to use in the email sign-off?",
            "campaign_suggestions": [],
        }
    message_body, reviewed_body = _with_adviser_signoff(message_body, signoff_name)
    if not message_body:
        return {
            "type": "campaign_email_clarification",
            "prepared": False,
            "error_code": "email_message_required",
            "message": "Please provide an email message before I prepare the preview.",
            "campaign_suggestions": [],
        }
    eligible_ids = _eligible_recipient_ids(campaign_id, scope)
    requested_ids = arguments.recipient_ids or sorted(eligible_ids)
    batch_id = str(uuid4())
    code = _confirmation_code()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

    with _write_connection() as connection:
        tenant_id = _storage_tenant_id(scope)
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
            (tenant_id, scope.fa_id, session_id, campaign_id),
        )
        connection.execute(
            """
            INSERT INTO campaign_email_send (
                tenant_id, send_batch_id, campaign_id, fa_id, session_id,
                subject, message_body, signoff_name, body_template,
                recipient_ids, recipient_snapshot,
                confirmation_hash, expires_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
            """,
            (
                tenant_id, batch_id, campaign_id, scope.fa_id, session_id,
                subject, message_body, signoff_name, reviewed_body,
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
        "subject": subject,
        "body": reviewed_body,
        "signoff_name": signoff_name,
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
        tenant_id = _storage_tenant_id(scope)
        batch = connection.execute(
            """
            SELECT * FROM campaign_email_send
            WHERE tenant_id = %s AND fa_id = %s AND session_id = %s
              AND status IN ('prepared', 'sending', 'sent', 'partial', 'failed')
            ORDER BY created_at DESC
            LIMIT 1
            FOR UPDATE
            """,
            (tenant_id, scope.fa_id, session_id),
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
                (tenant_id, batch["send_batch_id"]),
            )
            return {
                "type": "campaign_email_result",
                "sent": False,
                "error_code": "preview_expired",
                "error": "The email preview expired; prepare and review a new preview",
            }

        campaign_id = str(batch["campaign_id"])
        campaign = get_campaign(campaign_id, scope)
        require_active(campaign)
        eligible_ids = _eligible_recipient_ids(campaign_id, scope)
        recipients, excluded = _load_recipients(
            connection, scope,
            [str(contact_id) for contact_id in batch["recipient_ids"]],
            eligible_ids,
        )
        if excluded or len(recipients) != len(batch["recipient_ids"]):
            connection.execute(
                "UPDATE campaign_email_send SET status = 'invalidated' WHERE tenant_id = %s AND send_batch_id = %s",
                (tenant_id, batch["send_batch_id"]),
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
            (tenant_id, batch["send_batch_id"]),
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
                INSERT INTO campaign_member (
                    tenant_id, campaign_id, contact_id, added_by_user_id,
                    emailed_at, email_send_count
                ) VALUES (%s, %s, %s, %s, %s, 1)
                ON CONFLICT (tenant_id, campaign_id, contact_id)
                    WHERE is_deleted = FALSE
                DO UPDATE SET
                    emailed_at = EXCLUDED.emailed_at,
                    email_send_count = campaign_member.email_send_count + 1
                """,
                (
                    tenant_id, batch["campaign_id"], result["contact_id"],
                    scope.fa_id, now,
                ),
            )
        if successful:
            connection.execute(
                """
                UPDATE campaign
                SET email_send_runs = email_send_runs + 1
                WHERE tenant_id = %s AND campaign_id = %s
                  AND created_by_user_id = %s AND is_deleted = FALSE
                """,
                (tenant_id, batch["campaign_id"], scope.fa_id),
            )
        connection.execute(
            """
            UPDATE campaign_email_send
            SET status = %s, provider_results = %s::jsonb, sent_at = %s
            WHERE tenant_id = %s AND send_batch_id = %s
            """,
            (status, json.dumps(results), now, tenant_id, batch["send_batch_id"]),
        )
        batch = {**batch, "status": status, "sent_at": now}
        return _result_payload(batch, results)


def _result_payload(batch: dict, results: list[dict], repeated: bool = False) -> dict:
    successful = [item for item in results if item.get("success")]
    failed = [item for item in results if not item.get("success")]
    return {
        "type": "campaign_email_result",
        "data_source": "synthetic",
        "send_batch_id": str(batch["send_batch_id"]),
        "campaign_id": str(batch["campaign_id"]),
        "status": batch["status"],
        "sent": bool(successful),
        "successful_count": len(successful),
        "failed_count": len(failed),
        "results": results,
        "repeated_confirmation": repeated,
        "campaign_members_updated": len(successful),
    }


def _legacy_render_campaign_email(payload: dict) -> str:
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


def render_campaign_email(payload: dict) -> str:
    """Render email results without exposing internal contact identifiers."""
    if payload.get("type") == "campaign_email_clarification":
        suggestions = payload.get("campaign_suggestions", [])
        choices = "".join(f"\n- {name}" for name in suggestions)
        suggestion_text = f"\n\nAvailable campaigns include:{choices}" if choices else ""
        return "## More information needed\n\n" + payload["message"] + suggestion_text
    if payload.get("error"):
        detail = "".join(
            f"\n- {_recipient_display_name(item)}: {item['reason']}"
            for item in payload.get("excluded_recipients", [])
        )
        return f"## Campaign email not sent\n\n{payload['error']}{detail}"
    if payload.get("type") == "campaign_email_preview":
        recipients = "\n".join(f"- {item['name']}" for item in payload["recipients"])
        excluded = "\n".join(
            f"- {_recipient_display_name(item)} — {item['reason']}"
            for item in payload.get("excluded_recipients", [])
        )
        excluded_section = f"\n\n### Excluded recipients\n\n{excluded}" if excluded else ""
        mode = "simulated" if payload["delivery_mode"] == "mock" else "GWM Core Email API"
        return (
            "## Review campaign email\n\n"
            f"**Campaign:** {payload['campaign_name']}\n\n"
            f"**Delivery:** {mode}\n\n"
            f"**Subject:** {payload['subject']}\n\n"
            "### Message\n\n"
            f"{payload['body']}\n\n"
            f"### Recipients ({len(payload['recipients'])})\n\n{recipients}"
            f"{excluded_section}\n\n"
            "Review the subject, message, and recipients. Ask me for any edits, or "
            "proceed to the final confirmation step by entering:\n\n"
            f"`{payload['confirmation_phrase']}`\n\n"
            f"This confirmation expires at {payload['expires_at']}."
        )
    results = payload.get("results", [])
    lines = "\n".join(
        f"- {item['name']}: {'sent' if item['success'] else 'failed'} — {item['message']}"
        for item in results
    )
    repeated = (
        " This is the saved result; no email was sent again."
        if payload.get("repeated_confirmation") else ""
    )
    return (
        "## Campaign email result\n\n"
        f"**Status:** {payload['status']}\n\n"
        f"**Successful:** {payload['successful_count']}  \n"
        f"**Failed:** {payload['failed_count']}  \n"
        f"**Campaign members updated:** {payload['campaign_members_updated']}\n\n"
        f"{lines}{repeated}"
    )
