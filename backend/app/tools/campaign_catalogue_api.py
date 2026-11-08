"""Read the CRM campaign API for active-campaign discovery only."""
from datetime import date
from math import isfinite
import os

import httpx
from pydantic import BaseModel, Field, TypeAdapter

from app.config import get_settings
from app.campaigns.models import CampaignCriteriaPayload
from app.campaigns.repository import (
    CAMPAIGN_ID_PATTERN, DEMO_TENANT, Campaign, CampaignStorageUnavailable,
    Criteria, RequestScope,
)


class _CatalogueCampaign(BaseModel):
    # Validate consumed fields without importing the FastAPI host into MCP.
    id: str = Field(pattern=CAMPAIGN_ID_PATTERN, max_length=69)
    name: str = Field(min_length=1, max_length=200)
    description: str
    status: str
    startDate: date | None
    endDate: date | None
    criteria: CampaignCriteriaPayload


def fetch_campaigns(scope: RequestScope) -> tuple[Campaign, ...]:
    """Fetch creator-owned campaigns without a direct database fallback."""
    # The endpoint derives tenant from fa_id and cannot express another tenant.
    if scope.tenant_id not in (DEMO_TENANT, scope.fa_id):
        raise CampaignStorageUnavailable("Campaign API does not support this tenant context")
    settings = get_settings()
    base_url = settings.campaign_api_base_url or f"http://127.0.0.1:{os.environ.get('PORT', '4000')}"
    auth = None
    if settings.demo_auth_enabled:
        auth = httpx.BasicAuth(
            settings.demo_auth_username, settings.demo_auth_password.get_secret_value()
        )
    try:
        with httpx.Client(base_url=base_url, timeout=10, auth=auth, trust_env=False) as client:
            response = client.get('/api/campaigns', params={'role': 'advisor', 'fa_id': scope.fa_id})
            response.raise_for_status()
            records = TypeAdapter(list[_CatalogueCampaign]).validate_python(response.json())
        campaigns = []
        for record in records:
            criteria = record.criteria
            age, cash = criteria.ageRange, criteria.cashRange
            for bound in (age.min, age.max) if age else ():
                if bound is not None and (not bound.is_integer() or bound > 130):
                    raise ValueError('Invalid age range')
            for bound in (cash.min, cash.max) if cash else ():
                if bound is not None and not isfinite(bound):
                    raise ValueError('Invalid cash range')
            campaigns.append(Campaign(
                campaign_id=record.id, name=record.name, description=record.description,
                status=record.status, start_date=record.startDate, end_date=record.endDate,
                tenant_id=scope.tenant_id, fa_ids=(scope.fa_id,),
                criteria=Criteria(
                    age_groups=tuple(criteria.ageGroups), genders=tuple(criteria.genders),
                    cash_bands=tuple(criteria.cashBands),
                    age_min=int(age.min) if age and age.min is not None else None,
                    age_max=int(age.max) if age and age.max is not None else None,
                    cash_min=cash.min if cash else None, cash_max=cash.max if cash else None,
                ),
            ))
        return tuple(sorted(campaigns, key=lambda campaign: campaign.campaign_id))
    except (httpx.HTTPError, ValueError) as exc:
        raise CampaignStorageUnavailable("Campaign API is temporarily unavailable or returned invalid data") from exc
