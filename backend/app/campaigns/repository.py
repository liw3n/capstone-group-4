"""Tenant-scoped PostgreSQL reads of synthetic prototype tables."""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
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


class CampaignAmbiguous(ValueError):
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
            SELECT c.name, c.start_date, c.end_date, c.audience_criteria
            FROM campaign AS c
            WHERE c.campaign_id = %s AND c.tenant_id = %s
            """,
            (campaign_id, scope.fa_id),
        ).fetchone()
    if row is None:
        return None

    audience_criteria = row.get("audience_critera", {})
    criteria = Criteria(
        age_groups=tuple(audience_criteria.get("ageGroups", [])), genders=tuple(audience_criteria.get("genders", [])),
        cash_bands=tuple(audience_criteria.get("cashBands", [])), age_min=audience_criteria.get("ageCustomMin"), age_max=audience_criteria.get("ageCustomMax"),
        cash_min=float(audience_criteria.get("cashCustomMin")) if audience_criteria.get("cashCustomMin") is not None else None,
        cash_max=float(audience_criteria.get("cashCustomMax")) if audience_criteria.get("ageCustomMax") is not None else None,
    )
    return Campaign(campaign_id=campaign_id, name=row["name"], criteria=criteria,
                    fa_ids=(scope.fa_id,), start_date=row["start_date"], end_date=row["end_date"])


def get_campaign(campaign_id: str, scope: RequestScope) -> Campaign:
    """Inaccessible and unknown IDs look alike, without exposing other rows."""
    if not isinstance(campaign_id, str):
        raise CampaignUnavailable("Campaign not found or unavailable to this adviser")
    campaign = _load_campaign(campaign_id, scope)
    if campaign is None:
        raise CampaignUnavailable("Campaign not found or unavailable to this adviser")
    return campaign


def get_campaign_by_name(name: str, scope: RequestScope) -> Campaign:
    """Resolve an exact name only among this adviser's campaigns."""
    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT c.campaign_id
            FROM mock_campaign AS c
            JOIN mock_campaign_advisor AS a
              ON a.tenant_id = c.tenant_id AND a.campaign_id = c.campaign_id
            WHERE c.tenant_id = %s AND a.fa_id = %s
              AND lower(c.name) = lower(%s)
            ORDER BY c.campaign_id
            LIMIT 2
            """,
            (scope.tenant_id, scope.fa_id, name),
        ).fetchall()
    if not rows:
        raise CampaignUnavailable("Campaign not found or unavailable to this adviser")
    if len(rows) > 1:
        raise CampaignAmbiguous("Multiple accessible campaigns have that name; select one by ID")
    return get_campaign(rows[0]["campaign_id"], scope)


def count_campaign_contacts(scope: RequestScope, campaign_id: str,
                            period_start: datetime, period_end: datetime,
                            week_start: datetime,
                            last_week_start: datetime) -> tuple[int, int, int, int, int]:
    """Count distinct in-scope clients and weekly contacts from recorded events."""
    with _connection() as connection:
        row = connection.execute(
            """
            WITH contacted_clients AS (
                SELECT contact_id, MIN(contacted_at) AS first_contacted_at,
                       BOOL_OR(contacted_at >= %s) AS contacted_this_week,
                       BOOL_OR(contacted_at >= %s AND contacted_at < %s)
                           AS contacted_last_week
                FROM mock_campaign_contact_event
                WHERE tenant_id = %s AND fa_id = %s AND campaign_id = %s
                  AND contacted_at >= %s AND contacted_at < %s
                GROUP BY contact_id
            )
            SELECT COUNT(*) AS contacted_clients_total,
                   COUNT(*) FILTER (WHERE contacted_this_week) AS contacted_clients_this_week,
                   COUNT(*) FILTER (WHERE first_contacted_at >= %s)
                       AS first_contacted_clients_this_week,
                   COUNT(*) FILTER (WHERE contacted_last_week)
                       AS contacted_clients_last_week,
                   COUNT(*) FILTER (WHERE first_contacted_at >= %s
                                   AND first_contacted_at < %s)
                       AS first_contacted_clients_last_week
            FROM contacted_clients
            """,
            (week_start, last_week_start, week_start,
             scope.tenant_id, scope.fa_id, campaign_id,
             period_start, period_end, week_start, last_week_start, week_start),
        ).fetchone()
    return (row["contacted_clients_total"], row["contacted_clients_this_week"],
            row["first_contacted_clients_this_week"],
            row["contacted_clients_last_week"],
            row["first_contacted_clients_last_week"])


def count_campaign_contacts_in_period(scope: RequestScope, campaign_id: str,
                                      period_start: datetime, period_end: datetime) -> int:
    """Count distinct clients contacted in one bounded campaign period."""
    with _connection() as connection:
        row = connection.execute(
            """
            SELECT COUNT(DISTINCT contact_id) AS contacted_clients
            FROM mock_campaign_contact_event
            WHERE tenant_id = %s AND fa_id = %s AND campaign_id = %s
              AND contacted_at >= %s AND contacted_at < %s
            """,
            (scope.tenant_id, scope.fa_id, campaign_id, period_start, period_end),
        ).fetchone()
    return row["contacted_clients"]


def rank_campaigns_by_contacts(scope: RequestScope, period_start: datetime | None,
                               period_end: datetime) -> tuple[dict, ...]:
    """Rank accessible campaigns by distinct contacted clients, including zeroes."""
    with _connection() as connection:
        rows = connection.execute(
            """
            WITH campaign_counts AS (
                SELECT c.campaign_id, c.name, c.status,
                       COUNT(DISTINCT e.contact_id) AS contacted_clients
                FROM mock_campaign AS c
                JOIN mock_campaign_advisor AS a
                  ON a.tenant_id = c.tenant_id AND a.campaign_id = c.campaign_id
                LEFT JOIN mock_campaign_contact_event AS e
                  ON e.tenant_id = c.tenant_id
                 AND e.campaign_id = c.campaign_id AND e.fa_id = a.fa_id
                 AND e.contacted_at >=
                     (c.start_date::timestamp AT TIME ZONE 'Asia/Singapore')
                 AND e.contacted_at <
                     ((c.end_date + 1)::timestamp AT TIME ZONE 'Asia/Singapore')
                 AND (%s::timestamptz IS NULL OR e.contacted_at >= %s::timestamptz)
                 AND e.contacted_at < %s
                WHERE c.tenant_id = %s AND a.fa_id = %s
                GROUP BY c.campaign_id, c.name, c.status
            )
            SELECT campaign_id, name, status, contacted_clients,
                   COUNT(*) OVER () AS campaign_count,
                   COUNT(*) OVER (PARTITION BY contacted_clients) AS tie_count
            FROM campaign_counts
            ORDER BY contacted_clients DESC, name, campaign_id
            LIMIT 21
            """,
            (period_start, period_start, period_end, scope.tenant_id, scope.fa_id),
        ).fetchall()
    return tuple(rows)


def require_active(campaign: Campaign, as_of: date = DEMO_DATE) -> None:
    if not campaign.start_date <= as_of <= campaign.end_date:
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


def list_active_campaigns(scope: RequestScope, as_of: date,
                          campaign_ids: list[str] | None = None,
                          campaign_names: list[str] | None = None) -> tuple[Campaign, ...]:
    """Active campaigns assigned to this user (fa_id) in this tenant; exact filters."""
    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT c.campaign_id, c.tenant_id, c.name, c.status, c.start_date, c.end_date,
                   c.age_groups, c.genders, c.cash_bands,
                   c.age_min, c.age_max, c.cash_min, c.cash_max
            FROM mock_campaign AS c
            JOIN mock_campaign_advisor AS a
              ON a.tenant_id = c.tenant_id AND a.campaign_id = c.campaign_id
            WHERE c.tenant_id = %s AND a.fa_id = %s AND c.status = 'active'
              AND c.start_date <= %s AND c.end_date >= %s
              AND (%s::text[] IS NULL OR c.campaign_id = ANY(%s::text[]))
              AND (%s::text[] IS NULL OR lower(c.name) = ANY(%s::text[]))
            ORDER BY c.campaign_id
            """,
            (scope.tenant_id, scope.fa_id, as_of, as_of, campaign_ids, campaign_ids,
             campaign_names, [name.lower() for name in campaign_names]
             if campaign_names is not None else None),
        ).fetchall()
    return tuple(Campaign(
        campaign_id=row['campaign_id'], name=row['name'], tenant_id=row['tenant_id'],
        fa_ids=(scope.fa_id,), status=row['status'], start_date=row['start_date'], end_date=row['end_date'],
        criteria=Criteria(
            age_groups=tuple(row['age_groups']), genders=tuple(row['genders']),
            cash_bands=tuple(row['cash_bands']), age_min=row['age_min'], age_max=row['age_max'],
            cash_min=float(row['cash_min']) if row['cash_min'] is not None else None,
            cash_max=float(row['cash_max']) if row['cash_max'] is not None else None,
        ),
    ) for row in rows)
