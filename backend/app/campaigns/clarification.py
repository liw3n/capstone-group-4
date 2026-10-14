"""Durable, adviser-scoped clarification state for campaign generation."""

from contextlib import contextmanager
from dataclasses import dataclass
import re
from typing import Literal, Protocol
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app import config
from app.campaigns.repository import RequestScope
from app.store import StoreUnavailableError


CLARIFICATION_QUESTIONS = {
    "focus": (
        "What should the campaign primarily cover (for example budgeting and "
        "emergency savings, protection, investing, retirement, or a general "
        "financial-planning introduction)?"
    ),
    "audience": (
        "Who is the intended audience or life stage? You can also say all clients."
    ),
    "age": (
        "Which supported age group should be used: Under 35, 35–44, 45–54, "
        "55–64, 65+, or no age restriction?"
    ),
    "cash": (
        "Which supported cash band should that term mean: Below SGD 50,000, SGD "
        "50,000–250,000, SGD 250,000–1,000,000, above SGD 1,000,000, "
        "or no cash restriction?"
    ),
}

_FOCUS_PATTERN = re.compile(
    r"\b(?:budget|emergency|saving|protection|insurance|invest|wealth|retire|"
    r"education|legacy|estate|property|home|cpf|srs|financial health|"
    r"general financial planning|financial foundation)\w*\b"
)
_AUDIENCE_PATTERN = re.compile(
    r"\b(?:client|people|adult|student|graduate|professional|employee|worker|"
    r"family|families|parent|couple|business owner|all clients)\w*\b"
)
_AMBIGUOUS_AGE_PATTERN = re.compile(
    r"\b(?:student|graduate|entering (?:the )?workforce|early[ -]career|young|"
    r"younger|mid[ -]career|near(?:ing)? retirement|approaching retirement|"
    r"older|senior)\w*\b"
)
_SUPPORTED_AGE_PATTERN = re.compile(
    r"\b(?:under|below)\s*35\b|"
    r"\b(?:35\s*(?:to|[–-])\s*44|45\s*(?:to|[–-])\s*54|"
    r"55\s*(?:to|[–-])\s*64)\b|"
    r"\b65\s*(?:\+|and (?:above|over|older))|"
    r"\b(?:no age restriction|all ages)\b"
)
_NUMERIC_AGE_PATTERN = re.compile(
    r"\b(?:under|below|over|above|aged?|ages?)\s*\d{1,3}(?![\d,])|"
    r"\b\d{1,3}\s*(?:to|[–-])\s*\d{1,3}\b|\b\d{1,3}\s*\+"
)
_AMBIGUOUS_CASH_PATTERN = re.compile(
    r"\b(?:high[ -]value|affluent|wealthy|limited savings|low(?:er)? cash|"
    r"substantial cash)\b"
)
_SUPPORTED_CASH_PATTERN = re.compile(
    r"\b(?:below|under)\s*(?:sgd|\$)?\s*50(?:,?000|\s*k)\b|"
    r"\b50(?:,?000|\s*k)\s*(?:to|[–-])\s*250(?:,?000|\s*k)\b|"
    r"\b250(?:,?000|\s*k)\s*(?:to|[–-])\s*1(?:,?000,?000|\s*m)\b|"
    r"\b(?:above|over)\s*(?:sgd|\$)?\s*1(?:,?000,?000|\s*m)\b|"
    r"\b(?:no cash restriction|no cash threshold)\b"
)
_NUMERIC_CASH_PATTERN = re.compile(
    r"\b(?:below|under|above|over)\s*(?:(?:sgd|\$)\s*[\d,.]+\s*[km]?|"
    r"[\d,.]+\s*[km])\b|"
    r"\b[\d,.]+\s*[km]\s*(?:to|[–-])\s*[\d,.]+\s*[km]\b"
)
_EXPLICIT_GENDER_PATTERN = re.compile(
    r"\b(?:male|female|men|women|all genders|no gender restriction)\b"
)


@dataclass(frozen=True)
class CampaignTargetingLock:
    """Server-resolved criteria that draft generation cannot change."""

    age_groups: tuple[str, ...]
    genders: tuple[str, ...]
    cash_bands: tuple[str, ...]

    def as_payload(self) -> dict[str, list[str]]:
        return {
            "ageGroups": list(self.age_groups),
            "genders": list(self.genders),
            "cashBands": list(self.cash_bands),
        }


@dataclass(frozen=True)
class CampaignObjectiveAssessment:
    canonical_objective: str
    question_ids: tuple[str, ...]
    targeting_lock: CampaignTargetingLock


class CampaignIntentExtraction(BaseModel):
    """Untrusted model interpretation; server policy still decides readiness."""

    model_config = ConfigDict(extra="forbid")

    planningFocus: Literal[
        "unspecified",
        "budgeting_and_emergency_savings",
        "protection",
        "investing",
        "retirement",
        "education",
        "legacy_and_estate",
        "property",
        "cpf_and_srs",
        "general_financial_planning",
        "other",
    ]
    audienceSpecified: bool
    ageGroups: list[
        Literal["under35", "35to44", "45to54", "55to64", "65plus"]
    ] = Field(max_length=5)
    ageUnrestricted: bool
    unsupportedAgeCriterion: bool
    cashBands: list[
        Literal["below50k", "50kTo250k", "250kTo1m", "above1m"]
    ] = Field(max_length=4)
    cashUnrestricted: bool
    unsupportedCashCriterion: bool
    genders: list[Literal["male", "female"]] = Field(max_length=2)
    genderUnrestricted: bool

    @model_validator(mode="after")
    def validate_consistency(self):
        dimensions = (
            (self.ageGroups, self.ageUnrestricted),
            (self.cashBands, self.cashUnrestricted),
            (self.genders, self.genderUnrestricted),
        )
        if any(values and unrestricted for values, unrestricted in dimensions):
            raise ValueError("restricted and unrestricted intent cannot both be set")
        if any(len(values) != len(set(values)) for values, _ in dimensions):
            raise ValueError("intent values must be unique")
        return self


INTENT_EXTRACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "planningFocus": {
            "type": "string",
            "enum": [
                "unspecified", "budgeting_and_emergency_savings", "protection",
                "investing", "retirement", "education", "legacy_and_estate",
                "property", "cpf_and_srs", "general_financial_planning", "other",
            ],
        },
        "audienceSpecified": {"type": "boolean"},
        "ageGroups": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["under35", "35to44", "45to54", "55to64", "65plus"],
            },
        },
        "ageUnrestricted": {"type": "boolean"},
        "unsupportedAgeCriterion": {"type": "boolean"},
        "cashBands": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["below50k", "50kTo250k", "250kTo1m", "above1m"],
            },
        },
        "cashUnrestricted": {"type": "boolean"},
        "unsupportedCashCriterion": {"type": "boolean"},
        "genders": {
            "type": "array",
            "items": {"type": "string", "enum": ["male", "female"]},
        },
        "genderUnrestricted": {"type": "boolean"},
    },
    "required": [
        "planningFocus", "audienceSpecified", "ageGroups", "ageUnrestricted",
        "unsupportedAgeCriterion", "cashBands", "cashUnrestricted",
        "unsupportedCashCriterion", "genders", "genderUnrestricted",
    ],
}


_FOCUS_LABELS = {
    "budgeting_and_emergency_savings": "budgeting and emergency savings",
    "protection": "protection",
    "investing": "investing",
    "retirement": "retirement",
    "education": "education",
    "legacy_and_estate": "legacy and estate planning",
    "property": "property planning",
    "cpf_and_srs": "CPF and SRS planning",
    "general_financial_planning": "general financial planning",
    "other": "the other focus explicitly described by the adviser",
}


def _normalise_for_matching(value: str) -> str:
    return " ".join(re.sub(r"[^\w+$]+", " ", value.casefold()).split())


def _latest_explicit_dimension(
    values: tuple[str, ...], *patterns: re.Pattern[str]
) -> str | None:
    for value in reversed(values):
        if any(pattern.search(value) for pattern in patterns):
            return value
    return None


_AGE_VALUE_PATTERNS = (
    ("under35", re.compile(r"\b(?:under|below)\s*35\b")),
    ("35to44", re.compile(r"\b35\s*(?:to|[–-])\s*44\b")),
    ("45to54", re.compile(r"\b45\s*(?:to|[–-])\s*54\b")),
    ("55to64", re.compile(r"\b55\s*(?:to|[–-])\s*64\b")),
    ("65plus", re.compile(r"\b65\s*(?:\+|and (?:above|over|older))")),
)
_CASH_VALUE_PATTERNS = (
    (
        "under50k",
        re.compile(r"\b(?:below|under)\s*(?:sgd|\$)?\s*50(?:,?000|\s*k)\b"),
    ),
    (
        "50kTo250k",
        re.compile(r"\b50(?:,?000|\s*k)\s*(?:to|[–-])\s*250(?:,?000|\s*k)\b"),
    ),
    (
        "250kTo1m",
        re.compile(
            r"\b250(?:,?000|\s*k)\s*(?:to|[–-])\s*1(?:,?000,?000|\s*m)\b"
        ),
    ),
    (
        "above1m",
        re.compile(r"\b(?:above|over)\s*(?:sgd|\$)?\s*1(?:,?000,?000|\s*m)\b"),
    ),
)


def _matched_values(
    statement: str | None, patterns: tuple[tuple[str, re.Pattern[str]], ...]
) -> tuple[str, ...]:
    if statement is None:
        return ()
    return tuple(value for value, pattern in patterns if pattern.search(statement))


def _targeting_lock(
    statements: tuple[str, ...],
    explicit_age: str | None,
    explicit_cash: str | None,
) -> CampaignTargetingLock:
    explicit_gender = _latest_explicit_dimension(statements, _EXPLICIT_GENDER_PATTERN)
    genders: tuple[str, ...] = ()
    if explicit_gender is not None and not re.search(
        r"\b(?:all genders|no gender restriction)\b", explicit_gender
    ):
        genders = tuple(
            gender
            for gender, pattern in (
                ("male", re.compile(r"\b(?:male|men|man)\b")),
                ("female", re.compile(r"\b(?:female|women|woman)\b")),
            )
            if pattern.search(explicit_gender)
        )
    return CampaignTargetingLock(
        age_groups=_matched_values(explicit_age, _AGE_VALUE_PATTERNS),
        genders=genders,
        cash_bands=_matched_values(explicit_cash, _CASH_VALUE_PATTERNS),
    )


def assess_campaign_objective(
    objective: str,
    answers: tuple[str, ...] = (),
    extracted: CampaignIntentExtraction | None = None,
) -> CampaignObjectiveAssessment:
    statements = tuple(value.casefold() for value in (objective, *answers))
    combined = " ".join(statements)
    normalised = _normalise_for_matching(combined)
    use_defaults = bool(
        re.search(r"\buse (?:safe )?defaults?\b", combined)
    )
    unrestricted_targeting = use_defaults or bool(
        re.search(r"\b(?:no (?:targeting )?restrictions?|all clients)\b", combined)
    )
    question_ids: list[str] = []
    raw_focus = bool(_FOCUS_PATTERN.search(normalised))
    extracted_focus = extracted is not None and extracted.planningFocus != "unspecified"
    if not (raw_focus or extracted_focus or use_defaults):
        question_ids.append("focus")
    if not (
        _AUDIENCE_PATTERN.search(normalised)
        or raw_focus
        or (extracted is not None and extracted.audienceSpecified)
        or extracted_focus
        or unrestricted_targeting
    ):
        question_ids.append("audience")

    explicit_age = _latest_explicit_dimension(
        statements, _SUPPORTED_AGE_PATTERN, _NUMERIC_AGE_PATTERN
    )
    if explicit_age is not None:
        supported_age = bool(_SUPPORTED_AGE_PATTERN.search(explicit_age))
        unsupported_age = bool(
            _NUMERIC_AGE_PATTERN.search(explicit_age) and not supported_age
        )
    else:
        supported_age = False
        unsupported_age = bool(
            extracted is not None and extracted.unsupportedAgeCriterion
        ) or bool(
            extracted is not None
            and extracted.ageGroups
            and _AMBIGUOUS_AGE_PATTERN.search(combined)
        )
    if (
        (_AMBIGUOUS_AGE_PATTERN.search(combined) and not supported_age)
        or unsupported_age
    ) and not unrestricted_targeting:
        question_ids.append("age")

    explicit_cash = _latest_explicit_dimension(
        statements, _SUPPORTED_CASH_PATTERN, _NUMERIC_CASH_PATTERN
    )
    if explicit_cash is not None:
        supported_cash = bool(_SUPPORTED_CASH_PATTERN.search(explicit_cash))
        unsupported_cash = bool(
            _NUMERIC_CASH_PATTERN.search(explicit_cash) and not supported_cash
        )
    else:
        supported_cash = False
        unsupported_cash = bool(
            extracted is not None and extracted.unsupportedCashCriterion
        ) or bool(
            extracted is not None
            and extracted.cashBands
            and _AMBIGUOUS_CASH_PATTERN.search(combined)
        )
    if (
        (_AMBIGUOUS_CASH_PATTERN.search(combined) and not supported_cash)
        or unsupported_cash
    ) and not unrestricted_targeting:
        question_ids.append("cash")

    clarification = ""
    if answers:
        clarification = "\nClarifications from the adviser:\n" + "\n".join(
            f"- {answer}" for answer in answers
        )
    interpreted = []
    if extracted_focus and not raw_focus:
        interpreted.append(
            f"Planning focus: {_FOCUS_LABELS[extracted.planningFocus]}."
        )
    defaults = []
    if not supported_age:
        defaults.append("Age targeting: no age restriction.")
    if not (
        _EXPLICIT_GENDER_PATTERN.search(combined)
    ):
        defaults.append("Gender targeting: no gender restriction.")
    if not supported_cash:
        defaults.append("Cash targeting: no cash restriction.")
    canonical = objective + clarification
    if not question_ids:
        additions = interpreted + defaults
        if additions:
            canonical += "\nServer-validated campaign intent:\n" + "\n".join(
                f"- {item}" for item in additions
            )
    return CampaignObjectiveAssessment(
        canonical.strip(),
        tuple(question_ids[:3]),
        _targeting_lock(statements, explicit_age, explicit_cash),
    )


def render_campaign_clarification(question_ids: tuple[str, ...]) -> str:
    questions = "\n".join(
        f"{index}. {CLARIFICATION_QUESTIONS[question_id]}"
        for index, question_id in enumerate(question_ids, start=1)
    )
    return (
        "## A few details before I draft the campaign\n\n"
        f"{questions}\n\n"
        "Reply in one message, or say **use safe defaults**. You can also say "
        "**cancel campaign draft**.\n\n"
        "No campaign draft has been generated or created yet."
    )


def is_campaign_clarification_cancel(message: str) -> bool:
    return bool(
        re.search(
            r"\b(?:cancel|stop|discard|start over)\b.{0,30}\b(?:campaign|draft|this)\b|"
            r"^(?:cancel|stop|start over)[.! ]*$",
            message.casefold().strip(),
        )
    )


@dataclass(frozen=True)
class CampaignClarification:
    clarification_id: str
    objective: str
    answers: tuple[str, ...]
    pending_question_ids: tuple[str, ...]
    round_count: int


class CampaignClarificationStore(Protocol):
    def get_active(
        self, scope: RequestScope, session_id: str
    ) -> CampaignClarification | None: ...

    def start(
        self,
        scope: RequestScope,
        session_id: str,
        objective: str,
        pending_question_ids: tuple[str, ...],
    ) -> CampaignClarification: ...

    def update(
        self,
        scope: RequestScope,
        session_id: str,
        clarification_id: str,
        answers: tuple[str, ...],
        pending_question_ids: tuple[str, ...],
        round_count: int,
        status: str = "active",
    ) -> None: ...


@contextmanager
def _connection():
    database_url = config.get_settings().database_url
    if not database_url:
        raise StoreUnavailableError("DATABASE_URL is not configured")
    try:
        with psycopg.connect(database_url, row_factory=dict_row) as connection:
            connection.execute("SET LOCAL statement_timeout = '5s'")
            yield connection
    except StoreUnavailableError:
        raise
    except psycopg.Error as exc:
        raise StoreUnavailableError(
            "campaign clarification storage is temporarily unavailable"
        ) from exc


def _from_row(row: dict) -> CampaignClarification:
    return CampaignClarification(
        clarification_id=row["clarification_id"],
        objective=row["objective"],
        answers=tuple(row["answers"]),
        pending_question_ids=tuple(row["pending_question_ids"]),
        round_count=row["round_count"],
    )


class PostgresCampaignClarificationStore:
    """Persist one active clarification flow per scoped chat session."""

    def get_active(
        self, scope: RequestScope, session_id: str
    ) -> CampaignClarification | None:
        with _connection() as connection:
            row = connection.execute(
                """
                SELECT clarification_id, objective, answers,
                       pending_question_ids, round_count
                FROM campaign_generation_clarifications
                WHERE tenant_id = %s AND fa_id = %s AND session_id = %s
                  AND status = 'active'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (scope.tenant_id, scope.fa_id, session_id),
            ).fetchone()
        return _from_row(row) if row else None

    def start(
        self,
        scope: RequestScope,
        session_id: str,
        objective: str,
        pending_question_ids: tuple[str, ...],
    ) -> CampaignClarification:
        clarification_id = str(uuid4())
        with _connection() as connection:
            connection.execute(
                """
                UPDATE campaign_generation_clarifications
                SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP
                WHERE tenant_id = %s AND fa_id = %s AND session_id = %s
                  AND status = 'active'
                """,
                (scope.tenant_id, scope.fa_id, session_id),
            )
            row = connection.execute(
                """
                INSERT INTO campaign_generation_clarifications
                    (clarification_id, tenant_id, fa_id, session_id, objective,
                     pending_question_ids)
                SELECT %s, %s, %s, sessions.session_id, %s, %s
                FROM campaign_chat_sessions AS sessions
                WHERE sessions.session_id = %s AND sessions.fa_id = %s
                RETURNING clarification_id, objective, answers,
                          pending_question_ids, round_count
                """,
                (
                    clarification_id,
                    scope.tenant_id,
                    scope.fa_id,
                    objective,
                    list(pending_question_ids),
                    session_id,
                    scope.fa_id,
                ),
            ).fetchone()
            if row is None:
                raise StoreUnavailableError(
                    "campaign clarification session is unavailable"
                )
        return _from_row(row)

    def update(
        self,
        scope: RequestScope,
        session_id: str,
        clarification_id: str,
        answers: tuple[str, ...],
        pending_question_ids: tuple[str, ...],
        round_count: int,
        status: str = "active",
    ) -> None:
        with _connection() as connection:
            result = connection.execute(
                """
                UPDATE campaign_generation_clarifications
                SET answers = %s, pending_question_ids = %s,
                    round_count = %s, status = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE clarification_id = %s AND tenant_id = %s AND fa_id = %s
                  AND session_id = %s AND status = 'active'
                """,
                (
                    Jsonb(list(answers)),
                    list(pending_question_ids),
                    round_count,
                    status,
                    clarification_id,
                    scope.tenant_id,
                    scope.fa_id,
                    session_id,
                ),
            )
            if result.rowcount != 1:
                raise StoreUnavailableError(
                    "campaign clarification is no longer active"
                )
