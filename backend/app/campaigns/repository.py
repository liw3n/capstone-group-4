"""Tenant-scoped PostgreSQL reads of synthetic prototype tables."""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
import re
from math import isfinite
from uuid import UUID

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


def _storage_tenant_id(scope: RequestScope) -> str:
    """Map the legacy chat namespace to the new prototype's adviser tenant.

    The current CRM seeds use the adviser UUID as tenant_id. Explicit tenant
    scopes must remain explicit; never replace them with another tenant.
    """
    return scope.fa_id if scope.tenant_id == DEMO_TENANT else scope.tenant_id


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def _campaign_from_row(row: dict, scope: RequestScope) -> Campaign:
    raw = row.get("audience_criteria")
    if not isinstance(raw, dict):
        raise CampaignStorageUnavailable("Campaign targeting criteria are missing or invalid")
    aliases = {
        "ageGroups": {
            "under35": "under35", "35-44": "35to44", "35to44": "35to44",
            "45-54": "45to54", "45to54": "45to54", "55-64": "55to64",
            "55to64": "55to64", "65plus": "65plus",
        },
        "genders": {"male": "male", "female": "female"},
        "cashBands": {
            "under50k": "under50k", "50k-250k": "50kTo250k", "50kto250k": "50kTo250k",
            "250k-1m": "250kTo1m", "250kto1m": "250kTo1m", "above1m": "above1m",
        },
    }
    try:
        bands = {}
        for field, mapping in aliases.items():
            values = raw.get(field, [])
            if not isinstance(values, list):
                raise ValueError("Invalid targeting values")
            bands[field] = tuple(mapping[value.strip().lower()] for value in values)

        def bound(custom: str, legacy: str, side: str, age: bool = False):
            value = raw.get(custom)
            if value is None:
                value = (raw.get(legacy) or {}).get(side)
            if value is None:
                return None
            if isinstance(value, bool):
                raise ValueError("Invalid targeting bound")
            number = float(value)
            if not isfinite(number) or number < 0 or (age and (not number.is_integer() or number > 130)):
                raise ValueError("Invalid targeting bound")
            return int(number) if age else number

        criteria = Criteria(
            age_groups=bands["ageGroups"], genders=bands["genders"], cash_bands=bands["cashBands"],
            age_min=bound("ageCustomMin", "ageRange", "min", age=True),
            age_max=bound("ageCustomMax", "ageRange", "max", age=True),
            cash_min=bound("cashCustomMin", "cashRange", "min"),
            cash_max=bound("cashCustomMax", "cashRange", "max"),
        )
        for minimum, maximum in ((criteria.age_min, criteria.age_max), (criteria.cash_min, criteria.cash_max)):
            if minimum is not None and maximum is not None and minimum > maximum:
                raise ValueError("Invalid targeting range")
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as exc:
        raise CampaignStorageUnavailable("Campaign targeting criteria are invalid") from exc
    return Campaign(
        campaign_id=str(row["campaign_id"]), name=row["name"], criteria=criteria,
        tenant_id=scope.tenant_id, fa_ids=(scope.fa_id,), status=row["status"] or "active",
        start_date=row["start_date"], end_date=row["end_date"],
    )


CAMPAIGN_COLUMNS = "c.campaign_id, c.name, c.status, c.start_date, c.end_date, c.audience_criteria"


def _load_campaign(campaign_id: str, scope: RequestScope) -> Campaign | None:
    with _connection() as connection:
        if not all(_is_uuid(value) for value in (campaign_id, _storage_tenant_id(scope), scope.fa_id)):
            return None
        row = connection.execute(
            f"""
            SELECT {CAMPAIGN_COLUMNS}
            FROM campaign AS c
            WHERE c.campaign_id = %s AND c.tenant_id = %s
              AND c.created_by_user_id = %s AND c.is_deleted = FALSE
            """,
            (campaign_id, _storage_tenant_id(scope), scope.fa_id),
        ).fetchone()
    if row is None:
        return None

    return _campaign_from_row(row, scope)


def get_campaign(campaign_id: str, scope: RequestScope) -> Campaign:
    """Inaccessible and unknown IDs look alike, without exposing other rows."""
    if not isinstance(campaign_id, str) or not re.fullmatch(CAMPAIGN_ID_PATTERN, campaign_id):
        raise CampaignUnavailable("Campaign not found or unavailable to this adviser")
    campaign = _load_campaign(campaign_id, scope)
    if campaign is None:
        raise CampaignUnavailable("Campaign not found or unavailable to this adviser")
    return campaign


def get_campaign_by_name(name: str, scope: RequestScope) -> Campaign:
    """Resolve an exact name only among this adviser's campaigns."""
    with _connection() as connection:
        if not all(_is_uuid(value) for value in (_storage_tenant_id(scope), scope.fa_id)):
            raise CampaignUnavailable("Campaign not found or unavailable to this adviser")
        rows = connection.execute(
            f"""
            SELECT {CAMPAIGN_COLUMNS}
            FROM campaign AS c
            WHERE c.tenant_id = %s AND c.created_by_user_id = %s AND c.is_deleted = FALSE
              AND lower(c.name) = lower(%s)
            ORDER BY c.campaign_id
            LIMIT 2
            """,
            (_storage_tenant_id(scope), scope.fa_id, name),
        ).fetchall()
    if not rows:
        raise CampaignUnavailable("Campaign not found or unavailable to this adviser")
    if len(rows) > 1:
        raise CampaignAmbiguous("Multiple accessible campaigns have that name; select one by ID")
    return _campaign_from_row(rows[0], scope)


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
    if (campaign.status != "active" or campaign.start_date is None or campaign.end_date is None
            or not campaign.start_date <= as_of <= campaign.end_date):
        raise CampaignInactive("Campaign is not active on the demo date")


def _load_clients(scope: RequestScope) -> tuple[Client, ...]:
    with _connection() as connection:
        if not all(_is_uuid(value) for value in (_storage_tenant_id(scope), scope.fa_id)):
            return ()
        rows = connection.execute(
            """
            SELECT contact_id, full_name, date_of_birth
            FROM contact
            WHERE tenant_id = %s AND is_deleted = FALSE
              AND (assigned_to_user_id = %s OR
                   (assigned_to_user_id IS NULL AND created_by_user_id = %s))
            ORDER BY contact_id
            """,
            (_storage_tenant_id(scope), scope.fa_id, scope.fa_id),
        ).fetchall()
    # The contact table deliberately has no gender/available-cash columns. Use
    # the same explicitly synthetic portfolio enrichment as the CRM contact API.
    from app.contacts.catalog import _call_mock_portfolio_api
    gender, cash = _call_mock_portfolio_api([row["contact_id"] for row in rows])
    return tuple(Client(
        contact_id=str(row["contact_id"]), tenant_id=scope.tenant_id, fa_id=scope.fa_id,
        name=row["full_name"], dob=row["date_of_birth"].isoformat() if row["date_of_birth"] else None,
        gender=gender.get(row["contact_id"]),
        available_cash=cash.get(row["contact_id"]),
    ) for row in rows)


def list_clients_for_fa(scope: RequestScope) -> tuple[Client, ...]:
    """Filter ownership in SQL before any matching or counting. No fixture fallback."""
    return _load_clients(scope)


def list_active_campaigns(scope: RequestScope, as_of: date,
                          campaign_ids: list[str] | None = None,
                          campaign_names: list[str] | None = None) -> tuple[Campaign, ...]:
    """Active campaigns owned by this adviser in the prototype tenant; exact filters."""
    with _connection() as connection:
        if not all(_is_uuid(value) for value in (_storage_tenant_id(scope), scope.fa_id)):
            return ()
        rows = connection.execute(
            f"""
            SELECT {CAMPAIGN_COLUMNS}
            FROM campaign AS c
            WHERE c.tenant_id = %s AND c.created_by_user_id = %s
              AND c.is_deleted = FALSE AND COALESCE(c.status, 'active') = 'active'
              AND c.start_date <= %s AND c.end_date >= %s
              AND (%s::text[] IS NULL OR c.campaign_id::text = ANY(%s::text[]))
              AND (%s::text[] IS NULL OR lower(c.name) = ANY(%s::text[]))
            ORDER BY c.campaign_id
            """,
            (_storage_tenant_id(scope), scope.fa_id, as_of, as_of, campaign_ids, campaign_ids,
             campaign_names, [name.lower() for name in campaign_names]
             if campaign_names is not None else None),
        ).fetchall()
    return tuple(_campaign_from_row(row, scope) for row in rows)
