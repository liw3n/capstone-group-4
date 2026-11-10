"""Evaluate the campaign-generation pipeline on shared synthetic datasets.

The evaluator measures three dimensions in one run:

* tool-call accuracy: initial generation retrieves references before preparing
  a draft, while selective review requests call ``revise_campaign_draft`` with
  exactly the intended fields and authoritative current revision;
* response accuracy: generated and revised artifacts are valid, review-only,
  preserve authoritative fields and never create a campaign row;
* response time: end-to-end, model-provider and per-tool durations.

From the repository root::

    terraform -chdir=backend/terraform destroy -auto-approve
    make eval DATASET=small
    make eval-run EVAL=campaign_generation

Use ``ARGS="--dataset large --repeats 5"`` for the large dataset. Results are
written under ``backend/evaluation/results/`` (git-ignored).
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
import importlib.util
import json
from pathlib import Path
import statistics
import sys
import time
from typing import Any

import psycopg
from psycopg.rows import dict_row


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.campaigns.models import (  # noqa: E402
    CAMPAIGN_TARGETING_FIELDS,
    CampaignDraftArtifact,
    CampaignDraftRevisionArtifact,
    PersistedCampaignDraftArtifact,
    campaign_revision_changed_fields,
)
from app.campaigns.repository import RequestScope  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.llm import ChatOrchestrator, LLMClient  # noqa: E402
from app.tools.mcp_registry import MCPToolRegistry  # noqa: E402


EVAL_FA_ID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
SCOPE = RequestScope(EVAL_FA_ID)
RESULTS_DIR = Path(__file__).resolve().parent / "results"
GENERATION_TOOLS = ("find_campaign_references", "prepare_campaign_draft")
REVISION_TOOLS = ("revise_campaign_draft",)


@dataclass(frozen=True)
class DatasetSpec:
    name: str
    campaigns: int
    contacts: int
    campaign_members: int


DATASETS = {
    "small": DatasetSpec("small", campaigns=5, contacts=20, campaign_members=66),
    "large": DatasetSpec(
        "large", campaigns=100, contacts=10_000, campaign_members=25_000
    ),
}


@dataclass(frozen=True)
class GenerationCase:
    case_id: str
    prompt: str
    age_groups: tuple[str, ...]
    genders: tuple[str, ...]
    cash_bands: tuple[str, ...]
    start_date: date
    end_date: date


@dataclass(frozen=True)
class RevisionCase:
    case_id: str
    prompt: str
    expected_fields: tuple[str, ...]
    must_change_fields: tuple[str, ...] = ()
    expected_name: str | None = None
    age_groups: tuple[str, ...] | None = None
    genders: tuple[str, ...] | None = None
    cash_bands: tuple[str, ...] | None = None


GENERATION_CASES = (
    GenerationCase(
        "generation-01-retirement",
        "Could you create a campaign to help clients aged 55-64 prepare for "
        "retirement? Keep it educational, include every gender and cash level, "
        "and schedule it from 2026-12-01 through 2027-01-31.",
        ("55to64",), (), (), date(2026, 12, 1), date(2027, 1, 31),
    ),
    GenerationCase(
        "generation-02-education",
        "Design a campaign for this brief:\nFocus: education savings.\nAudience: "
        "female clients, ages 35-44, cash below SGD 50,000.\nDates: "
        "2027-02-01 to 2027-03-31.",
        ("35to44",), ("female",), ("under50k",),
        date(2027, 2, 1), date(2027, 3, 31),
    ),
    GenerationCase(
        "generation-03-legacy",
        "Draft a campaign for legacy and estate planning — men, 65+, above SGD "
        "1m in cash. Use 2027-04-01 to 2027-05-31.",
        ("65plus",), ("male",), ("above1m",),
        date(2027, 4, 1), date(2027, 5, 31),
    ),
    GenerationCase(
        "generation-04-safe-defaults",
        "Build an educational investing campaign for early-career clients. Use "
        "safe defaults for targeting. It should run between 2027-06-01 and "
        "2027-07-31.",
        (), (), (),
        date(2027, 6, 1), date(2027, 7, 31),
    ),
    GenerationCase(
        "generation-05-financial-planning",
        "From 2027-08-01 to 2027-09-30, run a campaign targeting clients with "
        "SGD 250,000-1,000,000 in cash. Make it a general financial-planning "
        "introduction for clients of all ages and any gender.",
        (), (), ("250kTo1m",), date(2027, 8, 1), date(2027, 9, 30),
    ),
)


REVISION_CASES = (
    RevisionCase(
        "revision-01-rename",
        "Change the campaign name to Retirement Compass 2027.",
        ("name",),
        expected_name="Retirement Compass 2027",
    ),
    RevisionCase(
        "revision-02-tone-and-length",
        "Keep the targeting, but rewrite the campaign description and client "
        "message in a warmer, more concise tone.",
        ("description", "clientMessage"),
        must_change_fields=("description", "clientMessage"),
    ),
    RevisionCase(
        "revision-03-targeting",
        "Update the age targeting to 65+ and the cash threshold to SGD 250k "
        "and above.",
        ("ageGroups", "cashBands", "description", "clientMessage"),
        age_groups=("65plus",),
        cash_bands=("250kTo1m", "above1m"),
    ),
    RevisionCase(
        "revision-04-gender",
        "Adjust the gender targeting to female clients and keep everything else "
        "consistent.",
        ("genders", "description", "clientMessage"),
        genders=("female",),
    ),
)


EvaluationCase = GenerationCase | RevisionCase


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    seconds: float
    result: dict[str, Any]


@dataclass
class CaseResult:
    case_id: str
    workflow: str
    run: int
    prompt: str
    expected_tools: list[str]
    actual_tools: list[str]
    tool_arguments_correct: bool
    tool_accuracy: bool
    response_accuracy: bool
    response_failures: list[str]
    end_to_end_seconds: float
    llm_seconds: float
    llm_calls: int
    reference_tool_seconds: float | None
    preparation_tool_seconds: float | None
    revision_tool_seconds: float | None
    answer_preview: str
    error: str | None = None


class RecordingRegistry:
    """Delegate to FastMCP while recording arguments, results and durations."""

    def __init__(self, inner: Any, calls: list[ToolCall]) -> None:
        self._inner = inner
        self._calls = calls

    def bind_scope(self, *args: Any, **kwargs: Any) -> "RecordingRegistry":
        return RecordingRegistry(self._inner.bind_scope(*args, **kwargs), self._calls)

    def execute(self, name: str, arguments_json: str) -> str:
        started = time.perf_counter()
        result = self._inner.execute(name, arguments_json)
        elapsed = time.perf_counter() - started
        try:
            arguments = json.loads(arguments_json)
        except (TypeError, json.JSONDecodeError):
            arguments = {"_raw": str(arguments_json)}
        try:
            payload = json.loads(result)
        except (TypeError, json.JSONDecodeError):
            payload = {"_raw": str(result)[:500]}
        if not isinstance(arguments, dict):
            arguments = {"_raw": arguments}
        if not isinstance(payload, dict):
            payload = {"_raw": payload}
        self._calls.append(ToolCall(name, arguments, elapsed, payload))
        return result

    def __getattr__(self, attribute: str) -> Any:
        return getattr(self._inner, attribute)


class TimedLLMClient:
    """Delegate to the configured model provider while recording total time."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.seconds = 0.0
        self.calls = 0

    def create_chat_completion(self, *args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        try:
            return self._inner.create_chat_completion(*args, **kwargs)
        finally:
            self.seconds += time.perf_counter() - started
            self.calls += 1

    def create_structured_completion(self, *args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        try:
            return self._inner.create_structured_completion(*args, **kwargs)
        finally:
            self.seconds += time.perf_counter() - started
            self.calls += 1

    def __getattr__(self, attribute: str) -> Any:
        return getattr(self._inner, attribute)


def _in_process_mcp_server() -> Any:
    spec = importlib.util.spec_from_file_location(
        "pulse_campaign_generation_evaluation_mcp", BACKEND_DIR / "mcp" / "server.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the FastMCP server")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.mcp


def _connection() -> psycopg.Connection:
    database_url = get_settings().database_url
    if not database_url:
        raise SystemExit("DATABASE_URL is not configured in backend/.env")
    return psycopg.connect(database_url, row_factory=dict_row, connect_timeout=5)


def _loaded_counts() -> dict[str, int]:
    with _connection() as connection:
        row = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM campaign
                WHERE tenant_id = %(fa)s AND is_deleted = FALSE) AS campaigns,
              (SELECT count(*) FROM contact
                WHERE tenant_id = %(fa)s AND is_deleted = FALSE) AS contacts,
              (SELECT count(*) FROM campaign_member
                WHERE tenant_id = %(fa)s AND is_deleted = FALSE) AS campaign_members
            """,
            {"fa": EVAL_FA_ID},
        ).fetchone()
    return {key: int(row[key]) for key in ("campaigns", "contacts", "campaign_members")}


def _resolve_dataset(requested: str | None) -> DatasetSpec:
    actual = _loaded_counts()
    for spec in DATASETS.values():
        expected = {
            "campaigns": spec.campaigns,
            "contacts": spec.contacts,
            "campaign_members": spec.campaign_members,
        }
        if actual == expected:
            if requested is not None and requested != spec.name:
                break
            return spec
    expectation = requested or "small|large"
    raise SystemExit(
        f"Expected the {expectation} evaluation dataset but found {actual}.\n"
        f"Run terraform destroy, then make eval DATASET={expectation}."
    )


def _campaign_count() -> int:
    with _connection() as connection:
        row = connection.execute(
            "SELECT count(*) AS count FROM campaign WHERE tenant_id = %s",
            (EVAL_FA_ID,),
        ).fetchone()
    return int(row["count"])


def _baseline_draft() -> PersistedCampaignDraftArtifact:
    """Return a validated review draft used as revision-case setup."""
    return PersistedCampaignDraftArtifact.model_validate({
        "type": "campaign_draft",
        "data_source": "ai_generated",
        "objective": "Encourage clients nearing retirement to review their assets",
        "referencesUsed": [
            {"referenceId": "campaign-pattern-retirement-001", "version": 1}
        ],
        "draft": {
            "name": "Retirement Asset Review",
            "description": "Invite clients to review how their assets are organised.",
            "clientMessage": (
                "This educational invitation is not financial advice. Any next "
                "step requires an individual suitability review."
            ),
            "criteria": {
                "ageGroups": ["55to64"],
                "genders": [],
                "cashBands": ["50kTo250k", "250kTo1m"],
            },
            "targetDemographicSummary": (
                "Clients aged 55 to 64 nearing retirement across all genders."
            ),
            "rationale": {
                "ageGroups": "The retirement transition supports ages 55 to 64.",
                "genders": "No gender restriction is set; all genders are included.",
                "cashBands": (
                    "The selected SGD 50k to SGD 1m cash bands support a review."
                ),
            },
            "assumptions": ["Retirement timing must be confirmed."],
            "disclaimer": (
                "Educational information only, not financial advice; suitability "
                "depends on individual circumstances and adviser review."
            ),
        },
        "validation": {
            "schema_valid": True,
            "policy_valid": True,
            "warnings": ["The assumption requires adviser review."],
        },
        "requires_adviser_review": True,
        "created": False,
        "draftId": "11111111-1111-4111-8111-111111111111",
        "creation": {
            "startDate": "2026-11-10",
            "endDate": "2027-01-31",
            "audienceSource": "contacts",
        },
        "revision": 1,
        "status": "generated",
        "changedFields": [],
    })


def _expected_tools(case: EvaluationCase) -> tuple[str, ...]:
    return GENERATION_TOOLS if isinstance(case, GenerationCase) else REVISION_TOOLS


def _generation_arguments_correct(
    case: GenerationCase, calls: list[ToolCall]
) -> bool:
    if tuple(call.name for call in calls) != GENERATION_TOOLS:
        return False
    retrieval, preparation = calls
    if set(retrieval.arguments) != {"objective", "limit"}:
        return False
    objective = retrieval.arguments.get("objective")
    if not isinstance(objective, str) or not objective.startswith(case.prompt):
        return False
    if retrieval.arguments.get("limit") != 3:
        return False
    references = retrieval.result.get("references")
    if not isinstance(references, list):
        return False
    available = {
        (item.get("referenceId"), item.get("version"))
        for item in references if isinstance(item, dict)
    }
    citations = preparation.arguments.get("referencesUsed")
    draft = preparation.arguments.get("draft")
    if not isinstance(citations, list) or not isinstance(draft, dict):
        return False
    used = {
        (item.get("referenceId"), item.get("version"))
        for item in citations if isinstance(item, dict)
    }
    criteria = draft.get("criteria")
    return (
        set(preparation.arguments) == {"referencesUsed", "draft"}
        and used <= available
        and isinstance(criteria, dict)
        and criteria.get("ageGroups") == list(case.age_groups)
        and criteria.get("genders") == list(case.genders)
        and criteria.get("cashBands") == list(case.cash_bands)
    )


def _revision_arguments_correct(
    case: RevisionCase,
    current: PersistedCampaignDraftArtifact,
    calls: list[ToolCall],
) -> bool:
    if tuple(call.name for call in calls) != REVISION_TOOLS:
        return False
    arguments = calls[0].arguments
    required = {
        "objective", "referencesUsed", "currentDraft", "proposedChanges",
        "fields", "instruction", "revision",
    }
    if set(arguments) != required:
        return False
    if arguments.get("objective") != current.objective:
        return False
    if arguments.get("referencesUsed") != [
        item.model_dump(mode="json") for item in current.referencesUsed
    ]:
        return False
    if arguments.get("currentDraft") != current.draft.model_dump(mode="json"):
        return False
    if arguments.get("revision") != current.revision:
        return False
    if arguments.get("instruction") != case.prompt:
        return False
    if tuple(arguments.get("fields", ())) != case.expected_fields:
        return False
    changes = arguments.get("proposedChanges")
    if not isinstance(changes, dict) or set(changes) != set(case.expected_fields):
        return False
    if case.expected_name is not None and changes.get("name") != case.expected_name:
        return False
    expected_criteria = {
        "ageGroups": case.age_groups,
        "genders": case.genders,
        "cashBands": case.cash_bands,
    }
    for field_name, expected in expected_criteria.items():
        if expected is not None and changes.get(field_name) != list(expected):
            return False
    return True


def _tool_arguments_correct(
    case: EvaluationCase,
    current: PersistedCampaignDraftArtifact | None,
    calls: list[ToolCall],
) -> bool:
    if isinstance(case, GenerationCase):
        return _generation_arguments_correct(case, calls)
    return current is not None and _revision_arguments_correct(case, current, calls)


def _generation_response_failures(
    case: GenerationCase,
    result: Any,
    calls: list[ToolCall],
    campaigns_before: int,
    campaigns_after: int,
) -> list[str]:
    failures: list[str] = []
    if campaigns_after != campaigns_before:
        failures.append("generation changed the campaign row count")
    artifacts = tuple(getattr(result, "artifacts", ()))
    if len(artifacts) != 1 or not isinstance(artifacts[0], CampaignDraftArtifact):
        return failures + ["response did not contain one validated campaign draft"]
    artifact = artifacts[0]
    creation = getattr(result, "creation", None)
    criteria = artifact.draft.criteria
    if artifact.created is not False or artifact.requires_adviser_review is not True:
        failures.append("artifact is not explicitly review-only and uncreated")
    if artifact.data_source != "ai_generated":
        failures.append("artifact data source is not ai_generated")
    if not artifact.validation.schema_valid or not artifact.validation.policy_valid:
        failures.append("artifact did not pass schema and policy validation")
    if tuple(criteria.ageGroups) != case.age_groups:
        failures.append("age criteria do not match the adviser request")
    if tuple(criteria.genders) != case.genders:
        failures.append("gender criteria do not match the adviser request")
    if tuple(criteria.cashBands) != case.cash_bands:
        failures.append("cash criteria do not match the adviser request")
    if creation is None:
        failures.append("response omitted server-owned creation metadata")
    elif creation.startDate != case.start_date or creation.endDate != case.end_date:
        failures.append("campaign schedule does not match the adviser request")
    retrieval_refs = set()
    if calls and isinstance(calls[0].result.get("references"), list):
        retrieval_refs = {
            (item.get("referenceId"), item.get("version"))
            for item in calls[0].result["references"] if isinstance(item, dict)
        }
    artifact_refs = {
        (item.referenceId, item.version) for item in artifact.referencesUsed
    }
    if not artifact_refs <= retrieval_refs:
        failures.append("artifact cites a reference not returned by retrieval")
    answer = str(result)
    for required in (
        "## Draft campaign",
        "Draft only — not created",
        "Adviser review is required",
        artifact.draft.name,
        artifact.draft.disclaimer,
    ):
        if required not in answer:
            failures.append(f"rendered response is missing {required!r}")
    return failures


def _draft_field(draft: Any, field_name: str) -> Any:
    if field_name in CAMPAIGN_TARGETING_FIELDS:
        return getattr(draft.criteria, field_name)
    return getattr(draft, field_name)


def _revision_response_failures(
    case: RevisionCase,
    current: PersistedCampaignDraftArtifact,
    result: Any,
    campaigns_before: int,
    campaigns_after: int,
) -> list[str]:
    failures: list[str] = []
    if campaigns_after != campaigns_before:
        failures.append("revision changed the campaign row count")
    artifacts = tuple(getattr(result, "artifacts", ()))
    if len(artifacts) != 1 or not isinstance(
        artifacts[0], CampaignDraftRevisionArtifact
    ):
        return failures + ["response did not contain one validated draft revision"]
    artifact = artifacts[0]
    if artifact.previousRevision != current.revision:
        failures.append("revision did not use the authoritative current revision")
    if artifact.revision != current.revision + 1:
        failures.append("revision number did not increment exactly once")
    expected_changed = campaign_revision_changed_fields(case.expected_fields)
    if tuple(artifact.changedFields) != expected_changed:
        failures.append("changedFields does not match the selected revision fields")
    if artifact.created is not False or artifact.requires_adviser_review is not True:
        failures.append("revision is not explicitly review-only and uncreated")
    if not artifact.validation.schema_valid or not artifact.validation.policy_valid:
        failures.append("revision did not pass schema and policy validation")
    if case.expected_name is not None and artifact.draft.name != case.expected_name:
        failures.append("revised campaign name does not match the instruction")
    expected_criteria = {
        "ageGroups": case.age_groups,
        "genders": case.genders,
        "cashBands": case.cash_bands,
    }
    for field_name, expected in expected_criteria.items():
        if expected is not None and tuple(
            getattr(artifact.draft.criteria, field_name)
        ) != expected:
            failures.append(f"revised {field_name} do not match the instruction")
    for field_name in (
        "name", "description", "clientMessage", "ageGroups", "genders",
        "cashBands", "targetDemographicSummary",
    ):
        if field_name not in expected_changed and _draft_field(
            artifact.draft, field_name
        ) != _draft_field(current.draft, field_name):
            failures.append(f"unselected field {field_name} was changed")
    for field_name in case.must_change_fields:
        if _draft_field(
            artifact.draft, field_name
        ) == _draft_field(current.draft, field_name):
            failures.append(f"selected field {field_name} was not revised")
    answer = str(result)
    for required in (
        "## Draft campaign",
        "Draft only — not created",
        f"Revision {artifact.revision}",
    ):
        if required not in answer:
            failures.append(f"rendered revision is missing {required!r}")
    return failures


def _response_failures(
    case: EvaluationCase,
    current: PersistedCampaignDraftArtifact | None,
    result: Any,
    calls: list[ToolCall],
    campaigns_before: int,
    campaigns_after: int,
) -> list[str]:
    if isinstance(case, GenerationCase):
        return _generation_response_failures(
            case, result, calls, campaigns_before, campaigns_after
        )
    if current is None:
        return ["revision case setup did not supply an active draft"]
    return _revision_response_failures(
        case, current, result, campaigns_before, campaigns_after
    )


def _tool_time(calls: list[ToolCall], name: str) -> float | None:
    values = [call.seconds for call in calls if call.name == name]
    return round(sum(values), 3) if values else None


def _run_case(
    case: EvaluationCase, run: int, settings: Any, transport: Any
) -> CaseResult:
    calls: list[ToolCall] = []
    client = TimedLLMClient(LLMClient(settings))
    orchestrator = ChatOrchestrator(
        client, settings, RecordingRegistry(MCPToolRegistry(transport), calls)
    )
    current = _baseline_draft() if isinstance(case, RevisionCase) else None
    campaigns_before = _campaign_count()
    started = time.perf_counter()
    result: Any = None
    error: str | None = None
    try:
        result = orchestrator.run(
            case.prompt,
            [],
            scope=SCOPE,
            session_id=f"generation-eval-{case.case_id}-{run}",
            current_draft=current,
            revision_context_checked=True,
        )
    except Exception as exc:  # retain provider/tool failures as observations
        error = f"{type(exc).__name__}: {exc}"
    elapsed = time.perf_counter() - started
    campaigns_after = _campaign_count()
    expected_tools = _expected_tools(case)
    arguments_correct = error is None and _tool_arguments_correct(
        case, current, calls
    )
    tool_accuracy = (
        error is None
        and tuple(call.name for call in calls) == expected_tools
        and arguments_correct
    )
    failures = [error] if error else _response_failures(
        case, current, result, calls, campaigns_before, campaigns_after
    )
    answer = "" if result is None else str(result)
    return CaseResult(
        case_id=case.case_id,
        workflow=("generation" if isinstance(case, GenerationCase) else "revision"),
        run=run,
        prompt=case.prompt,
        expected_tools=list(expected_tools),
        actual_tools=[call.name for call in calls],
        tool_arguments_correct=arguments_correct,
        tool_accuracy=tool_accuracy,
        response_accuracy=not failures,
        response_failures=[failure for failure in failures if failure],
        end_to_end_seconds=round(elapsed, 3),
        llm_seconds=round(client.seconds, 3),
        llm_calls=client.calls,
        reference_tool_seconds=_tool_time(calls, "find_campaign_references"),
        preparation_tool_seconds=_tool_time(calls, "prepare_campaign_draft"),
        revision_tool_seconds=_tool_time(calls, "revise_campaign_draft"),
        answer_preview=answer[:500],
        error=error,
    )


def _rate(results: list[CaseResult], attribute: str) -> float:
    passed = sum(bool(getattr(item, attribute)) for item in results)
    return round(passed / len(results), 3)


def _summary(results: list[CaseResult]) -> dict[str, Any]:
    summary = {
        "runs": len(results),
        "tool_accuracy": _rate(results, "tool_accuracy"),
        "response_accuracy": _rate(results, "response_accuracy"),
        "pass_rate": round(
            sum(item.tool_accuracy and item.response_accuracy for item in results)
            / len(results),
            3,
        ),
        "mean_response_seconds": round(
            statistics.mean(item.end_to_end_seconds for item in results), 3
        ),
        "mean_llm_seconds": round(
            statistics.mean(item.llm_seconds for item in results), 3
        ),
    }
    summary["by_workflow"] = {
        workflow: {
            "runs": len(selected),
            "tool_accuracy": _rate(selected, "tool_accuracy"),
            "response_accuracy": _rate(selected, "response_accuracy"),
            "mean_response_seconds": round(statistics.mean(
                item.end_to_end_seconds for item in selected
            ), 3),
        }
        for workflow in ("generation", "revision")
        if (selected := [item for item in results if item.workflow == workflow])
    }
    return summary


def _response_time(
    cases: list[EvaluationCase], results: list[CaseResult]
) -> dict[str, Any]:
    prompts = []
    for case in cases:
        runs = [item for item in results if item.case_id == case.case_id]
        prompts.append({
            "case_id": case.case_id,
            "runs": len(runs),
            "end_to_end_seconds": round(
                statistics.mean(item.end_to_end_seconds for item in runs), 3
            ),
            "llm_seconds": round(statistics.mean(item.llm_seconds for item in runs), 3),
            "reference_tool_seconds": round(statistics.mean(
                item.reference_tool_seconds or 0.0 for item in runs
            ), 3),
            "preparation_tool_seconds": round(statistics.mean(
                item.preparation_tool_seconds or 0.0 for item in runs
            ), 3),
            "revision_tool_seconds": round(statistics.mean(
                item.revision_tool_seconds or 0.0 for item in runs
            ), 3),
        })
    total = sum(item["end_to_end_seconds"] for item in prompts)
    return {
        "prompts": prompts,
        "prompt_count": len(prompts),
        "total_seconds": round(total, 3),
        "mean_seconds": round(total / len(prompts), 3),
    }


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate campaign generation/revision tool calls, responses and timing"
        )
    )
    parser.add_argument("--dataset", choices=sorted(DATASETS), default=None)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--mcp-url", default=None)
    parser.add_argument("--delay-seconds", type=float, default=5.0)
    parser.add_argument("--min-pass-rate", type=float, default=1.0)
    parser.add_argument("--case", action="append", default=None, metavar="CASE_ID")
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    if not 1 <= args.repeats <= 20:
        raise SystemExit("--repeats must be between 1 and 20")
    if args.delay_seconds < 0:
        raise SystemExit("--delay-seconds must not be negative")
    if not 0 <= args.min_pass_rate <= 1:
        raise SystemExit("--min-pass-rate must be between 0 and 1")
    settings = get_settings()
    if not settings.llm_configured:
        raise SystemExit("GROQ_API_KEY is not configured in backend/.env")
    dataset = _resolve_dataset(args.dataset)
    cases: list[EvaluationCase] = [*GENERATION_CASES, *REVISION_CASES]
    if args.case:
        known = {case.case_id for case in cases}
        unknown = sorted(set(args.case) - known)
        if unknown:
            raise SystemExit(f"Unknown case(s): {unknown}; available: {sorted(known)}")
        cases = [case for case in cases if case.case_id in args.case]

    print(
        f"Evaluating campaign generation and revision on {dataset.name}: "
        f"{len(cases)} prompts x {args.repeats} runs"
    )
    transport = args.mcp_url or _in_process_mcp_server()
    results: list[CaseResult] = []
    for case in cases:
        for run in range(1, args.repeats + 1):
            result = _run_case(case, run, settings, transport)
            results.append(result)
            passed = result.tool_accuracy and result.response_accuracy
            print(
                f"[{'PASS' if passed else 'FAIL'}] {case.case_id} run {run}: "
                f"tools={result.actual_tools} e2e={result.end_to_end_seconds:.3f}s "
                f"llm={result.llm_seconds:.3f}s"
                + (
                    f" failures={result.response_failures}"
                    if result.response_failures
                    else ""
                )
            )
            if args.delay_seconds:
                time.sleep(args.delay_seconds)

    summary = _summary(results)
    response_time = _response_time(cases, results)
    print("\nAccuracy summary")
    print(json.dumps(summary, indent=2))
    print("\nResponse time (seconds; dataset validation excluded)")
    print(
        f"  {'case':<42} {'end-to-end':>10} {'llm':>8} {'find':>8} "
        f"{'prepare':>8} {'revise':>8}"
    )
    for item in response_time["prompts"]:
        print(
            f"  {item['case_id']:<42} {item['end_to_end_seconds']:>10.3f} "
            f"{item['llm_seconds']:>8.3f} {item['reference_tool_seconds']:>8.3f} "
            f"{item['preparation_tool_seconds']:>8.3f} "
            f"{item['revision_tool_seconds']:>8.3f}"
        )
    print(f"  {'total':<42} {response_time['total_seconds']:>10.3f}")
    print(f"  {'mean':<42} {response_time['mean_seconds']:>10.3f}")

    RESULTS_DIR.mkdir(exist_ok=True)
    output = RESULTS_DIR / (
        f"campaign_generation_{dataset.name}_"
        f"{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.json"
    )
    output.write_text(
        json.dumps(
            {
                "data_source": "synthetic",
                "dataset": asdict(dataset),
                "model": settings.llm_model,
                "mcp_transport": args.mcp_url or "in-process",
                "cases": [asdict(case) for case in cases],
                "summary": summary,
                "response_time": response_time,
                "results": [asdict(result) for result in results],
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {output}")
    return 0 if summary["pass_rate"] >= args.min_pass_rate else 1


if __name__ == "__main__":
    raise SystemExit(main())
