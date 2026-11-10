"""Evaluate Campaign Performance on the unchanged small and large SQL datasets.

Three prompts exercise direct routing; two paraphrases exercise LLM tool
selection. Score the MCP call, arguments, tool result, final answer and time.
The default in-process MCP transport excludes browser and HTTP network time.
Results are saved to evaluation/results/ (git-ignored).
Use --show-answers to print the complete chatbot replies during a run.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
import unicodedata
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from fractions import Fraction
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.campaigns.repository import RequestScope
from app.config import get_settings
from app.llm import ChatOrchestrator, LLMClient
from app.store import _connection
from app.tools.mcp_registry import MCPToolRegistry
from evaluation.evaluate_campaign_follow_up import (
    DATASETS, EVAL_FA_ID, _RecordingRegistry, _TimedClient,
    _in_process_mcp_server, _resolve_dataset,
)

RESULTS_DIR = Path(__file__).resolve().parent / "results"
PERFORMANCE = "get_campaign_contact_performance"
RANKING = "get_campaign_contact_ranking"


@dataclass(frozen=True)
class PromptCase:
    case_id: str
    prompt: str
    route: str
    tool: str
    kind: str
    campaign: str | None = None
    period: str = "this_week"
    week_of: str | None = None
    metric: str | None = None
    direction: str = "most"


# Identical wording on both datasets. The last two are outside the application's
# exact direct-route patterns, so the LLM must choose and call the MCP tool.
PROMPTS = (
    PromptCase(
        "1-summary",
        "Give me a performance summary for Legacy Protection Refresh, "
        "including its email coverage.",
        "direct", PERFORMANCE, "summary", "Legacy Protection Refresh",
    ),
    PromptCase(
        "2-specific-week",
        "How many members were added to Young Families Cover Check in the "
        "week containing 8 September 2026?",
        "direct", PERFORMANCE, "week", "Young Families Cover Check",
        "specific_week", "2026-09-08",
    ),
    PromptCase(
        "3-most-recorded-email",
        "Which campaign has the most members with a recorded email?",
        "direct", RANKING, "ranking", period="campaign_to_date",
        metric="clients_emailed",
    ),
    PromptCase(
        "4-lowest-coverage",
        "Across my campaigns, which has the smallest proportion of members "
        "with a recorded email? Include ties.",
        "llm", RANKING, "ranking", period="campaign_to_date",
        metric="email_coverage", direction="least",
    ),
    PromptCase(
        "5-highest-coverage",
        "Across my campaigns, which has the highest percentage of members "
        "with a recorded email? Include ties.",
        "llm", RANKING, "ranking", period="campaign_to_date",
        metric="email_coverage", direction="most",
    ),
)
CASES = {
    dataset: tuple(replace(case, case_id=f"{dataset}-{case.case_id}")
                   for case in PROMPTS)
    for dataset in DATASETS
}

# Fixed expected figures are independently derived from the checked-in SQL
# generators. Ground-truth ranking names are queried below because the large
# dataset creates 95 more campaign names programmatically.
EXPECTED = {
    "small": {
        "campaign_count": 5,
        "summary": (13, 10, 15, 76.9),
        "week": 5,
        "most_emailed": (11, 1),
        "lowest_coverage": (Fraction(10, 13), 4),
        "highest_coverage": (Fraction(11, 14), 1),
    },
    "large": {
        "campaign_count": 100,
        "summary": (250, 215, 430, 86.0),
        "week": 63,
        "most_emailed": (215, 30),
        "lowest_coverage": (Fraction(214, 250), 70),
        "highest_coverage": (Fraction(215, 250), 30),
    },
}
RANKING_EXPECTATIONS = {
    ("clients_emailed", "most"): "most_emailed",
    ("email_coverage", "least"): "lowest_coverage",
    ("email_coverage", "most"): "highest_coverage",
}


def _campaign_id(name: str) -> str:
    with _connection() as connection:
        rows = connection.execute(
            """SELECT campaign_id::text AS id FROM campaign
               WHERE tenant_id = %s AND created_by_user_id = %s
                 AND is_deleted = FALSE AND name = %s""",
            (EVAL_FA_ID, EVAL_FA_ID, name),
        ).fetchall()
    if len(rows) != 1:
        raise SystemExit(f"Expected exactly one evaluation campaign named {name!r}")
    return rows[0]["id"]


def _ranking_truth(metric: str, direction: str):
    """Read the fixture directly and compute leaders independently of the tool."""
    with _connection() as connection:
        rows = connection.execute(
            """SELECT c.name, COUNT(m.contact_id) AS members,
                      COUNT(m.contact_id) FILTER
                        (WHERE m.email_send_count > 0) AS emailed
               FROM campaign AS c
               LEFT JOIN campaign_member AS m
                 ON m.tenant_id = c.tenant_id AND m.campaign_id = c.campaign_id
                AND m.is_deleted = FALSE AND m.added_by_user_id = %s
               WHERE c.tenant_id = %s AND c.created_by_user_id = %s
                 AND c.is_deleted = FALSE
               GROUP BY c.campaign_id, c.name""",
            (EVAL_FA_ID, EVAL_FA_ID, EVAL_FA_ID),
        ).fetchall()
    candidates = []
    for row in rows:
        members, emailed = int(row["members"]), int(row["emailed"])
        if metric == "email_coverage" and members == 0:
            continue
        score = Fraction(emailed, members) if metric == "email_coverage" else emailed
        candidates.append((row["name"], members, emailed, score))
    if not candidates:
        raise SystemExit("The evaluation dataset has no rankable campaigns")
    value = (min if direction == "least" else max)(row[3] for row in candidates)
    leaders = sorted((row for row in candidates if row[3] == value),
                     key=lambda row: row[0])
    return leaders[:20], len(leaders), value


def _arguments_correct(case: PromptCase, arguments: dict) -> bool:
    if any(key in arguments for key in ("fa_id", "tenant_id")):
        return False
    if case.tool == PERFORMANCE:
        return (arguments.get("campaign") == case.campaign
                and arguments.get("period", "this_week") == case.period
                and arguments.get("week_of") == case.week_of)
    return (arguments.get("metric", "clients_emailed") == case.metric
            and arguments.get("period", "campaign_to_date") == case.period
            and arguments.get("direction", "most") == case.direction
            and "campaign" not in arguments)


def _tool_result_correct(case: PromptCase, result: dict, expected: dict,
                         campaign_ids: dict, rankings: dict) -> bool:
    if result.get("data_source") != "synthetic" or result.get("error_code"):
        return False
    if case.tool == PERFORMANCE:
        if (result.get("campaign_id") != campaign_ids[case.campaign]
                or result.get("campaign_name") != case.campaign
                or result.get("requested_period") != case.period):
            return False
        if case.kind == "summary":
            return tuple(result.get(key) for key in (
                "campaign_members_total", "clients_emailed_total",
                "email_sends_total", "email_coverage_percent",
            )) == expected["summary"]
        if case.kind == "week":
            return (result.get("week_of") == case.week_of
                    and result.get("requested_week_start_date") == "2026-09-07"
                    and result.get("requested_week_end_date") == "2026-09-13"
                    and result.get("members_added_requested_week") == expected["week"])
        raise ValueError(f"Unsupported performance case: {case.kind}")

    visible, tie_count, value = rankings[(case.metric, case.direction)]
    known_value, known_ties = expected[RANKING_EXPECTATIONS[(case.metric, case.direction)]]
    actual = result.get("leaders")
    if (value != known_value or tie_count != known_ties
            or result.get("metric") != case.metric
            or result.get("direction") != case.direction
            or result.get("requested_period") != case.period
            or result.get("campaign_count") != expected["campaign_count"]
            or result.get("leaders_truncated") is not (tie_count > 20)
            or not isinstance(actual, list) or len(actual) != len(visible)):
        return False
    for leader, (name, members, emailed, _) in zip(actual, visible):
        if (leader.get("campaign_name") != name
                or leader.get("campaign_members_total") != members
                or leader.get("clients_emailed_total") != emailed):
            return False
        if case.metric == "email_coverage":
            if leader.get("email_coverage_percent") != round(100 * float(value), 1):
                return False
        elif leader.get("metric_count") != value:
            return False
    return True


def _normalized_response(answer: str) -> str:
    """Ignore typography differences while comparing names and percentages."""
    normalized = unicodedata.normalize("NFKC", answer)
    normalized = normalized.translate(str.maketrans({
        "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-",
    }))
    normalized = re.sub(r"\s+", " ", normalized)
    return re.sub(r"\s+%", "%", normalized).casefold()


def _claims_email_receipt(answer: str) -> bool:
    """A stored send count does not establish that a member received an email."""
    text = _normalized_response(answer)
    return re.search(
        r"\b(?:have|has|had|were|was)\s+received\b.{0,80}\bemail\b"
        r"|\bemail(?:s)?\b.{0,40}\b(?:delivered|received)\b",
        text,
    ) is not None


def _response_correct(case: PromptCase, answer: str, expected: dict,
                      rankings: dict) -> bool:
    if not answer or _claims_email_receipt(answer):
        return False
    if case.kind == "summary":
        members, emailed, sends, coverage = expected["summary"]
        return all(item in answer for item in (
            case.campaign,
            f"| Campaign members | {members} |",
            f"| Members with a recorded email | {emailed} |",
            f"| Total recorded email sends | {sends} |",
            f"| Email coverage | {coverage:g}% |",
        ))
    if case.kind == "week":
        return all(item in answer for item in (
            case.campaign, f"**{expected['week']} members**",
            "7 Sep 2026–13 Sep 2026",
        ))
    visible, tie_count, value = rankings[(case.metric, case.direction)]
    normalized_answer = _normalized_response(answer)
    named_leaders = sum(_normalized_response(name) in normalized_answer
                        for name, _, _, _ in visible)
    if (named_leaders == 0 if case.route == "llm" and tie_count > 20
            else named_leaders != len(visible)):
        return False
    if case.metric == "email_coverage":
        if f"{round(100 * float(value), 1):g}%" not in normalized_answer:
            return False
    elif re.search(rf"\b{value}\b", answer) is None:
        return False
    if tie_count > 20:
        return re.search(r"additional|not shown|truncat|at least|more tied",
                         answer, re.IGNORECASE) is not None
    return True


def _rate(results: list[dict], key: str) -> float:
    return round(sum(bool(row[key]) for row in results) / len(results), 3)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=sorted(DATASETS), default=None)
    parser.add_argument("--case", action="append", default=None, metavar="CASE_ID")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--min-pass-rate", type=float, default=1.0)
    parser.add_argument("--mcp-url", default=None)
    parser.add_argument("--show-answers", action="store_true",
                        help="Print each complete chatbot answer in the terminal")
    args = parser.parse_args()
    if args.repeats < 1 or not 0 <= args.min_pass_rate <= 1:
        parser.error("Use a positive --repeats and a --min-pass-rate between 0 and 1")

    spec = _resolve_dataset(args.dataset)
    cases = CASES[spec.name]
    if args.case:
        unknown = set(args.case) - {case.case_id for case in cases}
        if unknown:
            parser.error(f"Unknown case(s): {', '.join(sorted(unknown))}")
        cases = tuple(case for case in cases if case.case_id in args.case)
    settings = get_settings()
    if not settings.llm_configured:
        raise SystemExit("The two LLM cases require GROQ_API_KEY in backend/.env")

    campaign_ids = {
        name: _campaign_id(name) for name in (
            "Legacy Protection Refresh", "Young Families Cover Check",
        )
    }
    rankings = {
        (metric, direction): _ranking_truth(metric, direction)
        for metric, direction in RANKING_EXPECTATIONS
    }
    expected = EXPECTED[spec.name]
    for (metric, direction), key in RANKING_EXPECTATIONS.items():
        _, ties, value = rankings[(metric, direction)]
        if (value, ties) != expected[key]:
            raise SystemExit(f"The loaded {spec.name} ranking seed differs from {key} expectations")

    transport = args.mcp_url or _in_process_mcp_server()
    scope = RequestScope(EVAL_FA_ID)
    results = []
    print(f"Evaluating Campaign Performance on {spec.name}: {len(cases)} prompts")
    for case in cases:
        for run in range(1, args.repeats + 1):
            calls = []
            client = _TimedClient(LLMClient(settings))
            orchestrator = ChatOrchestrator(
                client, settings, _RecordingRegistry(MCPToolRegistry(transport), calls)
            )
            started = time.perf_counter()
            error = None
            try:
                answer = str(orchestrator.run(case.prompt, [], scope=scope))
            except Exception as exc:
                answer, error = "", f"{type(exc).__name__}: {exc}"
            elapsed = time.perf_counter() - started
            selected = len(calls) == 1 and calls[0].name == case.tool
            arguments = _arguments_correct(case, calls[0].arguments) if selected else False
            tool_result = (_tool_result_correct(
                case, calls[0].result, expected, campaign_ids, rankings
            ) if selected else False)
            response = _response_correct(case, answer, expected, rankings)
            response_issue = (
                "Claims email receipt or delivery from a recorded send"
                if _claims_email_receipt(answer) else "Expected answer facts are missing"
            ) if not response else None
            route = client.calls == 0 if case.route == "direct" else client.calls > 0
            row = {
                "case_id": case.case_id, "run": run, "prompt": case.prompt,
                "expected_route": case.route, "route_correct": route,
                "tool_selection_correct": selected, "arguments_correct": arguments,
                "tool_result_correct": tool_result, "response_correct": response,
                "response_issue": response_issue,
                "passed": (error is None and route and selected and arguments
                           and tool_result and response),
                "tool_sequence": [call.name for call in calls],
                "tool_arguments": calls[0].arguments if selected else None,
                "end_to_end_seconds": round(elapsed, 3),
                "llm_seconds": round(client.seconds, 3),
                "llm_calls": client.calls,
                "performance_tool_seconds": round(calls[0].seconds, 3) if selected else None,
                "error": error, "answer_preview": answer[:1000],
                "answer": answer,
            }
            results.append(row)
            print(
                f"[{'PASS' if row['passed'] else 'FAIL'}] {case.case_id} run {run}: "
                f"route={case.route} llm_calls={client.calls} "
                f"tools={row['tool_sequence']} args={row['tool_arguments']} "
                f"tool_result={tool_result} response={response} "
                f"time={row['end_to_end_seconds']:.3f}s"
                + (f" response_issue={response_issue}" if response_issue else "")
                + (f" error={error}" if error else "")
            )
            if args.show_answers:
                print(f"\n--- {case.case_id} answer (run {run}) ---\n"
                      f"{answer}\n--- end answer ---\n")

    summary = {
        "runs": len(results),
        "route_accuracy": _rate(results, "route_correct"),
        "tool_selection_accuracy": _rate(results, "tool_selection_correct"),
        "argument_accuracy": _rate(results, "arguments_correct"),
        "tool_call_accuracy": round(sum(
            row["tool_selection_correct"] and row["arguments_correct"]
            for row in results
        ) / len(results), 3),
        "tool_result_accuracy": _rate(results, "tool_result_correct"),
        "response_accuracy": _rate(results, "response_correct"),
        "pass_rate": _rate(results, "passed"),
    }
    summary["by_route"] = {}
    for route_name in ("direct", "llm"):
        route_results = [
            row for row in results if row["expected_route"] == route_name
        ]
        if route_results:
            summary["by_route"][route_name] = {
                "runs": len(route_results),
                "tool_call_accuracy": round(sum(
                    row["tool_selection_correct"] and row["arguments_correct"]
                    for row in route_results
                ) / len(route_results), 3),
                "response_accuracy": _rate(route_results, "response_correct"),
                "pass_rate": _rate(route_results, "passed"),
            }
    timings = []
    for case in cases:
        runs = [row for row in results if row["case_id"] == case.case_id]
        timings.append({
            "case_id": case.case_id, "route": case.route, "runs": len(runs),
            "mean_end_to_end_seconds": round(statistics.mean(
                row["end_to_end_seconds"] for row in runs
            ), 3),
            "mean_llm_seconds": round(statistics.mean(
                row["llm_seconds"] for row in runs
            ), 3),
            "mean_tool_seconds": round(statistics.mean(
                row["performance_tool_seconds"] for row in runs
                if row["performance_tool_seconds"] is not None
            ), 3) if any(row["performance_tool_seconds"] is not None
                       for row in runs) else None,
        })
    response_time = {
        "prompts": timings,
        "total_seconds": round(sum(row["mean_end_to_end_seconds"]
                                   for row in timings), 3),
        "mean_seconds": round(statistics.mean(
            row["mean_end_to_end_seconds"] for row in timings
        ), 3),
    }
    print(json.dumps({"summary": summary, "response_time": response_time}, indent=2))

    RESULTS_DIR.mkdir(exist_ok=True)
    output = RESULTS_DIR / (
        f"campaign_performance_{spec.name}_{datetime.now():%Y%m%d_%H%M%S}.json"
    )
    output.write_text(json.dumps({
        "data_source": "synthetic", "dataset": asdict(spec),
        "model": settings.llm_model, "mcp_transport": args.mcp_url or "in-process",
        "cases": [asdict(case) for case in cases], "summary": summary,
        "response_time": response_time, "results": results,
    }, indent=2))
    print(f"Wrote {output}")
    return 0 if summary["pass_rate"] >= args.min_pass_rate else 1


if __name__ == "__main__":
    raise SystemExit(main())
