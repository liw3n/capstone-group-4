"""Deterministic policy validation for generated campaign drafts."""
from __future__ import annotations

import re

from app.campaigns.models import (
    CampaignDraft,
    CampaignDraftValidation,
    CampaignReference,
)


class CampaignDraftPolicyError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        field: str | None = None,
        rule: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.field = field
        self.rule = rule


_EDUCATIONAL_MARKERS = (
    "educational", "general information", "information only", "for education",
)
_REVIEW_MARKERS = (
    "individual circumstances", "personal circumstances", "individual review",
    "adviser review", "advisor review", "suitability",
)
_ADVICE_MARKERS = (
    "not financial advice", "does not constitute financial advice",
)
_STANDARD_REVIEW_NOTICE = (
    "This content is educational and does not constitute financial advice. "
    "Any next step requires an individual fact-find and suitability assessment "
    "with an adviser."
)
_UNSUPPORTED_CLAIM_RULES = (
    ("guarantee_claim", re.compile(r"\bguarantee(?:d|s)?\b", re.IGNORECASE), True),
    ("risk_free_claim", re.compile(r"\brisk[ -]?free\b", re.IGNORECASE), True),
    (
        "regulatory_approval_claim",
        re.compile(r"\b(?:mas|regulator|government)[ -]?approved\b", re.IGNORECASE),
        True,
    ),
    (
        "regulatory_approval_claim",
        re.compile(r"\bregulatory approval\b", re.IGNORECASE),
        True,
    ),
    (
        "superlative_product_claim",
        re.compile(
            r"\b(?:best|highest-returning|sure-win) (?:product|policy|fund|investment)\b",
            re.IGNORECASE,
        ),
        True,
    ),
    ("percentage_claim", re.compile(
        r"\b\d+(?:\.\d+)?\s*%\s*(?:annual\s+)?(?:return|yield|interest|growth|premium|fee)\b",
        re.IGNORECASE,
    ), False),
    ("percentage_claim", re.compile(
        r"\b(?:return|yield|interest|growth|premium|fee)\s+(?:of\s+)?\d+(?:\.\d+)?\s*%",
        re.IGNORECASE,
    ), False),
    ("currency_claim", re.compile(
        r"\b(?:return|yield|premium|fee|payout)\s+(?:of\s+|starts?\s+(?:from|at)\s+)?"
        r"(?:sgd|\$)\s*\d[\d,]*(?:\.\d+)?\b",
        re.IGNORECASE,
    ), False),
    ("currency_claim", re.compile(
        r"(?:sgd|\$)\s*\d[\d,]*(?:\.\d+)?\s*"
        r"(?:return|yield|premium|fee|payout)\b",
        re.IGNORECASE,
    ), False),
)
_AUTOMATION_PATTERNS = (
    re.compile(r"\b(?:automatically|immediately)\s+(?:send|publish|activate|launch|create)\b",
               re.IGNORECASE),
    re.compile(r"\bsend\s+(?:this|the)\s+(?:message|campaign)\s+now\b", re.IGNORECASE),
    re.compile(
        r"\bwithout\s+(?:adviser|advisor|human)\s+(?:review|approval|confirmation)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bno\s+(?:adviser|advisor|human)\s+(?:review|approval|confirmation)\s+(?:is\s+)?required\b",
        re.IGNORECASE,
    ),
)
_PERSONAL_DATA_PATTERNS = (
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(r"\b[STFGM]\d{7}[A-Z]\b", re.IGNORECASE),
    re.compile(r"(?<!\d)(?:\+?65[ -]?)?[689]\d{3}[ -]?\d{4}(?!\d)"),
    re.compile(r"\baccount\s+(?:number|no\.?|id)\s*[:#-]?\s*[A-Z0-9-]{5,}\b",
               re.IGNORECASE),
    re.compile(r"\bdear\s+(?:mr|mrs|ms|mdm|dr)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b"),
    re.compile(r"\bdear\s+(?!client\b|customer\b)[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b"),
    re.compile(
        r"\bclient(?:'s)?\s+(?:name\s+is|named)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b"
    ),
)
_NO_GENDER_RESTRICTION = (
    "all genders", "any gender", "regardless of gender", "not gender-specific",
    "not gender specific", "no gender restriction",
)
_NO_AGE_RESTRICTION = (
    "all ages", "any age", "regardless of age", "no age restriction",
    "not age-specific", "not age specific",
)
_NO_CASH_RESTRICTION = (
    "all cash", "any cash", "regardless of cash", "no cash restriction",
    "no cash threshold", "not limited to a cash band",
)
_AGE_BAND_PATTERNS = {
    "under35": re.compile(r"\b(?:under|below)\s*35\b", re.IGNORECASE),
    "35to44": re.compile(r"\b35\s*(?:to|-)\s*44\b", re.IGNORECASE),
    "45to54": re.compile(r"\b45\s*(?:to|-)\s*54\b", re.IGNORECASE),
    "55to64": re.compile(r"\b55\s*(?:to|-)\s*64\b", re.IGNORECASE),
    "65plus": re.compile(r"\b65\s*(?:\+|plus|and above|or older)\b", re.IGNORECASE),
}
_CASH_BAND_PATTERNS = {
    "under50k": re.compile(r"\b(?:under|below)\s*(?:sgd\s*)?50(?:,?000|k)\b", re.IGNORECASE),
    "50kTo250k": re.compile(
        r"\b(?:sgd\s*)?50(?:,?000|k)\s*(?:to|-)\s*(?:sgd\s*)?250(?:,?000|k)\b",
        re.IGNORECASE,
    ),
    "250kTo1m": re.compile(
        r"\b(?:sgd\s*)?250(?:,?000|k)\s*(?:to|-)\s*(?:sgd\s*)?1(?:,?000,?000|m)\b",
        re.IGNORECASE,
    ),
    "above1m": re.compile(
        r"\b(?:above|over)\s*(?:sgd\s*)?1(?:,?000,?000|m)\b", re.IGNORECASE
    ),
}
_COMPOSITE_AGE_PATTERNS = (
    (re.compile(r"\b(?:under|below)\s*45\b", re.IGNORECASE), {"under35", "35to44"}),
    (re.compile(r"\b45\s*(?:to|-)\s*64\b", re.IGNORECASE), {"45to54", "55to64"}),
    (
        re.compile(r"\b55\s*(?:\+|plus|and above|or older)\b", re.IGNORECASE),
        {"55to64", "65plus"},
    ),
)
_COMPOSITE_CASH_PATTERNS = (
    (
        re.compile(r"\b(?:under|below)\s*(?:sgd\s*)?250(?:,?000|k)\b", re.IGNORECASE),
        {"under50k", "50kTo250k"},
    ),
    (
        re.compile(
            r"\b(?:sgd\s*)?250(?:,?000|k)\s*(?:\+|and above|or more)\b",
            re.IGNORECASE,
        ),
        {"250kTo1m", "above1m"},
    ),
)


def _contains_any(value: str, markers: tuple[str, ...]) -> bool:
    normalized = value.casefold()
    return any(marker in normalized for marker in markers)


def _draft_text_fields(draft: CampaignDraft) -> list[tuple[str, str]]:
    return [
        ("name", draft.name),
        ("description", draft.description),
        ("clientMessage", draft.clientMessage),
        ("targetDemographicSummary", draft.targetDemographicSummary),
        *((f"rationale.{key}", value) for key, value in draft.rationale.items()),
        *((f"assumptions[{index}]", value) for index, value in enumerate(draft.assumptions)),
        ("disclaimer", draft.disclaimer),
    ]


def _claim_is_negated(text: str, start: int, end: int) -> bool:
    before = text[max(0, start - 80):start]
    after = text[end:min(len(text), end + 50)]
    if re.search(r"\b(?:not\s+only|no\s+doubt)\b[^.!?;:]*$", before, re.IGNORECASE):
        return False
    preceding_negation = re.search(
        r"(?:\bno\b|\bnot\b|\bnever\b|\bwithout\b|\bdoes\s+not\b|"
        r"\bdo\s+not\b|\bcannot\b|\bcan't\b|\bisn't\b|\baren't\b)"
        r"(?:\W+\w+){0,4}\W*$",
        before,
        re.IGNORECASE,
    )
    following_negation = re.match(
        r"(?:\W+\w+){0,3}\W+(?:is|are|will|can|does|do)\s+not\b",
        after,
        re.IGNORECASE,
    )
    return preceding_negation is not None or following_negation is not None


def _contains_affirmative_phrase(text: str, phrase: str) -> bool:
    pattern = re.compile(re.escape(phrase), re.IGNORECASE)
    return any(
        not _claim_is_negated(text, match.start(), match.end())
        for match in pattern.finditer(text)
    )


def _validate_disclaimer(draft: CampaignDraft) -> None:
    for field_name, value in (
        ("disclaimer", draft.disclaimer),
        ("client message", draft.clientMessage),
    ):
        if not _has_required_review_language(value):
            raise CampaignDraftPolicyError(
                "missing_disclaimer",
                f"The {field_name} must state that the content is educational, is not "
                "financial advice and requires individual review",
            )


def _has_required_review_language(value: str) -> bool:
    return (
        _contains_any(value, _EDUCATIONAL_MARKERS)
        and _contains_any(value, _REVIEW_MARKERS)
        and _contains_any(value, _ADVICE_MARKERS)
    )


def add_required_review_language(
    draft: CampaignDraft,
) -> tuple[CampaignDraft, list[str]]:
    """Append the standard review notice when generated copy omits it."""
    updates: dict[str, str] = {}
    warnings: list[str] = []
    for field_name in ("clientMessage", "disclaimer"):
        value = getattr(draft, field_name)
        if not _has_required_review_language(value):
            updates[field_name] = f"{value.rstrip()}\n\n{_STANDARD_REVIEW_NOTICE}"
            warnings.append(
                f"Standard review language was added to {field_name} and requires adviser review."
            )
    if not updates:
        return draft, warnings
    return CampaignDraft.model_validate({**draft.model_dump(), **updates}), warnings


def _explicit_bands(text: str, patterns: dict[str, re.Pattern]) -> set[str]:
    return {band for band, pattern in patterns.items() if pattern.search(text)}


def _validate_targeting(draft: CampaignDraft) -> list[str]:
    warnings: list[str] = []
    criteria = draft.criteria
    gender_summary = draft.targetDemographicSummary
    gender_rationale = draft.rationale["genders"]
    gender_text = f"{gender_summary} {gender_rationale}"
    age_text = f"{draft.targetDemographicSummary} {draft.rationale['ageGroups']}"
    cash_text = f"{draft.targetDemographicSummary} {draft.rationale['cashBands']}"
    def mentioned_genders(value: str) -> set[str]:
        mentions = set()
        if re.search(r"\b(?:female|women|woman)\b", value, re.IGNORECASE):
            mentions.add("female")
        if re.search(r"\b(?:male|men|man)\b", value, re.IGNORECASE):
            mentions.add("male")
        return mentions

    summary_gender_mentions = mentioned_genders(gender_summary)
    rationale_gender_mentions = mentioned_genders(gender_rationale)
    gender_mentions = summary_gender_mentions | rationale_gender_mentions
    no_gender_restriction = _contains_any(gender_text, _NO_GENDER_RESTRICTION)
    if not criteria.genders:
        if summary_gender_mentions or (rationale_gender_mentions and not no_gender_restriction):
            raise CampaignDraftPolicyError(
                "inconsistent_targeting",
                "Gender targeting text contradicts the unrestricted gender criteria",
            )
    elif no_gender_restriction and set(criteria.genders) != {"male", "female"}:
        raise CampaignDraftPolicyError(
            "inconsistent_targeting",
            "Gender rationale says unrestricted but the criteria are restricted",
        )
    elif gender_mentions - set(criteria.genders):
        raise CampaignDraftPolicyError(
            "inconsistent_targeting",
            "Gender targeting text mentions a group outside the structured criteria",
        )
    elif not gender_mentions and len(criteria.genders) == 1:
        warnings.append("The gender restriction needs a clearer field-level rationale.")

    explicit_age_bands = _explicit_bands(age_text, _AGE_BAND_PATTERNS)
    if explicit_age_bands - set(criteria.ageGroups):
        raise CampaignDraftPolicyError(
            "inconsistent_targeting",
            "Age targeting text mentions a band outside the structured criteria",
        )
    for pattern, expected_bands in _COMPOSITE_AGE_PATTERNS:
        if pattern.search(age_text) and set(criteria.ageGroups) != expected_bands:
            raise CampaignDraftPolicyError(
                "inconsistent_targeting",
                "Age targeting text does not match the structured criteria",
            )
    if criteria.ageGroups and _contains_any(age_text, _NO_AGE_RESTRICTION):
        raise CampaignDraftPolicyError(
            "inconsistent_targeting",
            "Age rationale says unrestricted but the criteria are restricted",
        )
    if not criteria.ageGroups and not _contains_any(age_text, _NO_AGE_RESTRICTION):
        warnings.append("The absence of an age restriction needs adviser confirmation.")

    explicit_cash_bands = _explicit_bands(cash_text, _CASH_BAND_PATTERNS)
    if explicit_cash_bands - set(criteria.cashBands):
        raise CampaignDraftPolicyError(
            "inconsistent_targeting",
            "Cash targeting text mentions a band outside the structured criteria",
        )
    for pattern, expected_bands in _COMPOSITE_CASH_PATTERNS:
        if pattern.search(cash_text) and set(criteria.cashBands) != expected_bands:
            raise CampaignDraftPolicyError(
                "inconsistent_targeting",
                "Cash targeting text does not match the structured criteria",
            )
    if criteria.cashBands and _contains_any(cash_text, _NO_CASH_RESTRICTION):
        raise CampaignDraftPolicyError(
            "inconsistent_targeting",
            "Cash rationale says unrestricted but the criteria are restricted",
        )
    if not criteria.cashBands and not _contains_any(cash_text, _NO_CASH_RESTRICTION):
        warnings.append("The absence of a cash-band restriction needs adviser confirmation.")

    return warnings


def _objective_warnings(objective: str, draft: CampaignDraft) -> list[str]:
    objective_normalized = objective.casefold()
    warnings: list[str] = []
    if re.search(r"\bhigh[ -]?value\b", objective_normalized) and not re.search(
        r"(?:sgd|\$)\s*\d|\d+(?:,\d{3})+|\d+\s*(?:k|m)\b", objective_normalized
    ):
        warnings.append("The objective uses 'high-value' without defining a threshold.")

    if draft.criteria.genders:
        supported_gender_terms = {
            "female": ("female", "women", "woman"),
            "male": ("male", "men", "man"),
        }
        if not any(
            term in objective_normalized
            for gender in draft.criteria.genders
            for term in supported_gender_terms[gender]
        ):
            warnings.append("The objective does not explicitly support the gender restriction.")
    if draft.criteria.ageGroups and not re.search(
        r"\b(?:age|aged|young|younger|older|senior|retire|retirement|career)\w*\b",
        objective_normalized,
    ):
        warnings.append("The objective does not explicitly support the age restriction.")
    if draft.criteria.cashBands and not re.search(
        r"\b(?:cash|asset|wealth|liquid|afford|savings|income|portfolio|fund)\w*\b",
        objective_normalized,
    ):
        warnings.append("The objective does not explicitly support the cash-band restriction.")
    if draft.assumptions:
        warnings.append(
            f"The draft contains {len(draft.assumptions)} assumption(s) requiring adviser review."
        )
    return warnings


def validate_campaign_draft_policy(
    objective: str,
    draft: CampaignDraft,
    references: list[CampaignReference],
) -> CampaignDraftValidation:
    text_fields = _draft_text_fields(draft)
    text = "\n".join(value for _, value in text_fields)
    for field, value in text_fields:
        for rule, pattern, allow_negation in _UNSUPPORTED_CLAIM_RULES:
            matches = pattern.finditer(value)
            if any(
                not allow_negation
                or not _claim_is_negated(value, match.start(), match.end())
                for match in matches
            ):
                raise CampaignDraftPolicyError(
                    "unsupported_claim",
                    "The draft contains an unsupported financial or regulatory claim",
                    field=field,
                    rule=rule,
                )
    for reference in references:
        for prohibited_claim in reference.prohibitedClaims:
            for field, value in text_fields:
                if _contains_affirmative_phrase(value, prohibited_claim):
                    raise CampaignDraftPolicyError(
                        "unsupported_claim",
                        "The draft contains a claim prohibited by a cited reference",
                        field=field,
                        rule="catalogue_prohibited_claim",
                    )
    if any(pattern.search(text) for pattern in _AUTOMATION_PATTERNS):
        raise CampaignDraftPolicyError(
            "unsupported_claim",
            "The draft attempts to bypass adviser review or automate a consequential action",
        )
    if any(pattern.search(text) for pattern in _PERSONAL_DATA_PATTERNS):
        raise CampaignDraftPolicyError(
            "invalid_draft",
            "The draft must not contain client identifiers or personal contact data",
        )

    _validate_disclaimer(draft)
    warnings = _validate_targeting(draft)
    warnings.extend(_objective_warnings(objective, draft))
    return CampaignDraftValidation(warnings=list(dict.fromkeys(warnings))[:10])
