"""Shared model argument validation and request-scoped recommendation handler."""
from pydantic import BaseModel, ConfigDict, Field

from app.campaigns.matching import MAX_RESULTS, collect_campaign_recommendations, recommendation_preview
from app.campaigns.recommendation_lists import save_list
from uuid import UUID
from app.campaigns.repository import (
    CAMPAIGN_ID_PATTERN, CampaignInactive, CampaignStorageUnavailable, CampaignUnavailable, RequestScope,
)


PREVIEW_LIMIT = 10


class RecommendationArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    campaign_id: str = Field(pattern=CAMPAIGN_ID_PATTERN, max_length=69)
    limit: int = Field(default=PREVIEW_LIMIT, ge=1, le=MAX_RESULTS, strict=True)


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
        if type(limit) is not int or not 1 <= limit <= MAX_RESULTS:
            return {"data_source": "synthetic", "error_code": "invalid_arguments", "error": "Invalid preview limit"}
        full = collect_campaign_recommendations(campaign_id, scope)
        preview = recommendation_preview(full, min(limit, PREVIEW_LIMIT))
        snapshot = {"list_id": None, "expires_at": None}
        if preview["truncated"] or preview["incomplete_truncated"]:
            snapshot = save_list(scope, full, (metadata or {}).get("session_id"))
        return {**preview, **snapshot, "preview_limit": PREVIEW_LIMIT}
    except CampaignUnavailable as exc:
        return {"data_source": "synthetic", "error": str(exc), "error_code": "campaign_unavailable"}
    except CampaignInactive as exc:
        return {"data_source": "synthetic", "error": str(exc), "error_code": "campaign_inactive"}
    except CampaignStorageUnavailable as exc:
        return {"data_source": "synthetic", "error": str(exc), "error_code": "storage_unavailable"}


def render_recommendation_download(payload: dict) -> str:
    """Append only a trusted download action; Groq owns the visible client reply."""
    if not payload.get("list_id"):
        return ""
    list_id = str(UUID(payload["list_id"]))
    return (
        f"[Download full results (.xlsx)](#recommendation-excel-{list_id})\n\n"
        "The download includes all matching clients and incomplete profiles, including rows beyond this preview. Available for 24 hours."
    )
