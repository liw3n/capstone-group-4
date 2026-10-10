"""Tenant-scoped PostgreSQL reads of synthetic prototype tables."""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
import re

DEMO_DATE = date(2026, 8, 26)  # Same as frontend/data/seed.ts.
DEMO_TENANT = "pulse-demo"
DEMO_FA = "adv-steven-raynaldi"
CAMPAIGN_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,68}$"


@dataclass(frozen=True)
class RequestScope:
    fa_id: str
    tenant_id: str = DEMO_TENANT

    def __post_init__(self):
        if not isinstance(self.fa_id, str) or not self.fa_id.strip():
            raise ValueError("Adviser context is required")
        if not isinstance(self.tenant_id, str) or not self.tenant_id.strip():
            raise ValueError("Tenant context is required")


@dataclass(frozen=True)
class Criteria:
    age_groups: tuple[str, ...] = ()
    genders: tuple[str, ...] = ()
    cash_bands: tuple[str, ...] = ()
    age_min: int | None = None
    age_max: int | None = None
    cash_min: float | None = None
    cash_max: float | None = None


@dataclass(frozen=True)
class Campaign:
    campaign_id: str
    name: str
    criteria: Criteria
    fa_ids: tuple[str, ...] = (DEMO_FA,)
    tenant_id: str = DEMO_TENANT
    status: str = "active"
    start_date: date = date(2026, 8, 1)
    end_date: date = date(2026, 12, 31)


@dataclass(frozen=True)
class Client:
    contact_id: str
    fa_id: str
    name: str
    dob: str | None
    gender: str | None
    available_cash: float | None
    tenant_id: str = DEMO_TENANT


class CampaignUnavailable(ValueError):
    pass


class CampaignInactive(ValueError):
    pass


class CampaignStorageUnavailable(RuntimeError):
    """Safe error for configuration, connection or query failures."""


@contextmanager
def _connection():
    import psycopg
    from psycopg.rows import dict_row
    from app.config import get_settings

    database_url = get_settings().database_url
    if not database_url:
        raise CampaignStorageUnavailable("Campaign database is not configured")
    try:
        # Bound connection and query time. Runtime recommendations perform reads only.
        with psycopg.connect(database_url, row_factory=dict_row, connect_timeout=5) as connection:
            connection.execute("SET LOCAL statement_timeout = '5s'")
            connection.execute("SET TRANSACTION READ ONLY")
            yield connection
    except psycopg.Error as exc:
        raise CampaignStorageUnavailable("Campaign database is temporarily unavailable") from exc


def _load_campaign(campaign_id: str, scope: RequestScope) -> Campaign | None:
    with _connection() as connection:
        row = connection.execute(
            """
            SELECT c.campaign_id, c.tenant_id, c.name, c.status, c.start_date, c.end_date,
                   c.age_groups, c.genders, c.cash_bands,
                   c.age_min, c.age_max, c.cash_min, c.cash_max
            FROM mock_campaign AS c
            JOIN mock_campaign_advisor AS a
              ON a.tenant_id = c.tenant_id AND a.campaign_id = c.campaign_id
            WHERE c.campaign_id = %s AND c.tenant_id = %s AND a.fa_id = %s
            """,
            (campaign_id, scope.tenant_id, scope.fa_id),
        ).fetchone()
    if row is None:
        return None
    criteria = Criteria(
        age_groups=tuple(row["age_groups"]), genders=tuple(row["genders"]),
        cash_bands=tuple(row["cash_bands"]), age_min=row["age_min"], age_max=row["age_max"],
        cash_min=float(row["cash_min"]) if row["cash_min"] is not None else None,
        cash_max=float(row["cash_max"]) if row["cash_max"] is not None else None,
    )
    return Campaign(campaign_id=row["campaign_id"], name=row["name"], criteria=criteria,
                    tenant_id=row["tenant_id"], fa_ids=(scope.fa_id,), status=row["status"],
                    start_date=row["start_date"], end_date=row["end_date"])


def get_campaign(campaign_id: str, scope: RequestScope) -> Campaign:
    """Inaccessible and unknown IDs look alike, without exposing other rows."""
    if not isinstance(campaign_id, str) or not re.fullmatch(CAMPAIGN_ID_PATTERN, campaign_id):
        raise CampaignUnavailable("Campaign not found or unavailable to this adviser")
    campaign = _load_campaign(campaign_id, scope)
    if campaign is None:
        raise CampaignUnavailable("Campaign not found or unavailable to this adviser")
    return campaign


def require_active(campaign: Campaign, as_of: date = DEMO_DATE) -> None:
    if campaign.status != "active" or not campaign.start_date <= as_of <= campaign.end_date:
        raise CampaignInactive("Campaign is not active on the demo date")


def _load_clients(scope: RequestScope) -> tuple[Client, ...]:
    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT contact_id, tenant_id, fa_id, name, date_of_birth, gender, available_cash
            FROM mock_client
            WHERE tenant_id = %s AND fa_id = %s
            ORDER BY contact_id
            """,
            (scope.tenant_id, scope.fa_id),
        ).fetchall()
    return tuple(Client(
        contact_id=row["contact_id"], tenant_id=row["tenant_id"], fa_id=row["fa_id"],
        name=row["name"], dob=row["date_of_birth"].isoformat() if row["date_of_birth"] else None,
        gender=row["gender"],
        available_cash=float(row["available_cash"]) if row["available_cash"] is not None else None,
    ) for row in rows)


def list_clients_for_fa(scope: RequestScope) -> tuple[Client, ...]:
    """Filter ownership in SQL before any matching or counting. No fixture fallback."""
    return _load_clients(scope)
