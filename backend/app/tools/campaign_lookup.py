"""Read-only campaign identity resolution, separate from catalogue presentation."""
import re
import unicodedata

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.campaigns import repository
from app.campaigns.repository import CampaignStorageUnavailable, RequestScope
from app.tools import discovery

MAX_CANDIDATES = 5


class ResolveCampaignArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    campaign_name: str = Field(min_length=1, max_length=255, strict=True)


def _words(value: str) -> str:
    return " ".join(re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", value).casefold()))


def _error(code: str, message: str) -> dict:
    return {"data_source": "synthetic", "error_code": code, "error": message}


def execute_resolve_campaign(arguments: dict, metadata: dict | None) -> dict:
    context = metadata.get("pulse_scope") if isinstance(metadata, dict) else None
    if not isinstance(context, dict):
        return _error("missing_context", "Adviser request context is required")
    try:
        scope = RequestScope(fa_id=context.get("fa_id"), tenant_id=context.get("tenant_id"))
    except ValueError:
        return _error("missing_context", "Adviser request context is required")
    try:
        query = ResolveCampaignArguments.model_validate(arguments)
    except ValidationError:
        return _error("invalid_arguments", "Invalid tool arguments")

    as_of = discovery.current_date()
    try:
        campaigns = repository.list_active_campaigns(scope, as_of)
    except CampaignStorageUnavailable as exc:
        return _error("storage_unavailable", str(exc))

    # Prefer exact canonical names before removing conversational words. This
    # preserves real names that themselves end in "Campaign" or begin with "The".
    name = _words(query.campaign_name)
    matches = [campaign for campaign in campaigns if _words(campaign.name) == name]
    if not matches:
        words = name.split()
        if words and words[0] == "the":
            words = words[1:]
        if words and words[-1] == "campaign":
            words = words[:-1]
        name = " ".join(words)
        if name:
            matches = [campaign for campaign in campaigns if _words(campaign.name) == name]
            if not matches:
                # Whole-word partial phrases may identify several campaigns;
                # return ambiguity instead of inventing a best-match score.
                matches = [campaign for campaign in campaigns
                           if f" {name} " in f" {_words(campaign.name)} "]

    result = {"data_source": "synthetic", "as_of_date": as_of.isoformat()}
    if not matches:
        return {**result, "status": "not_found", "candidate_count": 0,
                "message": "No accessible active campaign matches that name. Ask for the campaign name, not its internal ID."}
    if len(matches) == 1:
        return {**result, "status": "matched", "campaign_id": matches[0].campaign_id,
                "name": matches[0].name}
    matches.sort(key=lambda campaign: (campaign.name.casefold(), campaign.campaign_id))
    return {
        **result, "status": "ambiguous", "candidate_count": len(matches),
        "candidates": [{"campaign_id": campaign.campaign_id, "name": campaign.name}
                       for campaign in matches[:MAX_CANDIDATES]],
        "truncated": len(matches) > MAX_CANDIDATES,
        "message": "Several campaigns match. Ask the adviser which campaign name they mean before requesting recommendations.",
    }
