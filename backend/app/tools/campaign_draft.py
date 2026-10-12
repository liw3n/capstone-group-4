"""Shared read-only handler for validating a model-generated campaign draft."""
from pydantic import ValidationError

from app.campaigns.models import (
    CampaignDraftArtifact,
    PrepareCampaignDraftArguments,
)
from app.campaigns.reference_repository import (
    CampaignReferenceRepository,
    CatalogueConfigurationError,
    RetrievalTokenError,
    get_reference_repository,
)
from app.campaigns.validation import (
    CampaignDraftPolicyError,
    add_required_review_language,
    validate_campaign_draft_policy,
)
from app.tools.campaign_references import scope_from_metadata


def _error(
    code: str,
    message: str,
    *,
    field: str | None = None,
    rule: str | None = None,
) -> dict:
    result = {
        "data_source": "ai_generated",
        "error_code": code,
        "error": message,
        "created": False,
    }
    if field is not None:
        result["field"] = field
    if rule is not None:
        result["rule"] = rule
    return result


def execute_prepare_campaign_draft(
    arguments: dict,
    metadata: dict | None,
    repository: CampaignReferenceRepository | None = None,
) -> dict:
    scope = scope_from_metadata(metadata)
    if scope is None:
        return _error("missing_context", "Adviser request context is required")
    try:
        request = PrepareCampaignDraftArguments.model_validate(arguments)
    except ValidationError:
        return _error("invalid_draft", "Campaign draft arguments are invalid")

    try:
        service = repository or get_reference_repository()
        claims = service.verify_token(request.retrievalToken, request.objective, scope)
    except CatalogueConfigurationError:
        return _error("catalogue_unavailable", "Campaign reference catalogue is unavailable")
    except RetrievalTokenError as exc:
        return _error(exc.code, str(exc))

    allowed_references = set(claims.references)
    cited_references = {
        (citation.referenceId, citation.version) for citation in request.referencesUsed
    }
    if not cited_references <= allowed_references:
        return _error(
            "invalid_reference_citation",
            "Draft citations must be a subset of the retrieved campaign references",
        )

    catalogue_lookup = {
        (entry.referenceId, entry.version): entry for entry in service.catalogue.entries
    }
    try:
        references = [catalogue_lookup[citation] for citation in cited_references]
    except KeyError:
        return _error(
            "invalid_reference_citation",
            "A cited campaign reference is unavailable",
        )

    try:
        normalized_draft, review_warnings = add_required_review_language(request.draft)
        validation = validate_campaign_draft_policy(
            request.objective, normalized_draft, references
        )
        validation = validation.model_copy(update={
            "warnings": list(dict.fromkeys(
                [*review_warnings, *validation.warnings]
            ))[:10]
        })
    except ValidationError:
        return _error("invalid_draft", "Campaign draft arguments are invalid")
    except CampaignDraftPolicyError as exc:
        return _error(exc.code, str(exc), field=exc.field, rule=exc.rule)

    return CampaignDraftArtifact(
        objective=request.objective,
        referencesUsed=request.referencesUsed,
        draft=normalized_draft,
        validation=validation,
    ).model_dump(mode="json")
