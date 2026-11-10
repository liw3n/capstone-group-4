"""Evaluate seven discovery/filter prompts on the synthetic small/large fixtures.

From the repository root, load one dataset at a time with make eval
DATASET=small|large, then make eval-run EVAL=get_active_campaigns
ARGS="--dataset small". Repeat after destroying/reprovisioning for large.
Uses the real LLM, in-process MCP protocol and a temporary local CRM HTTP API.
SQL ground truth is independent of the discovery handler. No CRM rows are changed.
Results (including complete answers) go to evaluation/results/ (git-ignored).
Prints per-run tool/argument/result/response scores, an accuracy summary and a
response-time table, then saves one JSON report like the other evaluators.
Default arguments and case-insensitive exact campaign names are normalized
before scoring. Use --show-answers to print complete chatbot replies.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
import json
import os
from pathlib import Path
import re
import socket
import statistics
import subprocess
import sys
import tempfile
import time

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import httpx
from app.campaigns.repository import RequestScope
from app.config import get_settings
from app.llm import ChatOrchestrator, LLMClient
from app.store import _connection
from app.tools.mcp_registry import MCPToolRegistry
from app.tools.discovery import ActiveCampaignArguments, AGE_LABELS, CASH_LABELS, DEFAULT_FIELDS
from pydantic import ValidationError
from evaluation.evaluate_campaign_follow_up import (
    DATASETS, EVAL_FA_ID, _RecordingRegistry, _TimedClient,
    _in_process_mcp_server, _resolve_dataset,
)

TOOL = "get_active_campaigns"
FIELDS = DEFAULT_FIELDS
FIELD_HEADERS = {
    "campaign_id": "Campaign ID", "name": "Campaign Name", "description": "Description",
    "start_date": "Start Date", "end_date": "End Date", "age_groups": "Age Group",
    "genders": "Genders", "cash_bands": "Cash Bands", "status": "Status",
    "age_min": "Age Min", "age_max": "Age Max", "cash_min": "Cash Min", "cash_max": "Cash Max",
}
RESULTS_DIR = Path(__file__).resolve().parent / "results"


@dataclass(frozen=True)
class PromptCase:
    case_id: str
    prompt: str
    name: str | None = None
    filters: dict = field(default_factory=dict)

    def expected_arguments(self):
        arguments = {"campaign_names": [self.name]} if self.name else {}
        if self.filters:
            arguments["filters"] = self.filters
        return arguments


PROMPTS = (
    PromptCase("1-all", "get active campaigns"),
    PromptCase("2-named", "get campaign details for legacy protection refresh",
               name="Legacy Protection Refresh"),
    PromptCase("3-gender", "Show active campaigns suitable for female clients.",
               filters={"genders": ["Female"]}),
    PromptCase("4-gender-age", "Show active campaigns suitable for female clients aged 35 to 44.",
               filters={"genders": ["Female"], "age_min": 35, "age_max": 44}),
    PromptCase("5-gender-age-cash", "Show active campaigns suitable for female clients aged 35 to 44 "
               "with cash of S$250,000 to below S$1,000,000.",
               filters={"genders": ["Female"], "age_min": 35, "age_max": 44,
                        "cash_min": 250000, "cash_max": 1000000, "cash_max_exclusive": True}),
    PromptCase("6-description", "Show active campaigns with ‘retirement’ in their description.",
               filters={"description_contains": "retirement"}),
    PromptCase("7-date", "Show active campaigns starting between 1 September 2026 and "
               "30 September 2026, inclusive.",
               filters={"start_date_from": "2026-09-01", "start_date_to": "2026-09-30"}),
)
CASES = {dataset: tuple(replace(case, case_id=f"{dataset}-{case.case_id}")
                        for case in PROMPTS) for dataset in DATASETS}


def fixture_matches(row: dict, case: PromptCase) -> bool:
    """Independent oracle for the seven prompts and the checked-in fixture bands.

    Empty audience restrictions mean any client. Age/cash match overlapping
    eligibility ranges, not containment. Does not call the application's matcher.
    """
    if case.name and row["name"].casefold() != case.name.casefold():
        return False
    criteria, filters = row["audience_criteria"], case.filters
    if criteria.get("ageRange") or criteria.get("cashRange"):
        raise ValueError("These fixture expectations cover band-based criteria only")
    genders = criteria.get("genders", [])
    if filters.get("genders") and genders and not (
        {v.casefold() for v in genders} & {v.casefold() for v in filters["genders"]}
    ):
        return False
    age_bands = {"under35": (0, 34), "35to44": (35, 44), "45to54": (45, 54),
                 "55to64": (55, 64), "65plus": (65, float("inf"))}
    if "age_min" in filters and criteria.get("ageGroups"):
        if not any(age_bands[b][0] <= filters["age_max"] and age_bands[b][1] >= filters["age_min"]
                   for b in criteria["ageGroups"]):
            return False
    cash_bands = {"under50k": (0, 50000), "50kTo250k": (50000, 250000),
                  "250kTo1m": (250000, 1000000), "above1m": (1000000, float("inf"))}
    if "cash_min" in filters and criteria.get("cashBands"):
        if not any(cash_bands[b][0] < filters["cash_max"] and cash_bands[b][1] > filters["cash_min"]
                   for b in criteria["cashBands"]):
            return False
    term = filters.get("description_contains")
    if term and term.casefold() not in (row["description"] or "").casefold():
        return False
    if "start_date_from" in filters:
        start = row["start_date"]
        if not start or not filters["start_date_from"] <= start.isoformat() <= filters["start_date_to"]:
            return False
    return True


def ground_truth(case: PromptCase) -> list[dict]:
    """Read creator-owned active rows directly, without calling application tools."""
    with _connection() as connection:
        rows = connection.execute(
            """SELECT campaign_id::text, name, description, start_date, end_date, status,
                      audience_criteria FROM campaign
               WHERE tenant_id = %s AND created_by_user_id = %s
                 AND is_deleted = FALSE AND status = 'active'
               ORDER BY campaign_id""",
            (EVAL_FA_ID, EVAL_FA_ID),
        ).fetchall()
    expected = []
    for row in rows:
        if not fixture_matches(row, case):
            continue
        criteria = row["audience_criteria"]
        expected.append(dict(
            campaign_id=row["campaign_id"], status=row["status"],
            name=row["name"], description=row["description"],
            start_date=row["start_date"].isoformat() if row["start_date"] else None,
            end_date=row["end_date"].isoformat() if row["end_date"] else None,
            age_groups=" or ".join(AGE_LABELS[b] for b in criteria.get("ageGroups", [])) or "Any",
            genders=", ".join(v.title() for v in criteria.get("genders", [])) or "Any",
            cash_bands=" or ".join(CASH_LABELS[b] for b in criteria.get("cashBands", [])) or "Any",
            age_min=None, age_max=None, cash_min=None, cash_max=None,
        ))
    return expected


def arguments_correct(case: PromptCase, arguments: dict, expected_count: int = 1) -> bool:
    try:
        query = ActiveCampaignArguments.model_validate(arguments)
    except ValidationError:
        return False
    names = [v.casefold() for v in query.campaign_names] if query.campaign_names is not None else None
    filters = query.filters.model_dump(mode="json", exclude_none=True, exclude_defaults=True) if query.filters else {}
    return (names == ([case.name.casefold()] if case.name else None)
            and query.campaign_ids is None
            and filters == case.filters and query.limit >= max(1, expected_count))


def result_correct(case: PromptCase, payload: dict, truth: list[dict]) -> bool:
    columns = payload.get("columns", [])
    if (not isinstance(columns, list) or "name" not in columns
            or any(key not in FIELD_HEADERS for key in columns)
            or len(set(columns)) != len(columns)
            or any(key not in row for row in truth for key in columns)):
        return False
    return (payload.get("data_source") == "synthetic"
            and not payload.get("error")
            and payload.get("rows") == [{key: row[key] for key in columns} for row in truth]
            and payload.get("total_count") == len(truth)
            and payload.get("returned_count") == len(truth)
            and payload.get("truncated") is False)


def response_correct(case: PromptCase, answer: str, truth: list[dict]) -> bool:
    # Parse visible table cells against SQL facts rather than the tool's table.
    table = [line.strip() for line in answer.splitlines() if line.strip().startswith("|")]
    cells = [[cell.strip() for cell in line.strip("|").split("|")] for line in table]
    if len(cells) < 2:
        return False
    reverse = {label: key for key, label in FIELD_HEADERS.items()}
    if "Campaign Name" not in cells[0] or any(header not in reverse for header in cells[0]):
        return False
    columns = [reverse[header] for header in cells[0]]
    if len(set(columns)) != len(columns) or any(key not in row for row in truth for key in columns):
        return False
    if not all(re.fullmatch(r":?-+:?", cell) for cell in cells[1]):
        return False
    expected = [[str(row[field]) if row[field] is not None else "Unknown" for field in columns] for row in truth]
    if cells[2:] != expected:
        return False
    if not truth and "no active campaigns" not in answer.lower():
        return False
    return "(Singapore)" in answer and "Download Excel" in answer


@contextmanager
def local_api():
    """Start the real read-only CRM API; clean it up even after failed runs."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    previous = os.environ.get("CAMPAIGN_API_BASE_URL")
    os.environ["CAMPAIGN_API_BASE_URL"] = url
    get_settings.cache_clear()
    with tempfile.TemporaryFile() as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
             "--port", str(port), "--no-access-log"], cwd=BACKEND_DIR,
            stdout=log, stderr=log,
        )
        try:
            with httpx.Client(trust_env=False, timeout=1) as client:
                for _ in range(100):
                    if process.poll() is not None:
                        raise RuntimeError("Evaluation CRM API failed to start")
                    try:
                        # A 401 also establishes readiness when demo auth is enabled.
                        if client.get(url + "/health").status_code in (200, 401):
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.1)
                else:
                    raise RuntimeError("Evaluation CRM API did not become ready")
            yield url
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            if previous is None:
                os.environ.pop("CAMPAIGN_API_BASE_URL", None)
            else:
                os.environ["CAMPAIGN_API_BASE_URL"] = previous
            get_settings.cache_clear()


def _summary(results: list[dict]) -> dict:
    def rate(key):
        return round(statistics.mean(bool(row[key]) for row in results), 3)

    return {
        "runs": len(results),
        "tool_selection_accuracy": rate("tool_selection_correct"),
        "argument_accuracy": rate("arguments_correct"),
        "tool_call_accuracy": round(statistics.mean(
            row["tool_selection_correct"] and row["arguments_correct"] for row in results
        ), 3),
        "tool_result_accuracy": rate("tool_result_correct"),
        "response_accuracy": rate("response_correct"),
        "pass_rate": rate("passed"),
    }


def _response_time(cases: tuple[PromptCase, ...], results: list[dict]) -> dict:
    """Mean time per prompt across repeats, with total/mean across prompts."""
    prompts = []
    for case in cases:
        runs = [row for row in results if row["case_id"] == case.case_id]
        tool_times = [row["discovery_tool_seconds"] for row in runs
                      if row["discovery_tool_seconds"] is not None]
        prompts.append({
            "case_id": case.case_id,
            "runs": len(runs),
            "end_to_end_seconds": round(statistics.mean(row["end_to_end_seconds"] for row in runs), 3),
            "llm_seconds": round(statistics.mean(row["llm_seconds"] for row in runs), 3),
            "discovery_tool_seconds": round(statistics.mean(tool_times), 3) if tool_times else None,
        })
    total = sum(row["end_to_end_seconds"] for row in prompts)
    return {
        "prompts": prompts, "prompt_count": len(prompts),
        "total_seconds": round(total, 3),
        "mean_seconds": round(total / len(prompts), 3),
    }


def _print_response_time(response_time: dict) -> None:
    print("\nResponse time (seconds)")
    print(f"  {'case':<40} {'end-to-end':>10} {'llm':>8} {'tool':>8}")
    for prompt in response_time["prompts"]:
        tool = prompt["discovery_tool_seconds"]
        print(f"  {prompt['case_id']:<40} {prompt['end_to_end_seconds']:>10.3f} "
              f"{prompt['llm_seconds']:>8.3f} {'-' if tool is None else f'{tool:.3f}':>8}")
    print(f"  {'total':<40} {response_time['total_seconds']:>10.3f}")
    print(f"  {'mean (total / ' + str(response_time['prompt_count']) + ')':<40} "
          f"{response_time['mean_seconds']:>10.3f}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=sorted(DATASETS))
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--min-pass-rate", type=float, default=1.0)
    parser.add_argument("--show-answers", action="store_true")
    parser.add_argument("--case", action="append", metavar="CASE_ID")
    parser.add_argument("--mcp-url", default=None)
    args = parser.parse_args()
    if args.repeats < 1 or not 0 <= args.min_pass_rate <= 1:
        parser.error("Use positive repeats and a pass rate between 0 and 1")
    spec = _resolve_dataset(args.dataset)
    cases = CASES[spec.name]
    if args.case:
        if set(args.case) - {case.case_id for case in cases}:
            parser.error("Unknown case ID for the loaded dataset")
        cases = tuple(case for case in cases if case.case_id in args.case)
    if not get_settings().llm_configured:
        raise SystemExit("Configure GROQ_API_KEY in backend/.env for live tool-selection evaluation")
    truth = {case.case_id: ground_truth(case) for case in cases}
    expected_active = {"small": 5, "large": 91}[spec.name]
    if len(ground_truth(PROMPTS[0])) != expected_active:
        raise SystemExit("Loaded campaigns differ from the expected synthetic fixtures")
    print(f"Evaluating {TOOL} on the {spec.name} dataset ({len(cases)} prompts)")
    results = []
    with local_api():
        settings = get_settings()
        transport = args.mcp_url or _in_process_mcp_server()
        for case in cases:
            for run in range(1, args.repeats + 1):
                calls = []
                client = _TimedClient(LLMClient(settings))
                orchestrator = ChatOrchestrator(
                    client, settings, _RecordingRegistry(MCPToolRegistry(transport), calls))
                started = time.perf_counter()
                error, answer = None, ""
                try:
                    answer = str(orchestrator.run(case.prompt, [], scope=RequestScope(EVAL_FA_ID)))
                except Exception as exc:
                    # Avoid storing provider exception strings that may contain connection details.
                    error = type(exc).__name__
                elapsed = time.perf_counter() - started
                selected = len(calls) == 1 and calls[0].name == TOOL
                arguments = selected and arguments_correct(case, calls[0].arguments, len(truth[case.case_id]))
                discovery_calls = [call for call in calls if call.name == TOOL]
                tool_result = bool(discovery_calls) and result_correct(case, discovery_calls[-1].result, truth[case.case_id])
                response = response_correct(case, answer, truth[case.case_id])
                row = {
                    "case_id": case.case_id, "run": run, "prompt": case.prompt,
                    "tool_selection_correct": selected, "arguments_correct": arguments,
                    "tool_result_correct": tool_result, "response_correct": response,
                    "passed": error is None and arguments and tool_result and response,
                    "tool_sequence": [call.name for call in calls],
                    "tool_arguments": discovery_calls[-1].arguments if discovery_calls else None,
                    "expected_count": len(truth[case.case_id]),
                    "returned_count": discovery_calls[-1].result.get("returned_count") if discovery_calls else None,
                    "end_to_end_seconds": round(elapsed, 3),
                    "llm_seconds": round(client.seconds, 3), "llm_calls": client.calls,
                    "discovery_tool_seconds": round(sum(call.seconds for call in discovery_calls), 3)
                    if discovery_calls else None,
                    "error": error, "answer_preview": answer[:1000], "answer": answer,
                }
                results.append(row)
                print(
                    f"[{'PASS' if row['passed'] else 'FAIL'}] {case.case_id} run {run}: "
                    f"tools={row['tool_sequence']} args={row['tool_arguments']} "
                    f"arguments={arguments} tool_result={tool_result} response={response} "
                    f"time={elapsed:.3f}s"
                    + (f" error={error}" if error else ""), flush=True,
                )
                if args.show_answers:
                    print(f"\n--- {case.case_id} answer (run {run}) ---\n"
                          f"{answer}\n--- end answer ---\n")

    summary = _summary(results)
    print(json.dumps(summary, indent=2))
    response_time = _response_time(cases, results)
    _print_response_time(response_time)

    RESULTS_DIR.mkdir(exist_ok=True)
    output = RESULTS_DIR / f"get_active_campaigns_{spec.name}_{datetime.now():%Y%m%d_%H%M%S}.json"
    output.write_text(json.dumps({
        "data_source": "synthetic", "dataset": asdict(spec),
        "model": settings.llm_model, "mcp_transport": args.mcp_url or "in-process",
        "cases": [asdict(case) for case in cases],
        "summary": summary, "response_time": response_time, "results": results,
    }, indent=2))
    print(f"Wrote {output}")
    return 0 if summary["pass_rate"] >= args.min_pass_rate else 1


if __name__ == "__main__":
    raise SystemExit(main())
