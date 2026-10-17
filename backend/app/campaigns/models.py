"""Shared campaign-generation contracts and lifecycle definitions.

Model-facing inputs intentionally exclude adviser identity, tenant identity,
campaign status, creator details and timestamps. Those values belong to trusted
request metadata or to the later server-side confirmation workflow.
"""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

AgeGroup = Literal["under35", "35to44", "45to54", "55to64", "65plus"]
Gender = Literal["male", "female"]
CashBand = Literal["under50k", "50kTo250k", "250kTo1m", "above1m"]
CampaignCategory = Literal[
    "retirement", "protection", "education", "legacy", "property", "other"
]
CampaignCriteriaDimension = Literal["ageGroups", "genders", "cashBands"]
CampaignDraftField = Literal[
    "name", "description", "clientMessage", "ageGroups", "genders",
    "cashBands", "targetDemographicSummary",
]
CampaignDraftStatus = Literal[
    "generated", "reviewed", "confirmed", "rejected", "expired"
]
CampaignTurnAction = Literal[
    "ordinary_chat",
    "revise_fields",
    "suggest_field_options",
    "select_field_option",
    "show_current_draft",
    "start_new_draft",
    "needs_clarification",
]
CampaignGenerationErrorCode = Literal[
    "invalid_arguments", "missing_context", "catalogue_unavailable",
    "invalid_retrieval_token", "expired_retrieval_token", "scope_mismatch",
    "invalid_reference_citation", "invalid_draft", "unsupported_claim", "missing_disclaimer",
    "inconsistent_targeting", "stale_revision", "confirmation_required",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class NumericRangePayload(StrictModel):
    min: float | None = Field(default=None, ge=0)
    max: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_order(self):
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("range minimum cannot exceed maximum")
        return self


class CampaignCriteriaPayload(StrictModel):
    ageGroups: list[AgeGroup]
    ageRange: NumericRangePayload | None = None
    genders: list[Gender]
    cashBands: list[CashBand]
    cashRange: NumericRangePayload | None = None


class CampaignDraftCriteria(StrictModel):
    ageGroups: list[AgeGroup] = Field(max_length=5)
    genders: list[Gender] = Field(max_length=2)
    cashBands: list[CashBand] = Field(max_length=4)

    @model_validator(mode="after")
    def reject_duplicate_values(self):
        for field_name in ("ageGroups", "genders", "cashBands"):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must not contain duplicates")
        return self


class CampaignDraft(StrictModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=10_000)
    clientMessage: str = Field(min_length=1, max_length=10_000)
    criteria: CampaignDraftCriteria
    targetDemographicSummary: str = Field(min_length=1, max_length=1_000)
    rationale: dict[CampaignCriteriaDimension, str]
    assumptions: list[str] = Field(default_factory=list, max_length=10)
    disclaimer: str = Field(min_length=1, max_length=1_000)

    @model_validator(mode="after")
    def require_complete_rationale(self):
        expected = {"ageGroups", "genders", "cashBands"}
        if set(self.rationale) != expected:
            raise ValueError("rationale must cover ageGroups, genders and cashBands")
        if any(not value.strip() for value in self.rationale.values()):
            raise ValueError("rationale values must not be empty")
        if any(not assumption.strip() for assumption in self.assumptions):
            raise ValueError("assumptions must not contain empty values")
        return self


class CampaignReference(StrictModel):
    referenceId: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,79}$", max_length=80)
    title: str = Field(min_length=1, max_length=255)
    category: CampaignCategory
    objectiveTags: list[str] = Field(min_length=1, max_length=20)
    descriptionPattern: str = Field(min_length=1, max_length=2_000)
    messagingPattern: str = Field(min_length=1, max_length=2_000)
    typicalCriteria: CampaignDraftCriteria
    targetingRationale: dict[CampaignCriteriaDimension, str]
    requiredDisclaimers: list[str] = Field(min_length=1, max_length=10)
    prohibitedClaims: list[str] = Field(min_length=1, max_length=20)
    approvalStatus: Literal["approved", "retired"]
    version: int = Field(ge=1, strict=True)
    validFrom: date
    validUntil: date | None = None
    tenantIds: list[str] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_catalogue_entry(self):
        if self.validUntil is not None and self.validUntil < self.validFrom:
            raise ValueError("validUntil cannot precede validFrom")
        if set(self.targetingRationale) != {"ageGroups", "genders", "cashBands"}:
            raise ValueError("targetingRationale must cover every criteria dimension")
        normalized_tags = [tag.casefold() for tag in self.objectiveTags]
        if any(not tag for tag in normalized_tags) or len(normalized_tags) != len(set(normalized_tags)):
            raise ValueError("objectiveTags must be non-empty and unique")
        for field_name in ("requiredDisclaimers", "prohibitedClaims"):
            values = getattr(self, field_name)
            normalized_values = [value.casefold() for value in values]
            if (any(not value for value in normalized_values)
                    or len(normalized_values) != len(set(normalized_values))):
                raise ValueError(f"{field_name} must be non-empty and unique")
        if any(not value.strip() for value in self.targetingRationale.values()):
            raise ValueError("targetingRationale values must not be empty")
        normalized_tenants = [tenant.casefold() for tenant in self.tenantIds]
        if (any(not tenant for tenant in normalized_tenants)
                or len(normalized_tenants) != len(set(normalized_tenants))):
            raise ValueError("tenantIds must be non-empty and unique")
        return self


class CampaignReferenceCatalogue(StrictModel):
    catalogueVersion: int = Field(ge=1, strict=True)
    entries: list[CampaignReference] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def reject_duplicate_reference_ids(self):
        reference_ids = [entry.referenceId for entry in self.entries]
        if len(reference_ids) != len(set(reference_ids)):
            raise ValueError("catalogue contains duplicate referenceId values")
        return self


class CampaignReferenceQuery(StrictModel):
    objective: str = Field(min_length=10, max_length=2_000)
    categories: list[CampaignCategory] | None = Field(default=None, max_length=5)
    limit: int = Field(default=3, ge=1, le=3, strict=True)

    @model_validator(mode="after")
    def reject_duplicate_categories(self):
        if self.categories is not None and len(self.categories) != len(set(self.categories)):
            raise ValueError("categories must not contain duplicates")
        return self


class CampaignReferenceCitation(StrictModel):
    referenceId: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,79}$", max_length=80)
    version: int = Field(ge=1, strict=True)


class CampaignReferenceResultItem(CampaignReferenceCitation):
    title: str = Field(min_length=1, max_length=255)
    category: CampaignCategory
    matchedTags: list[str] = Field(max_length=20)
    matchReasons: list[Literal[
        "category_filter", "category_term", "objective_tag", "lexical_overlap"
    ]] = Field(min_length=1, max_length=4)
    descriptionPattern: str = Field(min_length=1, max_length=2_000)
    messagingPattern: str = Field(min_length=1, max_length=2_000)
    typicalCriteria: CampaignDraftCriteria
    targetingRationale: dict[CampaignCriteriaDimension, str]
    requiredDisclaimers: list[str] = Field(max_length=10)


class CampaignReferenceResult(StrictModel):
    type: Literal["campaign_references"] = "campaign_references"
    data_source: Literal["synthetic_curated_catalogue"] = "synthetic_curated_catalogue"
    query: str = Field(min_length=10, max_length=2_000)
    catalogueVersion: int = Field(ge=1, strict=True)
    retrievalToken: str = Field(min_length=20, max_length=8_000)
    references: list[CampaignReferenceResultItem] = Field(max_length=3)
    returnedCount: int = Field(ge=0, le=3)
    truncated: bool


class PrepareCampaignDraftArguments(StrictModel):
    objective: str = Field(min_length=10, max_length=2_000)
    retrievalToken: str = Field(min_length=20, max_length=8_000)
    referencesUsed: list[CampaignReferenceCitation] = Field(max_length=3)
    draft: CampaignDraft

    @model_validator(mode="after")
    def reject_duplicate_citations(self):
        citations = [
            (citation.referenceId, citation.version) for citation in self.referencesUsed
        ]
        if len(citations) != len(set(citations)):
            raise ValueError("referencesUsed must not contain duplicates")
        return self


class CampaignDraftChanges(StrictModel):
    """Model-proposed values for only the fields selected for revision."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1, max_length=10_000)
    clientMessage: str | None = Field(default=None, min_length=1, max_length=10_000)
    ageGroups: list[AgeGroup] | None = Field(default=None, max_length=5)
    genders: list[Gender] | None = Field(default=None, max_length=2)
    cashBands: list[CashBand] | None = Field(default=None, max_length=4)
    targetDemographicSummary: str | None = Field(
        default=None, min_length=1, max_length=1_000
    )

    @model_validator(mode="after")
    def reject_duplicate_criteria(self):
        for field_name in ("ageGroups", "genders", "cashBands"):
            values = getattr(self, field_name)
            if values is not None and len(values) != len(set(values)):
                raise ValueError(f"{field_name} must not contain duplicates")
        return self


class ReviseCampaignDraftArguments(StrictModel):
    objective: str = Field(min_length=10, max_length=2_000)
    referencesUsed: list[CampaignReferenceCitation] = Field(max_length=3)
    currentDraft: CampaignDraft
    proposedChanges: CampaignDraftChanges
    fields: list[CampaignDraftField] = Field(min_length=1, max_length=7)
    instruction: str | None = Field(default=None, max_length=2_000)
    revision: int = Field(ge=1, strict=True)

    @model_validator(mode="after")
    def validate_revision_selection(self):
        if len(self.fields) != len(set(self.fields)):
            raise ValueError("fields must not contain duplicates")
        selected = set(self.fields)
        proposed = set(self.proposedChanges.model_fields_set)
        if selected != proposed:
            raise ValueError("proposedChanges must contain exactly the selected fields")
        if any(getattr(self.proposedChanges, field) is None for field in proposed):
            raise ValueError("proposedChanges values must not be null")
        citations = [
            (citation.referenceId, citation.version) for citation in self.referencesUsed
        ]
        if len(citations) != len(set(citations)):
            raise ValueError("referencesUsed must not contain duplicates")
        return self


class CampaignDraftPreviewRequest(StrictModel):
    revision: int = Field(ge=1, strict=True)


class CampaignDraftConfirmationRequest(CampaignDraftPreviewRequest):
    confirmationToken: str = Field(min_length=20, max_length=8_000)
    idempotencyKey: str = Field(min_length=8, max_length=128)


class CampaignDraftValidation(StrictModel):
    schema_valid: Literal[True] = True
    policy_valid: Literal[True] = True
    warnings: list[str] = Field(default_factory=list, max_length=10)


class CampaignDraftArtifact(StrictModel):
    type: Literal["campaign_draft"] = "campaign_draft"
    data_source: Literal["ai_generated"] = "ai_generated"
    objective: str = Field(min_length=10, max_length=2_000)
    referencesUsed: list[CampaignReferenceCitation] = Field(max_length=3)
    draft: CampaignDraft
    validation: CampaignDraftValidation
    requires_adviser_review: Literal[True] = True
    created: Literal[False] = False

    @model_validator(mode="after")
    def reject_duplicate_citations(self):
        citations = [
            (citation.referenceId, citation.version) for citation in self.referencesUsed
        ]
        if len(citations) != len(set(citations)):
            raise ValueError("referencesUsed must not contain duplicates")
        return self


class CampaignDraftRevisionArtifact(StrictModel):
    type: Literal["campaign_draft_revision"] = "campaign_draft_revision"
    data_source: Literal["ai_generated"] = "ai_generated"
    objective: str = Field(min_length=10, max_length=2_000)
    referencesUsed: list[CampaignReferenceCitation] = Field(max_length=3)
    draft: CampaignDraft
    previousRevision: int = Field(ge=1, strict=True)
    revision: int = Field(ge=2, strict=True)
    changedFields: list[CampaignDraftField] = Field(min_length=1, max_length=7)
    validation: CampaignDraftValidation
    requires_adviser_review: Literal[True] = True
    created: Literal[False] = False

    @model_validator(mode="after")
    def validate_revision_artifact(self):
        if self.revision != self.previousRevision + 1:
            raise ValueError("revision must advance exactly once")
        if len(self.changedFields) != len(set(self.changedFields)):
            raise ValueError("changedFields must not contain duplicates")
        citations = [
            (citation.referenceId, citation.version) for citation in self.referencesUsed
        ]
        if len(citations) != len(set(citations)):
            raise ValueError("referencesUsed must not contain duplicates")
        return self


class PersistedCampaignDraftArtifact(StrictModel):
    """Canonical adviser/session-scoped draft returned by the chat API."""

    type: Literal["campaign_draft"] = "campaign_draft"
    data_source: Literal["ai_generated"] = "ai_generated"
    draftId: str = Field(pattern=r"^[a-f0-9-]{36}$", min_length=36, max_length=36)
    objective: str = Field(min_length=10, max_length=2_000)
    referencesUsed: list[CampaignReferenceCitation] = Field(max_length=3)
    draft: CampaignDraft
    revision: int = Field(ge=1, strict=True)
    status: CampaignDraftStatus
    changedFields: list[CampaignDraftField] = Field(default_factory=list, max_length=7)
    validation: CampaignDraftValidation
    requires_adviser_review: Literal[True] = True
    created: Literal[False] = False

    @model_validator(mode="after")
    def reject_duplicate_metadata(self):
        if len(self.changedFields) != len(set(self.changedFields)):
            raise ValueError("changedFields must not contain duplicates")
        citations = [
            (citation.referenceId, citation.version) for citation in self.referencesUsed
        ]
        if len(citations) != len(set(citations)):
            raise ValueError("referencesUsed must not contain duplicates")
        return self


class CampaignTurnDecision(StrictModel):
    """Strict, non-authoritative interpretation of a turn with an active draft."""

    action: CampaignTurnAction
    fields: list[CampaignDraftField] = Field(default_factory=list, max_length=7)
    optionNumber: int | None = Field(default=None, ge=1, le=10, strict=True)

    @model_validator(mode="after")
    def validate_action_shape(self):
        if len(self.fields) != len(set(self.fields)):
            raise ValueError("fields must not contain duplicates")
        if self.action in {"revise_fields", "suggest_field_options"}:
            if not self.fields:
                raise ValueError("the selected action requires at least one field")
        elif self.fields:
            raise ValueError("the selected action does not accept fields")
        if self.action == "select_field_option":
            if self.optionNumber is None:
                raise ValueError("optionNumber is required when selecting an option")
        elif self.optionNumber is not None:
            raise ValueError("optionNumber is only valid when selecting an option")
        return self


class CampaignDraftOptionProposal(StrictModel):
    """Unpersisted structured options generated for one current draft field."""

    type: Literal["campaign_draft_option_proposal"] = "campaign_draft_option_proposal"
    field: CampaignDraftField
    options: list[str] = Field(min_length=2, max_length=10)
    baseRevision: int = Field(ge=1, strict=True)
    created: Literal[False] = False

    @model_validator(mode="after")
    def validate_options(self):
        if self.field in {"ageGroups", "genders", "cashBands"}:
            raise ValueError("criteria dimensions do not support free-text option sets")
        normalized = [option.casefold() for option in self.options]
        if any(not option for option in normalized):
            raise ValueError("options must not be empty")
        if len(normalized) != len(set(normalized)):
            raise ValueError("options must be unique")
        limits = {
            "name": 255,
            "description": 10_000,
            "clientMessage": 10_000,
            "targetDemographicSummary": 1_000,
        }
        if any(len(option) > limits[self.field] for option in self.options):
            raise ValueError("an option exceeds the selected field's length limit")
        return self


class PersistedCampaignDraftOptionSet(StrictModel):
    """Scoped, revision-bound choices that can be selected in a later turn."""

    type: Literal["campaign_draft_options"] = "campaign_draft_options"
    optionSetId: str = Field(pattern=r"^[a-f0-9-]{36}$", min_length=36, max_length=36)
    draftId: str = Field(pattern=r"^[a-f0-9-]{36}$", min_length=36, max_length=36)
    baseRevision: int = Field(ge=1, strict=True)
    field: CampaignDraftField
    options: list[str] = Field(min_length=2, max_length=10)
    status: Literal["pending", "selected", "stale", "expired"]
    expiresAt: datetime
    created: Literal[False] = False

    @model_validator(mode="after")
    def validate_persisted_options(self):
        if self.field in {"ageGroups", "genders", "cashBands"}:
            raise ValueError("criteria dimensions do not support free-text option sets")
        normalized = [option.casefold() for option in self.options]
        if any(not option for option in normalized):
            raise ValueError("options must not be empty")
        if len(normalized) != len(set(normalized)):
            raise ValueError("options must be unique")
        limits = {
            "name": 255,
            "description": 10_000,
            "clientMessage": 10_000,
            "targetDemographicSummary": 1_000,
        }
        if any(len(option) > limits[self.field] for option in self.options):
            raise ValueError("an option exceeds the selected field's length limit")
        return self


class CampaignDraftPreview(StrictModel):
    draftId: str = Field(min_length=1, max_length=128)
    revision: int = Field(ge=1, strict=True)
    contentHash: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirmationToken: str = Field(min_length=20, max_length=8_000)
    expiresAt: str = Field(min_length=1, max_length=64)
    draft: CampaignDraft
