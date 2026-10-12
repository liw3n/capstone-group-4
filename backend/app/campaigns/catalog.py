"""PostgreSQL-backed campaign catalogue used by the CRM UI.

This is an explicitly synthetic prototype adapter.  It does not claim parity
with the company GCRM campaign tables, whose column definitions were not
provided.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator, Literal

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app import config
from app.campaigns.repository import (
    DEMO_DATE,
    DEMO_TENANT,
    CampaignStorageUnavailable,
    RequestScope,
)

CampaignRole = Literal["advisor", "marketing"]

SELECT_COLUMNS = """
    c.campaign_id, c.name, c.status, c.start_date, c.end_date,
    c.age_groups, c.genders, c.cash_bands,
    c.age_min, c.age_max, c.cash_min, c.cash_max,
    c.description, c.client_message, c.banner_data_url,
    c.origin, c.audience_source, c.channel, c.team_ids, c.advisor_ids,
    c.created_by_advisor_id, c.created_by, c.created_at,
    c.include_ids, c.exclude_ids, c.lead_ids,
    c.lead_stats_uploaded, c.lead_stats_added, c.lead_stats_removed,
    c.actions, c.email_log, c.lead_contacts
"""


@contextmanager
def _connection() -> Iterator[Any]:
    database_url = config.get_settings().database_url
    if not database_url:
        raise CampaignStorageUnavailable("Campaign database is not configured")
    try:
        with psycopg.connect(
            database_url, row_factory=dict_row, connect_timeout=5
        ) as connection:
            connection.execute("SET LOCAL statement_timeout = '5s'")
            yield connection
    except psycopg.Error as exc:
        raise CampaignStorageUnavailable(
            "Campaign database is temporarily unavailable"
        ) from exc


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _number(value: Any) -> float | int | None:
    if value is None:
        return None
    number = float(value)
    return int(number) if number.is_integer() else number


def _record(row: dict[str, Any]) -> dict[str, Any]:
    age_range = {"min": row["age_min"], "max": row["age_max"]}
    cash_range = {"min": _number(row["cash_min"]), "max": _number(row["cash_max"])}
    return {
        "id": row["campaign_id"],
        "name": row["name"],
        "status": row["status"],
        "startDate": row["start_date"].isoformat(),
        "endDate": row["end_date"].isoformat(),
        "description": row["description"],
        "clientMessage": row["client_message"],
        "bannerDataUrl": row["banner_data_url"],
        "origin": row["origin"],
        "audienceSource": row["audience_source"],
        "channel": row["channel"],
        "teamIds": list(row["team_ids"]),
        "advisorIds": list(row["advisor_ids"]),
        "createdByAdvisorId": row["created_by_advisor_id"],
        "criteria": {
            "ageGroups": list(row["age_groups"]),
            "genders": list(row["genders"]),
            "cashBands": list(row["cash_bands"]),
            "ageRange": age_range if any(value is not None for value in age_range.values()) else None,
            "cashRange": cash_range if any(value is not None for value in cash_range.values()) else None,
        },
        "includeIds": list(row["include_ids"]),
        "excludeIds": list(row["exclude_ids"]),
        "leadIds": list(row["lead_ids"]),
        "leadStats": {
            "uploaded": row["lead_stats_uploaded"],
            "added": row["lead_stats_added"],
            "removed": row["lead_stats_removed"],
        },
        "createdBy": row["created_by"],
        "createdAt": _timestamp(row["created_at"]),
        "actions": dict(row["actions"]),
        "emailLog": list(row["email_log"]),
        "leadContacts": list(row["lead_contacts"]),
    }


def list_campaigns(role: CampaignRole, scope: RequestScope | None) -> list[dict[str, Any]]:
    with _connection() as connection:
        if role == "marketing":
            rows = connection.execute(
                f"""SELECT {SELECT_COLUMNS}
                    FROM mock_campaign AS c
                    WHERE c.tenant_id = %s AND c.origin = 'marketing'
                    ORDER BY c.created_at DESC, c.campaign_id""",
                (DEMO_TENANT,),
            ).fetchall()
        else:
            if scope is None:
                raise ValueError("Adviser request context is required")
            rows = connection.execute(
                f"""SELECT {SELECT_COLUMNS}
                    FROM mock_campaign AS c
                    WHERE c.tenant_id = %s
                      AND (c.created_by_advisor_id = %s OR EXISTS (
                          SELECT 1 FROM mock_campaign_advisor AS a
                          WHERE a.tenant_id = c.tenant_id
                            AND a.campaign_id = c.campaign_id AND a.fa_id = %s
                      ))
                    ORDER BY c.created_at DESC, c.campaign_id""",
                (scope.tenant_id, scope.fa_id, scope.fa_id),
            ).fetchall()
    return [_record(row) for row in rows]


def _get_row(connection: Any, role: CampaignRole, scope: RequestScope | None,
             campaign_id: str) -> dict[str, Any] | None:
    if role == "marketing":
        return connection.execute(
            f"""SELECT {SELECT_COLUMNS} FROM mock_campaign AS c
                WHERE c.tenant_id = %s AND c.campaign_id = %s
                  AND c.origin = 'marketing'""",
            (DEMO_TENANT, campaign_id),
        ).fetchone()
    if scope is None:
        raise ValueError("Adviser request context is required")
    return connection.execute(
        f"""SELECT {SELECT_COLUMNS} FROM mock_campaign AS c
            WHERE c.tenant_id = %s AND c.campaign_id = %s
              AND (c.created_by_advisor_id = %s OR EXISTS (
                  SELECT 1 FROM mock_campaign_advisor AS a
                  WHERE a.tenant_id = c.tenant_id
                    AND a.campaign_id = c.campaign_id AND a.fa_id = %s
              ))""",
        (scope.tenant_id, campaign_id, scope.fa_id, scope.fa_id),
    ).fetchone()


def get_campaign_record(role: CampaignRole, scope: RequestScope | None,
                        campaign_id: str) -> dict[str, Any] | None:
    with _connection() as connection:
        row = _get_row(connection, role, scope, campaign_id)
    return _record(row) if row else None


def create_campaign(role: CampaignRole, scope: RequestScope | None,
                    payload: dict[str, Any]) -> dict[str, Any]:
    tenant_id = scope.tenant_id if scope is not None else DEMO_TENANT
    campaign_id = payload["id"]
    origin = "advisor" if role == "advisor" else "marketing"
    creator_id = scope.fa_id if role == "advisor" and scope is not None else None
    criteria = payload["criteria"]
    age_range = criteria.get("ageRange") or {}
    cash_range = criteria.get("cashRange") or {}
    start_date = payload.get("startDate") or DEMO_DATE
    end_date = payload.get("endDate") or (DEMO_DATE + timedelta(days=365))

    with _connection() as connection:
        existing = connection.execute(
            "SELECT 1 FROM mock_campaign WHERE tenant_id = %s AND campaign_id = %s",
            (tenant_id, campaign_id),
        ).fetchone()
        if existing:
            raise ValueError("Campaign ID already exists")
        connection.execute(
            """
            INSERT INTO mock_campaign (
                tenant_id, campaign_id, name, status, start_date, end_date,
                age_groups, genders, cash_bands, age_min, age_max, cash_min, cash_max,
                description, client_message, banner_data_url, origin, audience_source,
                channel, team_ids, advisor_ids, created_by_advisor_id, created_by,
                include_ids, exclude_ids, lead_ids,
                lead_stats_uploaded, lead_stats_added, lead_stats_removed,
                actions, email_log, lead_contacts, created_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s
            )
            """,
            (
                tenant_id, campaign_id, payload["name"], payload.get("status", "active"),
                start_date, end_date, criteria["ageGroups"], criteria["genders"],
                criteria["cashBands"], age_range.get("min"), age_range.get("max"),
                cash_range.get("min"), cash_range.get("max"), payload["description"],
                payload["clientMessage"], payload.get("bannerDataUrl"), origin,
                payload["audienceSource"], payload.get("channel") if role == "marketing" else None,
                payload.get("teamIds", []) if role == "marketing" else [],
                payload.get("advisorIds", []) if role == "marketing" else [], creator_id,
                payload["createdBy"], payload.get("includeIds", []),
                payload.get("excludeIds", []), payload.get("leadIds", []),
                payload["leadStats"]["uploaded"], payload["leadStats"]["added"],
                payload["leadStats"]["removed"], Jsonb(payload.get("actions", {})),
                Jsonb(payload.get("emailLog", [])), Jsonb(payload.get("leadContacts", [])),
                payload.get("createdAt") or datetime.now(timezone.utc),
            ),
        )

        if role == "advisor" and scope is not None:
            assigned_advisers = [scope.fa_id]
        else:
            assigned_advisers = payload.get("advisorIds", [])
            if not assigned_advisers:
                assigned_advisers = [row["fa_id"] for row in connection.execute(
                    """SELECT DISTINCT fa_id FROM mock_client
                       WHERE tenant_id = %s ORDER BY fa_id""", (tenant_id,)
                ).fetchall()]
        for fa_id in assigned_advisers:
            connection.execute(
                """INSERT INTO mock_campaign_advisor (tenant_id, campaign_id, fa_id)
                   VALUES (%s, %s, %s) ON CONFLICT DO NOTHING""",
                (tenant_id, campaign_id, fa_id),
            )
        row = _get_row(connection, role, scope, campaign_id)
    return _record(row)


def update_campaign_state(role: CampaignRole, scope: RequestScope | None,
                          campaign_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    with _connection() as connection:
        current = _get_row(connection, role, scope, campaign_id)
        if current is None:
            return None
        if role == "marketing" and payload["emailLog"] != list(current["email_log"]):
            raise ValueError("Marketing cannot record adviser email sends")
        recipient_ids = {
            contact_id
            for entry in payload["emailLog"]
            for contact_id in entry.get("recipientIds", [])
        }
        if recipient_ids:
            if scope is None:
                raise ValueError("Adviser context is required for email recipients")
            consented_ids = {
                row["contact_id"] for row in connection.execute(
                    """SELECT contact_id FROM mock_client
                       WHERE tenant_id = %s AND fa_id = %s
                         AND opt_in_email = TRUE AND contact_id = ANY(%s)""",
                    (scope.tenant_id, scope.fa_id, list(recipient_ids)),
                ).fetchall()
            }
            if consented_ids != recipient_ids:
                raise ValueError(
                    "Every email recipient must be an owned contact with email consent"
                )
        connection.execute(
            """
            UPDATE mock_campaign
            SET include_ids = %s, exclude_ids = %s, lead_ids = %s,
                lead_stats_uploaded = %s, lead_stats_added = %s,
                lead_stats_removed = %s, actions = %s,
                email_log = %s, lead_contacts = %s
            WHERE tenant_id = %s AND campaign_id = %s
            """,
            (
                payload["includeIds"], payload["excludeIds"], payload["leadIds"],
                payload["leadStats"]["uploaded"], payload["leadStats"]["added"],
                payload["leadStats"]["removed"], Jsonb(payload["actions"]),
                Jsonb(payload["emailLog"]), Jsonb(payload["leadContacts"]),
                scope.tenant_id if scope is not None else DEMO_TENANT, campaign_id,
            ),
        )
        row = _get_row(connection, role, scope, campaign_id)
    return _record(row)
