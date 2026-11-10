"""Measure client-recommendation latency on the shared small/large datasets.

From the repository root, with exactly one evaluation dataset already loaded::

    make eval-run EVAL=client_recommendation ARGS="--dataset small --repeats 3"
    make eval-run EVAL=client_recommendation ARGS="--dataset large --repeats 3"

These are separate runs against separately loaded datasets. This script never
provisions, clears or switches the database. It uses real Groq calls and the
normal orchestrator; recommendation snapshots may be created by the real tool.
Prompts have fresh, empty history and no selected campaign. Default transport is
in-process FastMCP; --mcp-url measures calls through a running MCP server instead.
Timing excludes preflight, browser/API request handling, saved chat and Excel
downloads. The six prompts cover four recommendations, a missing-campaign
clarification and an unknown campaign. Recovered tool errors retain their full
elapsed time in completed latency and are counted separately. No tool-call
accuracy, matching-accuracy or response-quality score is claimed.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
import statistics
import sys
import time
from typing import Any
from uuid import uuid4

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.campaigns import clock
from app.campaigns.repository import RequestScope, get_campaign, require_active
from app.config import get_settings
from app.llm import ChatOrchestrator, LLMClient
from app.tools.mcp_registry import MCPToolRegistry
from evaluation.evaluate_campaign_follow_up import (
    DATASETS, EVAL_FA_ID, _TimedClient, _campaign_id,
    _in_process_mcp_server, _resolve_dataset,
)

RESULTS_DIR = Path(__file__).resolve().parent / "results"
RECOMMEND = "recommend_clients_for_campaign"
LOOKUP = "resolve_campaign"
SCOPE = RequestScope(EVAL_FA_ID)


@dataclass(frozen=True)
class PromptCase:
    case_id: str
    campaign: str | None
    prompt: str
    expected_outcome: str = "recommendation"


PROMPTS = (
    PromptCase("1-young-families", "Young Families Cover Check",
               "Which clients do you recommend for the Young Families Cover Check?"),
    PromptCase("2-legacy", "Legacy Protection Refresh",
               "Who should I target for the legacy protection refresh campaign?"),
    PromptCase("3-clarification", None, "Which clients do you recommend?", "clarification"),
    PromptCase("4-unknown", "Nonexistent Evaluation Campaign Z9",
               "Which clients do you recommend for Nonexistent Evaluation Campaign Z9?", "not_found"),
    PromptCase("5-education", "Education Savings Kickstart",
               "Which clients do you recommend for the Education Savings Kickstart campaign?"),
    PromptCase("6-retirement", "Retirement Income Review",
               "Which clients do you recommend for the Retirement Income Review?"),
)
CASES = {
    dataset: tuple(replace(case, case_id=f"{dataset}-{case.case_id}") for case in PROMPTS)
    for dataset in DATASETS
}


class TimedRegistry:
    """Time real MCP calls, retaining counts rather than full client payloads."""

    def __init__(self, inner: Any, calls: list[dict]) -> None:
        self.inner, self.calls = inner, calls

    def bind_scope(self, *args: Any, **kwargs: Any) -> TimedRegistry:
        return TimedRegistry(self.inner.bind_scope(*args, **kwargs), self.calls)

    def schemas(self) -> list[dict]:
        # Preserve the real model's tool choices. Abort unrelated execution
        # instead of allowing an evaluation request to create CRM/email drafts.
        return self.inner.schemas()

    def execute(self, name: str, arguments_json: str) -> str:
        call: dict[str, Any] = {"name": name, "error": None}
        started = time.perf_counter()
        try:
            if name not in {LOOKUP, RECOMMEND}:
                raise ValueError("Unrelated tool requested during recommendation timing")
            result = self.inner.execute(name, arguments_json)
            payload = json.loads(result)
            if not isinstance(payload, dict):
                call["error"] = "invalid_tool_result"
            elif "error" in payload or "error_code" in payload:
                # Raw provider/storage errors can contain sensitive details.
                call["error"] = "tool_error"
                known_codes = {"invalid_arguments", "missing_context", "campaign_unavailable",
                               "campaign_inactive", "storage_unavailable"}
                code = payload.get("error_code")
                if isinstance(code, str) and code in known_codes:
                    call["error_code"] = code
                elif payload.get("error") == "Invalid tool arguments":
                    call["error_code"] = "invalid_arguments"
                else:
                    call["error_code"] = "unspecified_tool_error"
            elif name == LOOKUP:
                call["lookup_status"] = payload.get("status")
                if payload.get("status") not in {"matched", "not_found", "ambiguous"}:
                    call["error"] = "invalid_lookup_result"
            else:
                for key in ("campaign_id", "as_of_date", "evaluated_count", "matched_count",
                            "incomplete_count", "excluded_count", "returned_count"):
                    call[key] = payload.get(key)
                call["snapshot_created"] = bool(payload.get("list_id"))
            return result
        except Exception as exc:
            call["error"] = type(exc).__name__
            raise
        finally:
            call["seconds"] = time.perf_counter() - started
            self.calls.append(call)


def measure_run(case: PromptCase, run: int, settings: Any, transport: Any,
                client: Any, expected_id: str | None) -> dict:
    calls: list[dict] = []
    timed_client = _TimedClient(client)
    registry = TimedRegistry(MCPToolRegistry(transport), calls)
    orchestrator = ChatOrchestrator(timed_client, settings, registry)
    error = None
    result = None
    started = time.perf_counter()
    try:
        result = orchestrator.run(case.prompt, [], scope=SCOPE)
    except Exception as exc:
        error = type(exc).__name__
    elapsed = time.perf_counter() - started
    if error is None:
        recommendations = [call for call in calls if call["name"] == RECOMMEND]
        lookups = [call for call in calls if call["name"] == LOOKUP]
        if result is None or not str(result).strip():
            error = "empty_answer"
        elif case.expected_outcome == "clarification":
            if calls:
                error = "unexpected_tool_call"
        elif case.expected_outcome == "not_found":
            if recommendations:
                error = "unexpected_recommendation_call"
            elif not lookups or lookups[-1].get("lookup_status") != "not_found":
                error = "expected_not_found_result_missing"
        elif not recommendations:
            error = "no_recommendation_result"
        else:
            latest = recommendations[-1]
            if latest["error"] is not None:
                error = "tool_error"
            elif latest.get("campaign_id") != expected_id:
                error = "unexpected_campaign"
            elif type(latest.get("evaluated_count")) is not int:
                error = "invalid_recommendation_result"
    tool_errors = sum(call["error"] is not None for call in calls)
    return {
        "case_id": case.case_id, "run": run, "campaign": case.campaign,
        "expected_outcome": case.expected_outcome,
        "status": "completed" if error is None else "error", "error": error,
        "tool_error_count": tool_errors,
        "recovered": error is None and tool_errors > 0,
        "end_to_end_seconds": elapsed, "llm_seconds": timed_client.seconds,
        "llm_calls": timed_client.calls,
        "mcp_tool_seconds": sum(call["seconds"] for call in calls),
        "lookup_tool_seconds": sum(call["seconds"] for call in calls if call["name"] == LOOKUP),
        "recommendation_tool_seconds": sum(call["seconds"] for call in calls if call["name"] == RECOMMEND),
        "tool_calls": calls,
    }


def timing_statistics(values: list[float]) -> dict:
    if not values:
        return {key: None for key in ("mean", "median", "p95", "min", "max")}
    ordered = sorted(values)
    return {
        "mean": statistics.mean(values), "median": statistics.median(values),
        "p95": ordered[math.ceil(.95 * len(ordered)) - 1],
        "min": ordered[0], "max": ordered[-1],
    }


def summarise(results: list[dict]) -> dict:
    completed = [row for row in results if row["status"] == "completed"]
    failures = [row for row in results if row["status"] != "completed"]
    return {
        "attempts": len(results), "completed": len(completed), "errors": len(failures),
        "recovered": sum(bool(row.get("recovered")) for row in completed),
        "completed_latency_seconds": {
            key: timing_statistics([row[key] for row in completed])
            for key in ("end_to_end_seconds", "llm_seconds", "mcp_tool_seconds",
                        "lookup_tool_seconds", "recommendation_tool_seconds")
        },
        "failed_end_to_end_seconds": timing_statistics([row["end_to_end_seconds"] for row in failures]),
    }


def print_summary(summary: dict, by_case: dict) -> None:
    def formatted(value: float | None) -> str:
        return "—" if value is None else f"{value:.3f}"

    print(f"\nAttempts: {summary['attempts']}; completed: {summary['completed']}; "
          f"errors: {summary['errors']}; recovered: {summary['recovered']}")
    print("Completed-run latency (seconds; errors excluded)")
    print(f"{'Case':<28} {'Done':>4} {'Errors':>6} {'Mean':>8} {'Median':>8} {'P95':>8} {'LLM mean':>9} {'Tool mean':>10}")
    for name, item in [*by_case.items(), ("ALL", summary)]:
        timing = item["completed_latency_seconds"]
        total = timing["end_to_end_seconds"]
        print(f"{name:<28} {item['completed']:>4} {item['errors']:>6} "
              f"{formatted(total['mean']):>8} {formatted(total['median']):>8} {formatted(total['p95']):>8} "
              f"{formatted(timing['llm_seconds']['mean']):>9} "
              f"{formatted(timing['recommendation_tool_seconds']['mean']):>10}")


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", choices=sorted(DATASETS), default=None,
                        help="Expected loaded dataset; omitted means detect from table counts")
    parser.add_argument("--repeats", type=int, default=3, help="Runs per prompt (1–20; default 3)")
    parser.add_argument("--case", action="append", metavar="CASE_ID",
                        help="Only this dataset-prefixed case, e.g. small-1-young-families; repeatable")
    parser.add_argument("--list-cases", action="store_true", help="List prompts without database/model access")
    parser.add_argument("--mcp-url", default=None, help="Running MCP endpoint; default uses in-process MCP")
    parser.add_argument("--delay-seconds", type=float, default=0,
                        help="Delay between attempts, excluded from latency (default 0)")
    args = parser.parse_args(argv)
    if not 1 <= args.repeats <= 20:
        parser.error("--repeats must be between 1 and 20")
    if not math.isfinite(args.delay_seconds) or args.delay_seconds < 0:
        parser.error("--delay-seconds must be a finite nonnegative number")
    if args.case:
        known = {case.case_id for dataset, cases in CASES.items()
                 if args.dataset is None or dataset == args.dataset for case in cases}
        if set(args.case) - known:
            parser.error("Unknown case ID for the selected dataset")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    if args.list_cases:
        for dataset, cases in CASES.items():
            if args.dataset is None or args.dataset == dataset:
                for case in cases:
                    print(f"{case.case_id}: {case.prompt}")
        return 0
    # These checks occur before any model request and outside the timed interval.
    spec = _resolve_dataset(args.dataset)
    cases = [case for case in CASES[spec.name] if not args.case or case.case_id in args.case]
    if not cases or (args.case and set(args.case) - {case.case_id for case in cases}):
        raise SystemExit("Requested cases do not belong to the loaded dataset")
    settings = get_settings()
    if not settings.llm_configured:
        raise SystemExit("GROQ_API_KEY is not configured")
    business_date = clock.current_date()
    expected_ids = {case.case_id: _campaign_id(case.campaign)
                    for case in cases if case.expected_outcome == "recommendation"}
    for campaign_id in expected_ids.values():
        require_active(get_campaign(campaign_id, SCOPE), business_date)
    transport = args.mcp_url or _in_process_mcp_server()
    client = LLMClient(settings)
    results = []
    print(f"Recommendation latency: {spec.name}, {len(cases)} prompts x {args.repeats} runs")
    print("Measures orchestrator time, not browser/API or Excel download time.")
    for case in cases:
        for run in range(1, args.repeats + 1):
            if results and args.delay_seconds:
                time.sleep(args.delay_seconds)
            row = measure_run(case, run, settings, transport, client, expected_ids.get(case.case_id))
            results.append(row)
            print(f"[{row['status'].upper()}] {case.case_id} run {run}: "
                  f"total={row['end_to_end_seconds']:.3f}s llm={row['llm_seconds']:.3f}s "
                  f"recommendation={row['recommendation_tool_seconds']:.3f}s"
                  + (" recovered_after_tool_error=True" if row.get('recovered') else "")
                  + (f" error={row['error']}" if row['error'] else ""))
    summary = summarise(results)
    by_case = {case.case_id: summarise([row for row in results if row['case_id'] == case.case_id])
               for case in cases}
    report = {
        "evaluation_version": 2,
        "data_source": "synthetic", "dataset": asdict(spec), "as_of_date": business_date.isoformat(),
        "model": settings.llm_model, "mcp_transport": args.mcp_url or "in-process",
        "measurement": {
            "scope": "ChatOrchestrator.run through final answer, including tool discovery, model calls and MCP execution",
            "excludes": ["preflight", "browser rendering", "browser/API request handling",
                         "chat-history persistence", "Excel download", "inter-run delay"],
            "fresh_history": True, "selected_campaign": None, "sequential_runs": True,
            "warmup_runs_excluded": 0, "p95_method": "nearest rank; preliminary for small samples",
            "notes": "Snapshot writes are included. Existing recommendation logic and synthetic enrichment are unchanged. No accuracy or response-quality scores.",
        },
        "cases": [asdict(case) for case in cases], "summary": summary,
        "by_case": by_case,
        "by_outcome": {
            outcome: summarise([row for row in results if row['expected_outcome'] == outcome])
            for outcome in dict.fromkeys(case.expected_outcome for case in cases)
        },
        "results": results,
    }
    RESULTS_DIR.mkdir(exist_ok=True)
    output = RESULTS_DIR / (
        f"client_recommendation_latency_{spec.name}_"
        f"{datetime.now(timezone.utc):%Y%m%d_%H%M%S}_{uuid4().hex[:8]}.json"
    )
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print_summary(summary, by_case)
    print(f"Wrote {output}")
    return 0 if summary["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
