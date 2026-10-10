"""Shared model argument validation and request-scoped recommendation handler."""
from pydantic import BaseModel, ConfigDict, Field

from app.campaigns.matching import MAX_RESULTS, recommend_clients_for_campaign
from app.campaigns.repository import (
    CAMPAIGN_ID_PATTERN, CampaignInactive, CampaignStorageUnavailable, CampaignUnavailable, RequestScope,
)


class RecommendationArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    campaign_id: str = Field(pattern=CAMPAIGN_ID_PATTERN, max_length=69)
    limit: int = Field(default=MAX_RESULTS, ge=1, le=MAX_RESULTS, strict=True)


def execute_recommendation(campaign_id: str, limit: int, metadata: dict | None) -> dict:
    context = (metadata or {}).get("pulse_scope")
    if not isinstance(context, dict):
        return {"data_source": "synthetic", "error": "Adviser request context is required",
                "error_code": "missing_context"}
    try:
        scope = RequestScope(fa_id=context.get("fa_id"), tenant_id=context.get("tenant_id"))
    except ValueError:
        return {"data_source": "synthetic", "error": "Adviser request context is required",
                "error_code": "missing_context"}
    try:
        return recommend_clients_for_campaign(campaign_id, scope, limit)
    except CampaignUnavailable as exc:
        return {"data_source": "synthetic", "error": str(exc), "error_code": "campaign_unavailable"}
    except CampaignInactive as exc:
        return {"data_source": "synthetic", "error": str(exc), "error_code": "campaign_inactive"}
    except CampaignStorageUnavailable as exc:
        return {"data_source": "synthetic", "error": str(exc), "error_code": "storage_unavailable"}
