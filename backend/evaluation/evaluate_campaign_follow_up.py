"""Evaluations for the campaign_follow_up MCP tool.

Runs adviser prompts through the real ChatOrchestrator, LLM provider and
FastMCP server against a seeded evaluation database, then scores whether
campaign_follow_up was called with the right campaign and limit and returned
the ground-truth unreplied clients (Tool Calling Accuracy), and records each
prompt's response time with the total and mean (Response Time).

Datasets (synthetic, tables/eval_data/):
  small  5 campaigns, 20 contacts, 66 campaign members
  large  100 campaigns, 10,000 contacts, 25,000 campaign members

Reset the local database to one dataset, then run from the repository root:

    terraform -chdir=backend/terraform destroy
    make eval DATASET=small        # or DATASET=large
    make eval-run EVAL=campaign_follow_up    # ARGS="--case small-1-scoped-default"

The loaded dataset is detected from row counts; --dataset small|large makes the
expectation explicit. Other options: --repeats N, --min-pass-rate 0.8,
--mcp-url http://127.0.0.1:8001/mcp, --case CASE_ID (repeatable). Results are written to
evaluation/results/ (git-ignored).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.campaigns.repository import RequestScope  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.llm import ChatOrchestrator, LLMClient  # noqa: E402
from app.store import _connection  # noqa: E402
from app.tools.mcp_registry import MCPToolRegistry  # noqa: E402

EVAL_FA_ID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
TOOL_NAME = "campaign_follow_up"
RESULTS_DIR = Path(__file__).resolve().parent / "results"


#=========================#
# Tool Calling Accuracy   #
#=========================#


@dataclass(frozen=True)
class DatasetSpec:
    name: str
    campaigns: int
    contacts: int
    campaign_members: int


@dataclass(frozen=True)
class PromptCase:
    case_id: str
    prompt: str
    # Campaign the chat is scoped to (opened from the Campaigns workspace), or
    # None for the general PULSE chat where the adviser names the campaign.
    scoped_campaign: str | None
    # Campaign whose unreplied clients the tool should return.
    expected_campaign: str
    # Limit the model should pass; None means any limit is acceptable.
    expected_limit: int | None = None
    note: str = ""


DATASETS = {
    "small": DatasetSpec(name="small", campaigns=5, contacts=20, campaign_members=66),
    "large": DatasetSpec(name="large", campaigns=100, contacts=10_000,
                         campaign_members=25_000),
}

# The same five prompts run on both datasets: two in a chat scoped to a
# campaign, two in the general chat naming the campaign, and one scoped chat
# that names a different (out-of-scope) campaign. campaign_follow_up documents
# that a server-bound campaign scope overrides the campaign argument, so scope
# must win there. The five named campaigns exist in both datasets; in the large
# one they sit among generated near-match names such as "Retirement Income Wave 012".
PROMPT_CASES = [
    PromptCase(
        case_id="1-scoped-default",
        prompt="Which clients should I follow up with for this campaign?",
        scoped_campaign="Legacy Protection Refresh",
        expected_campaign="Legacy Protection Refresh",
    ),
    PromptCase(
        case_id="2-scoped-limit",
        prompt="Who still hasn't replied to my emails? Give me the top 3 to chase.",
        scoped_campaign="Retirement Income Review",
        expected_campaign="Retirement Income Review",
        expected_limit=3,
    ),
    PromptCase(
        case_id="3-unscoped-named",
        prompt=("Which clients from the Young Families Cover Check campaign "
                "haven't responded yet?"),
        scoped_campaign=None,
        expected_campaign="Young Families Cover Check",
    ),
    PromptCase(
        case_id="4-unscoped-limit",
        prompt=("I emailed clients about Education Savings Kickstart a few weeks ago. "
                "Recommend 2 people I should follow up with."),
        scoped_campaign=None,
        expected_campaign="Education Savings Kickstart",
        expected_limit=2,
    ),
    PromptCase(
        case_id="5-scoped-names-other-campaign",
        prompt=("For the Year-End Portfolio Health Check campaign, "
                "who should I follow up with?"),
        scoped_campaign="Legacy Protection Refresh",
        expected_campaign="Legacy Protection Refresh",
        note="Out-of-scope campaign named inside a scoped chat; scope must win.",
    ),
]

# Case IDs carry the dataset prefix (e.g. small-1-scoped-default) so results
# and --case name the dataset they ran on.
CASES = {
    name: [replace(case, case_id=f"{name}-{case.case_id}") for case in PROMPT_CASES]
    for name in DATASETS
}


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    seconds: float
    result: dict[str, Any]


@dataclass
class CaseResult:
    case_id: str
    run: int
    scope: str
    prompt: str
    tool_called: bool = False
    wrong_tool_called: bool = False
    campaign_correct: bool = False
    limit_correct: bool = False
    result_correct: bool = False
    passed: bool = False
    end_to_end_seconds: float = 0.0
    llm_seconds: float = 0.0
    llm_calls: int = 0
    follow_up_tool_seconds: float | None = None
    tool_sequence: list[str] = field(default_factory=list)
    follow_up_arguments: dict[str, Any] | None = None
    expected_unreplied: int = 0
    returned_unreplied: int | None = None
    error: str | None = None
    answer_preview: str = ""


class _RecordingRegistry:
    """Delegates to a bound MCPToolRegistry while timing every tool call."""

    def __init__(self, inner: Any, calls: list[ToolCall]) -> None:
        self._inner = inner
        self._calls = calls

    def bind_scope(self, *args: Any, **kwargs: Any) -> "_RecordingRegistry":
        return _RecordingRegistry(self._inner.bind_scope(*args, **kwargs), self._calls)

    def execute(self, name: str, arguments_json: str) -> str:
        started = time.perf_counter()
        result = self._inner.execute(name, arguments_json)
        elapsed = time.perf_counter() - started
        try:
            arguments = json.loads(arguments_json)
        except json.JSONDecodeError:
            arguments = {"_raw": arguments_json}
        try:
            payload = json.loads(result)
        except (TypeError, json.JSONDecodeError):
            payload = {"_raw": str(result)[:500]}
        self._calls.append(ToolCall(name, arguments, elapsed,
                                    payload if isinstance(payload, dict) else {"_raw": payload}))
        return result

    def __getattr__(self, attribute: str) -> Any:
        return getattr(self._inner, attribute)


class _TimedClient:
    """Delegates to the LLM client while timing chat completions."""

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
        "pulse_mcp_server", BACKEND_DIR / "mcp" / "server.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.mcp


def _loaded_counts() -> dict[str, int]:
    with _connection() as connection:
        counts = connection.execute(
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
    return {key: counts[key] for key in ("campaigns", "contacts", "campaign_members")}


def _expected_counts(spec: DatasetSpec) -> dict[str, int]:
    return {"campaigns": spec.campaigns, "contacts": spec.contacts,
            "campaign_members": spec.campaign_members}


def _resolve_dataset(requested: str | None) -> DatasetSpec:
    """Return the requested or detected dataset, failing if it is not loaded."""
    actual = _loaded_counts()
    if requested is None:
        for spec in DATASETS.values():
            if actual == _expected_counts(spec):
                return spec
        raise SystemExit(
            f"Database holds no evaluation dataset (found {actual}).\n"
            "Run: terraform -chdir=backend/terraform destroy, then "
            "make eval DATASET=small|large"
        )
    spec = DATASETS[requested]
    if actual != _expected_counts(spec):
        raise SystemExit(
            f"Database does not hold the {spec.name} evaluation dataset.\n"
            f"  expected {_expected_counts(spec)}\n  found    {actual}\n"
            "Run: terraform -chdir=backend/terraform destroy, then "
            f"make eval DATASET={spec.name}"
        )
    return spec


def _campaign_id(name: str) -> str:
    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT campaign_id::text AS campaign_id FROM campaign
            WHERE tenant_id = %s AND created_by_user_id = %s
              AND is_deleted = FALSE AND name = %s
            """,
            (EVAL_FA_ID, EVAL_FA_ID, name),
        ).fetchall()
    if len(rows) != 1:
        raise SystemExit(f"Expected one campaign named {name!r}, found {len(rows)}")
    return rows[0]["campaign_id"]


def _ground_truth(campaign_id: str) -> set[str]:
    """Contacts whose highest engagement status for the campaign is 0."""
    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT contact_id::text AS contact_id
            FROM campaign_member
            WHERE tenant_id = %s AND campaign_id = %s AND is_deleted = FALSE
            GROUP BY contact_id
            HAVING max(engagement_status) = 0
            """,
            (EVAL_FA_ID, campaign_id),
        ).fetchall()
    return {row["contact_id"] for row in rows}


def _score(case: PromptCase, run: int, calls: list[ToolCall], answer: str,
           elapsed: float, client: _TimedClient, expected_id: str,
           truth: set[str]) -> CaseResult:
    result = CaseResult(
        case_id=case.case_id, run=run,
        scope=f"scoped:{case.scoped_campaign}" if case.scoped_campaign else "unscoped",
        prompt=case.prompt, end_to_end_seconds=round(elapsed, 3),
        llm_seconds=round(client.seconds, 3), llm_calls=client.calls,
        tool_sequence=[call.name for call in calls], expected_unreplied=len(truth),
        answer_preview=answer[:400],
    )
    follow_ups = [call for call in calls if call.name == TOOL_NAME]
    result.tool_called = bool(follow_ups)
    # Pre-contact matching is the tool most easily confused with follow-up.
    result.wrong_tool_called = "recommend_clients_for_campaign" in result.tool_sequence
    if not follow_ups:
        return result

    successful = [call for call in follow_ups if "error_code" not in call.result]
    call = successful[-1] if successful else follow_ups[-1]
    result.follow_up_arguments = call.arguments
    result.follow_up_tool_seconds = round(sum(c.seconds for c in follow_ups), 3)
    if "error_code" in call.result:
        result.error = f"{call.result.get('error_code')}: {call.result.get('error')}"

    limit = call.arguments.get("limit", 5)
    result.limit_correct = case.expected_limit is None or limit == case.expected_limit
    returned_id = str((call.result.get("campaign_info") or {}).get("campaign_id", ""))
    result.campaign_correct = returned_id == expected_id
    returned = {str(candidate.get("client_id")) for candidate in call.result.get("candidates", [])}
    if "total_unreplied_clients" in call.result:
        result.returned_unreplied = call.result["total_unreplied_clients"]
    result.result_correct = result.campaign_correct and returned == truth
    result.passed = (result.tool_called and not result.wrong_tool_called
                     and result.campaign_correct and result.limit_correct
                     and result.result_correct)
    return result


def _summary(results: list[CaseResult]) -> dict[str, Any]:
    total = len(results)

    def rate(attribute: str) -> float:
        return round(sum(bool(getattr(r, attribute)) for r in results) / total, 3)

    return {
        "runs": total,
        "tool_selection_accuracy": rate("tool_called"),
        "wrong_tool_rate": rate("wrong_tool_called"),
        "campaign_accuracy": rate("campaign_correct"),
        "limit_accuracy": rate("limit_correct"),
        "result_accuracy": rate("result_correct"),
        "pass_rate": rate("passed"),
    }


#=========================#
# Response Time           #
#=========================#

def _response_time(cases: list[PromptCase], results: list[CaseResult]) -> dict[str, Any]:
    """Per-prompt response time for the same prompts, plus the total and mean.

    Each prompt's time is the average of its runs (one run unless --repeats is
    set). The mean is the total across prompts divided by the number of prompts.
    """
    prompts = []
    for case in cases:
        runs = [r for r in results if r.case_id == case.case_id]
        tool = [r.follow_up_tool_seconds for r in runs if r.follow_up_tool_seconds is not None]
        prompts.append({
            "case_id": case.case_id,
            "runs": len(runs),
            "end_to_end_seconds": round(statistics.mean(r.end_to_end_seconds for r in runs), 3),
            "llm_seconds": round(statistics.mean(r.llm_seconds for r in runs), 3),
            "follow_up_tool_seconds": round(statistics.mean(tool), 3) if tool else None,
        })
    total = sum(prompt["end_to_end_seconds"] for prompt in prompts)
    return {
        "prompts": prompts,
        "prompt_count": len(prompts),
        "total_seconds": round(total, 3),
        "mean_seconds": round(total / len(prompts), 3),
    }


def _print_response_time(response_time: dict[str, Any]) -> None:
    print("\nResponse time (seconds)")
    print(f"  {'case':<40} {'end-to-end':>10} {'llm':>8} {'tool':>8}")
    for prompt in response_time["prompts"]:
        tool = prompt["follow_up_tool_seconds"]
        print(f"  {prompt['case_id']:<40} {prompt['end_to_end_seconds']:>10.3f} "
              f"{prompt['llm_seconds']:>8.3f} {'-' if tool is None else f'{tool:.3f}':>8}")
    print(f"  {'total':<40} {response_time['total_seconds']:>10.3f}")
    print(f"  {'mean (total / ' + str(response_time['prompt_count']) + ')':<40} "
          f"{response_time['mean_seconds']:>10.3f}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=f"Evaluate {TOOL_NAME} tool-call accuracy and response time")
    parser.add_argument("--dataset", choices=sorted(DATASETS), default=None,
                        help="Expected dataset (default: detect from the loaded database)")
    parser.add_argument("--repeats", type=int, default=1,
                        help="Runs per prompt, to measure LLM variance (default 1)")
    parser.add_argument("--mcp-url", default=None,
                        help="Call a running FastMCP server (e.g. http://127.0.0.1:8001/mcp) "
                             "instead of loading mcp/server.py in-process")
    parser.add_argument("--min-pass-rate", type=float, default=1.0,
                        help="Exit non-zero below this pass rate (default 1.0)")
    parser.add_argument("--case", action="append", default=None, metavar="CASE_ID",
                        help="Run only this case ID (repeatable; default: all cases)")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.llm_configured:
        raise SystemExit("GROQ_API_KEY is not configured in backend/.env")
    spec = _resolve_dataset(args.dataset)
    cases = CASES[spec.name]
    if args.case:
        known = {case.case_id for case in cases}
        unknown = [case_id for case_id in args.case if case_id not in known]
        if unknown:
            raise SystemExit(f"Unknown case(s) for the {spec.name} dataset: {unknown}\n"
                             f"Available: {sorted(known)}")
        cases = [case for case in cases if case.case_id in args.case]
    print(f"Evaluating {TOOL_NAME} on the {spec.name} dataset ({len(cases)} prompts)")

    transport = args.mcp_url or _in_process_mcp_server()
    expectations = {}
    for case in cases:
        expected_id = _campaign_id(case.expected_campaign)
        scoped_id = _campaign_id(case.scoped_campaign) if case.scoped_campaign else None
        expectations[case.case_id] = (expected_id, scoped_id, _ground_truth(expected_id))

    scope = RequestScope(EVAL_FA_ID)
    results: list[CaseResult] = []
    for case in cases:
        expected_id, scoped_id, truth = expectations[case.case_id]
        for run in range(1, args.repeats + 1):
            calls: list[ToolCall] = []
            client = _TimedClient(LLMClient(settings))
            orchestrator = ChatOrchestrator(
                client, settings, _RecordingRegistry(MCPToolRegistry(transport), calls)
            )
            started = time.perf_counter()
            error = None
            try:
                answer = str(orchestrator.run(case.prompt, [], scope=scope, campaign_id=scoped_id))
            except Exception as exc:  # report provider/tool failures as failed runs
                answer, error = "", f"{type(exc).__name__}: {exc}"
            elapsed = time.perf_counter() - started
            result = _score(case, run, calls, answer, elapsed, client, expected_id, truth)
            result.error = error or result.error
            results.append(result)
            status = "PASS" if result.passed else "FAIL"
            print(f"[{status}] {case.case_id} run {run}: tools={result.tool_sequence} "
                  f"args={result.follow_up_arguments} unreplied="
                  f"{result.returned_unreplied}/{result.expected_unreplied} "
                  f"e2e={result.end_to_end_seconds}s tool={result.follow_up_tool_seconds}s"
                  + (f" error={result.error}" if result.error else ""))

    summary = _summary(results)
    print(json.dumps(summary, indent=2))
    response_time = _response_time(cases, results)
    _print_response_time(response_time)

    RESULTS_DIR.mkdir(exist_ok=True)
    output = RESULTS_DIR / f"tool_call_accuracy_{spec.name}_{datetime.now():%Y%m%d_%H%M%S}.json"
    output.write_text(json.dumps({
        "data_source": "synthetic",
        "dataset": asdict(spec),
        "model": settings.llm_model,
        "mcp_transport": args.mcp_url or "in-process",
        "cases": [asdict(case) for case in cases],
        "summary": summary,
        "response_time": response_time,
        "results": [asdict(result) for result in results],
    }, indent=2, default=str))
    print(f"Wrote {output}")
    return 0 if summary["pass_rate"] >= args.min_pass_rate else 1


if __name__ == "__main__":
    raise SystemExit(main())
