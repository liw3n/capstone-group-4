"""Shared read-only handlers for preparing and revising campaign drafts."""
from copy import deepcopy
import re
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from app.campaigns.models import (
    CAMPAIGN_TARGETING_FIELDS,
    CampaignDraftArtifact,
    CampaignDraftRevisionArtifact,
    PrepareCampaignDraftArguments,
    ReviseCampaignDraftArguments,
    campaign_revision_changed_fields,
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


_AGE_LABELS = {
    "under35": "Under 35",
    "35to44": "35 to 44",
    "45to54": "45 to 54",
    "55to64": "55 to 64",
    "65plus": "65 and above",
}
_GENDER_LABELS = {"male": "Male", "female": "Female"}
_CASH_LABELS = {
    "under50k": "Below SGD 50k",
    "50kTo250k": "SGD 50k to SGD 250k",
    "250kTo1m": "SGD 250k to SGD 1m",
    "above1m": "Above SGD 1m",
}


def _targeting_text(criteria) -> tuple[str, dict[str, str]]:
    age = ", ".join(_AGE_LABELS[value] for value in criteria.ageGroups)
    genders = ", ".join(_GENDER_LABELS[value] for value in criteria.genders)
    cash = ", ".join(_CASH_LABELS[value] for value in criteria.cashBands)
    age = age or "any age"
    genders = genders or "all genders"
    cash = cash or "no cash threshold"
    summary = (
        f"Clients in the following age targeting: {age}; gender targeting: "
        f"{genders}; cash targeting: {cash}."
    )
    rationale = {
        "ageGroups": (
            f"The adviser selected these age groups during draft review: {age}."
            if criteria.ageGroups
            else "No age restriction is set for this draft."
        ),
        "genders": (
            f"The adviser selected this gender targeting during draft review: {genders}."
            if criteria.genders
            else "No gender restriction is set; the draft applies to all genders."
        ),
        "cashBands": (
            f"The adviser selected these cash bands during draft review: {cash}."
            if criteria.cashBands
            else "No cash threshold is set for this draft."
        ),
    }
    return summary, rationale


def _targeting_normalization_warnings(request: ReviseCampaignDraftArguments) -> list[str]:
    instruction = (request.instruction or "").casefold()
    warnings: list[str] = []
    if "ageGroups" in request.fields and re.search(
        r"\b(?:above|over|older than)\s*65\b", instruction
    ):
        warnings.append(
            "The requested age threshold was normalized to the supported "
            "65-and-above age group."
        )
    if "cashBands" in request.fields and re.search(
        r"\b(?:above|over|more than)\s*(?:sgd|\$)?\s*"
        r"250(?:,?000|\s*k)\b",
        instruction,
    ):
        warnings.append(
            "The requested cash threshold was normalized to the supported "
            "SGD 250k-to-1m and above-SGD-1m bands."
        )
    return warnings


def _apply_revision_changes(request: ReviseCampaignDraftArguments):
    revised = deepcopy(request.currentDraft.model_dump())
    changes = request.proposedChanges.model_dump(exclude_unset=True)
    for field_name in request.fields:
        if field_name in CAMPAIGN_TARGETING_FIELDS:
            revised["criteria"][field_name] = changes[field_name]
        else:
            revised[field_name] = changes[field_name]
    selected_targeting = CAMPAIGN_TARGETING_FIELDS.intersection(request.fields)
    if selected_targeting:
        criteria = request.currentDraft.criteria.__class__.model_validate(
            revised["criteria"]
        )
        summary, rationale = _targeting_text(criteria)
        revised["rationale"] = rationale
        revised["targetDemographicSummary"] = summary
    return request.currentDraft.__class__.model_validate(revised)


def _field_value(draft, field_name: str):
    if field_name in CAMPAIGN_TARGETING_FIELDS:
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

        changed_fields = campaign_revision_changed_fields(request.fields)
        selected = set(changed_fields)
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
                [
                    *review_warnings,
                    *_targeting_normalization_warnings(request),
                    *validation.warnings,
                ]
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
        changedFields=list(changed_fields),
        validation=validation,
    ).model_dump(mode="json")
