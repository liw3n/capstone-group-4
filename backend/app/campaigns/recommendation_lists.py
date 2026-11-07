"""Short-lived, adviser-scoped snapshots for full recommendation downloads."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.config import get_settings
from app.campaigns import repository
from app.campaigns.repository import CampaignStorageUnavailable, RequestScope

LIFETIME = timedelta(hours=24)


class RecommendationListNotFound(ValueError):
    pass


class RecommendationListExpired(ValueError):
    pass


@contextmanager
def connection():
    url = get_settings().database_url
    if not url:
        raise CampaignStorageUnavailable("Recommendation list storage is not configured")
    try:
        with psycopg.connect(url, row_factory=dict_row, connect_timeout=5) as active:
            active.execute("SET LOCAL statement_timeout = '5s'")
            yield active
    except psycopg.errors.UndefinedTable as exc:
        raise CampaignStorageUnavailable(
            "Recommendation list storage needs the create_campaign_recommendation_lists.sql migration"
        ) from exc
    except psycopg.Error as exc:
        raise CampaignStorageUnavailable("Recommendation list storage is temporarily unavailable") from exc


def save_list(scope: RequestScope, payload: dict, session_id: str | None = None) -> dict:
    now = datetime.now(timezone.utc)
    list_id = uuid4()
    expires = now + LIFETIME
    tenant = repository._storage_tenant_id(scope)
    with connection() as active:
        active.execute(
            "DELETE FROM campaign_recommendation_lists WHERE tenant_id = %s AND fa_id = %s AND expires_at <= %s",
            (tenant, scope.fa_id, now),
        )
        active.execute(
            """INSERT INTO campaign_recommendation_lists
               (list_id, tenant_id, fa_id, session_id, campaign_id, expires_at, payload)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (list_id, tenant, scope.fa_id, session_id, payload["campaign_id"], expires, Jsonb(payload)),
        )
    return {"list_id": str(list_id), "expires_at": expires.isoformat()}


def load_list(scope: RequestScope, list_id: UUID) -> dict:
    with connection() as active:
        row = active.execute(
            """SELECT payload, expires_at FROM campaign_recommendation_lists
               WHERE list_id = %s AND tenant_id = %s AND fa_id = %s""",
            (list_id, repository._storage_tenant_id(scope), scope.fa_id),
        ).fetchone()
    if row is None:
        raise RecommendationListNotFound("Recommendation list not found")
    if row["expires_at"] <= datetime.now(timezone.utc):
        raise RecommendationListExpired("This list has expired. Request recommendations again.")
    payload = row["payload"]
    # A saved ID must not retain access after campaign/contact reassignment or deletion.
    try:
        repository.get_campaign(payload["campaign_id"], scope)
    except repository.CampaignUnavailable as exc:
        raise RecommendationListNotFound("Recommendation list not found") from exc
    owned = {client.contact_id for client in repository.list_clients_for_fa(scope)}
    saved = {client["contact_id"] for key in ("clients", "incomplete_clients") for client in payload[key]}
    if not saved.issubset(owned):
        raise RecommendationListExpired("Client access has changed. Request recommendations again.")
    return {**payload, "list_id": str(list_id), "expires_at": row["expires_at"].isoformat()}
