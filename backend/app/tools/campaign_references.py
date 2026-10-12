"""Shared handler for read-only campaign reference retrieval."""
from pydantic import ValidationError

from app.campaigns.models import CampaignReferenceQuery
from app.campaigns.reference_repository import (
    CampaignReferenceRepository,
    CatalogueConfigurationError,
    get_reference_repository,
)
from app.campaigns.repository import RequestScope


def scope_from_metadata(metadata: dict | None) -> RequestScope | None:
    context = metadata.get("pulse_scope") if isinstance(metadata, dict) else None
    if not isinstance(context, dict):
        return None
    try:
        return RequestScope(
            fa_id=context.get("fa_id"), tenant_id=context.get("tenant_id")
        )
    except ValueError:
        return None


def execute_find_campaign_references(
    arguments: dict,
    metadata: dict | None,
    repository: CampaignReferenceRepository | None = None,
) -> dict:
    scope = scope_from_metadata(metadata)
    if scope is None:
        return {
            "data_source": "synthetic_curated_catalogue",
            "error_code": "missing_context",
            "error": "Adviser request context is required",
        }
    try:
        query = CampaignReferenceQuery.model_validate(arguments)
    except ValidationError:
        return {
            "data_source": "synthetic_curated_catalogue",
            "error_code": "invalid_arguments",
            "error": "Invalid tool arguments",
        }
    try:
        service = repository or get_reference_repository()
        return service.find(query, scope).model_dump(mode="json")
    except CatalogueConfigurationError:
        return {
            "data_source": "synthetic_curated_catalogue",
            "error_code": "catalogue_unavailable",
            "error": "Campaign reference catalogue is unavailable",
        }
