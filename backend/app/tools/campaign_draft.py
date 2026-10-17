"""Shared read-only handlers for preparing and revising campaign drafts."""
from copy import deepcopy
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from app.campaigns.models import (
    CampaignDraftArtifact,
    CampaignDraftRevisionArtifact,
    PrepareCampaignDraftArguments,
    ReviseCampaignDraftArguments,
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


def _revision_references(
    request: ReviseCampaignDraftArguments,
    scope,
    service: CampaignReferenceRepository,
):
    """Resolve only currently approved, in-scope citations from the catalogue."""
    as_of = service.clock().astimezone(ZoneInfo("Asia/Singapore")).date()
    catalogue_lookup = {
        (entry.referenceId, entry.version): entry
        for entry in service.catalogue.entries
        if scope.tenant_id in entry.tenantIds
        and entry.approvalStatus == "approved"
        and entry.validFrom <= as_of
        and (entry.validUntil is None or entry.validUntil >= as_of)
    }
    citations = [
        (citation.referenceId, citation.version) for citation in request.referencesUsed
    ]
    try:
        return [catalogue_lookup[citation] for citation in citations]
    except KeyError as exc:
        raise RetrievalTokenError(
            "invalid_reference_citation",
            "A cited campaign reference is unavailable for revision",
        ) from exc


def _apply_revision_changes(request: ReviseCampaignDraftArguments):
    revised = deepcopy(request.currentDraft.model_dump())
    changes = request.proposedChanges.model_dump(exclude_unset=True)
    for field_name in request.fields:
        if field_name in {"ageGroups", "genders", "cashBands"}:
            revised["criteria"][field_name] = changes[field_name]
        else:
            revised[field_name] = changes[field_name]
    return request.currentDraft.__class__.model_validate(revised)


def _field_value(draft, field_name: str):
    if field_name in {"ageGroups", "genders", "cashBands"}:
        return getattr(draft.criteria, field_name)
    return getattr(draft, field_name)


def execute_revise_campaign_draft(
    arguments: dict,
    metadata: dict | None,
    repository: CampaignReferenceRepository | None = None,
) -> dict:
    """Apply selected changes to a validated draft without persisting anything."""
    scope = scope_from_metadata(metadata)
    if scope is None:
        return _error("missing_context", "Adviser request context is required")
    try:
        request = ReviseCampaignDraftArguments.model_validate(arguments)
    except ValidationError:
        return _error("invalid_draft", "Campaign draft revision arguments are invalid")

    try:
        service = repository or get_reference_repository()
        references = _revision_references(request, scope, service)

        # The host must supply the previously validated artifact as currentDraft.
        # Revalidation here fails closed if that boundary is violated.
        validate_campaign_draft_policy(
            request.objective, request.currentDraft, references
        )
        revised_draft = _apply_revision_changes(request)
        normalized_draft, review_warnings = add_required_review_language(revised_draft)

        selected = set(request.fields)
        for field_name in (
            "name", "description", "clientMessage", "ageGroups", "genders",
            "cashBands", "targetDemographicSummary",
        ):
            if field_name not in selected and _field_value(
                normalized_draft, field_name
            ) != _field_value(request.currentDraft, field_name):
                return _error(
                    "invalid_draft",
                    "Campaign draft revision changed an unselected field",
                    field=field_name,
                    rule="unselected_field_changed",
                )

        validation = validate_campaign_draft_policy(
            request.objective, normalized_draft, references
        )
        validation = validation.model_copy(update={
            "warnings": list(dict.fromkeys(
                [*review_warnings, *validation.warnings]
            ))[:10]
        })
    except CatalogueConfigurationError:
        return _error("catalogue_unavailable", "Campaign reference catalogue is unavailable")
    except RetrievalTokenError as exc:
        return _error(exc.code, str(exc))
    except ValidationError:
        return _error("invalid_draft", "Campaign draft revision arguments are invalid")
    except CampaignDraftPolicyError as exc:
        return _error(exc.code, str(exc), field=exc.field, rule=exc.rule)

    return CampaignDraftRevisionArtifact(
        objective=request.objective,
        referencesUsed=request.referencesUsed,
        draft=normalized_draft,
        previousRevision=request.revision,
        revision=request.revision + 1,
        changedFields=request.fields,
        validation=validation,
    ).model_dump(mode="json")
