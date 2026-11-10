"""Evaluate the campaign-email MCP workflow on the shared synthetic datasets.

The evaluator covers tool-call accuracy, response/database accuracy and response
time for ``prepare_campaign_email``, ``confirm_campaign_email`` and
``discard_campaign_email``. Case setup is deliberately excluded from timing.

From the repository root, load exactly one shared evaluation dataset and run::

    terraform -chdir=backend/terraform destroy
    make eval DATASET=small
    make eval-run EVAL=campaign_email ARGS="--dataset small --repeats 5"

Repeat the provisioning step with ``DATASET=large`` for the large evaluation.
All delivery is forced through the mock transport; this file refuses to run in
GWM delivery mode. Results are written under ``backend/evaluation/results/``.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import statistics
import sys
import time
from typing import Any
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.campaigns.email import (  # noqa: E402
    PrepareCampaignEmailArguments,
    confirm_campaign_email,
    prepare_campaign_email,
)
from app.campaigns.repository import RequestScope  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.integrations.gwm_email import MockEmailTransport  # noqa: E402
from app.llm import ChatOrchestrator, LLMClient  # noqa: E402
from app.store import ChatHistoryItem  # noqa: E402
from app.tools.mcp_registry import MCPToolRegistry  # noqa: E402


EVAL_FA_ID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
SCOPE = RequestScope(EVAL_FA_ID)
RESULTS_DIR = Path(__file__).resolve().parent / "results"


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
class PromptCase:
    case_id: str
    tool: str
    scenario: str
    prompt: str
    campaign_name: str
    expected_tools: tuple[str, ...]
    expected_signoff: str | None = None
    expected_subject: str | None = None
    expected_body_fragment: str | None = None
    note: str = ""


# Five prompts per tool. The same cases run against both shared datasets.
PROMPT_CASES = (
    PromptCase(
        "prepare-01-signoff-short",
        "prepare_campaign_email",
        "new_signoff",
        "Steven",
        "Young Families Cover Check",
        ("prepare_campaign_email",),
        expected_signoff="Steven",
    ),
    PromptCase(
        "prepare-02-signoff-explicit",
        "prepare_campaign_email",
        "new_signoff",
        "Use Steven Tan",
        "Education Savings Kickstart",
        ("prepare_campaign_email",),
        expected_signoff="Steven Tan",
    ),
    PromptCase(
        "prepare-03-signoff-sentence",
        "prepare_campaign_email",
        "new_signoff",
        "Sign it as Sarah Lim",
        "Young Families Cover Check",
        ("prepare_campaign_email",),
        expected_signoff="Sarah Lim",
    ),
    PromptCase(
        "prepare-04-subject-edit",
        "prepare_campaign_email",
        "subject_edit",
        "Change the subject to Join our planning forum",
        "Education Savings Kickstart",
        ("prepare_campaign_email",),
        expected_subject="Join our planning forum",
    ),
    PromptCase(
        "prepare-05-body-edit",
        "prepare_campaign_email",
        "body_revision",
        "Add that the session includes an educational financial-planning discussion",
        "Young Families Cover Check",
        ("prepare_campaign_email",),
        expected_body_fragment="educational financial-planning discussion",
    ),
    PromptCase(
        "confirm-01-valid",
        "confirm_campaign_email",
        "valid_confirmation",
        "<confirmation_phrase>",
        "Young Families Cover Check",
        ("confirm_campaign_email",),
    ),
    PromptCase(
        "confirm-02-wrong-code",
        "confirm_campaign_email",
        "wrong_confirmation",
        "CONFIRM EMAIL ZZZZZZ",
        "Education Savings Kickstart",
        ("confirm_campaign_email",),
    ),
    PromptCase(
        "confirm-03-general-approval",
        "confirm_campaign_email",
        "general_approval",
        "Looks good, send it",
        "Young Families Cover Check",
        (),
        note="General approval must not bypass the exact confirmation phrase.",
    ),
    PromptCase(
        "confirm-04-expired",
        "confirm_campaign_email",
        "expired_confirmation",
        "<confirmation_phrase>",
        "Education Savings Kickstart",
        ("confirm_campaign_email",),
    ),
    PromptCase(
        "confirm-05-repeated",
        "confirm_campaign_email",
        "repeated_confirmation",
        "<confirmation_phrase>",
        "Young Families Cover Check",
        ("confirm_campaign_email",),
    ),
    PromptCase(
        "discard-01-campaign-question",
        "discard_campaign_email",
        "cancel_campaign_question",
        "Cancel email drafting",
        "Young Families Cover Check",
        ("discard_campaign_email",),
    ),
    PromptCase(
        "discard-02-signoff-question",
        "discard_campaign_email",
        "cancel_signoff_question",
        "Never mind",
        "Education Savings Kickstart",
        ("discard_campaign_email",),
    ),
    PromptCase(
        "discard-03-preview",
        "discard_campaign_email",
        "discard_preview",
        "Discard this email",
        "Young Families Cover Check",
        ("discard_campaign_email",),
    ),
    PromptCase(
        "discard-04-exit",
        "discard_campaign_email",
        "exit_preview",
        "Exit",
        "Education Savings Kickstart",
        ("discard_campaign_email",),
    ),
    PromptCase(
        "discard-05-content-question",
        "discard_campaign_email",
        "stop_content_question",
        "Stop drafting",
        "Young Families Cover Check",
        ("discard_campaign_email",),
    ),
)


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    seconds: float
    result: dict[str, Any]


@dataclass
class CaseState:
    campaign_id: str
    session_id: str
    prompt: str
    history: list[ChatHistoryItem]
    preview: dict[str, Any] | None = None
    member_counts_before: dict[str, int] = field(default_factory=dict)
    campaign_send_runs_before: int = 0


@dataclass
class CaseResult:
    case_id: str
    run: int
    tool: str
    scenario: str
    prompt: str
    campaign_name: str
    campaign_id: str
    expected_tools: list[str]
    actual_tools: list[str]
    tool_arguments_correct: bool
    tool_accuracy: bool
    response_accuracy: bool
    response_failures: list[str]
    end_to_end_seconds: float
    llm_seconds: float
    llm_calls: int
    target_tool_seconds: float | None
    answer_preview: str
    error: str | None = None


class RecordingRegistry:
    """Delegate to FastMCP while recording tool order, arguments and duration."""

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
    """Delegate to the configured LLM and record provider time and call count."""

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
        "pulse_email_evaluation_mcp", BACKEND_DIR / "mcp" / "server.py"
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
    return {
        "campaigns": int(row["campaigns"]),
        "contacts": int(row["contacts"]),
        "campaign_members": int(row["campaign_members"]),
    }


def _expected_counts(spec: DatasetSpec) -> dict[str, int]:
    return {
        "campaigns": spec.campaigns,
        "contacts": spec.contacts,
        "campaign_members": spec.campaign_members,
    }


def _resolve_dataset(requested: str | None) -> DatasetSpec:
    actual = _loaded_counts()
    if requested is None:
        for spec in DATASETS.values():
            if actual == _expected_counts(spec):
                return spec
        raise SystemExit(
            f"Database does not contain a recognised evaluation dataset: {actual}.\n"
            "Run terraform destroy, then make eval DATASET=small|large."
        )
    spec = DATASETS[requested]
    if actual != _expected_counts(spec):
        raise SystemExit(
            f"Expected the {spec.name} evaluation dataset {_expected_counts(spec)}, "
            f"but found {actual}.\nRun terraform destroy, then "
            f"make eval DATASET={spec.name}."
        )
    return spec


def _campaign_id(name: str) -> str:
    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT campaign_id::text AS campaign_id
            FROM campaign
            WHERE tenant_id = %s AND created_by_user_id = %s
              AND is_deleted = FALSE AND name = %s
            """,
            (EVAL_FA_ID, EVAL_FA_ID, name),
        ).fetchall()
    if len(rows) != 1:
        raise SystemExit(f"Expected one campaign named {name!r}, found {len(rows)}")
    return str(rows[0]["campaign_id"])


def _insert_session(session_id: str) -> None:
    with _connection() as connection:
        connection.execute(
            "INSERT INTO campaign_chat_sessions (fa_id, session_id) VALUES (%s, %s)",
            (EVAL_FA_ID, session_id),
        )


def _metadata(campaign_id: str, session_id: str, message: str) -> dict[str, Any]:
    return {
        "pulse_scope": {"fa_id": EVAL_FA_ID, "tenant_id": "pulse-demo"},
        "campaign_id": campaign_id,
        "session_id": session_id,
        "latest_user_message": message,
    }


def _prepare_preview(campaign_id: str, session_id: str) -> dict[str, Any]:
    preview = prepare_campaign_email(
        PrepareCampaignEmailArguments(
            subject="Educational campaign invitation",
            body=(
                "Hello {{client_name}}, this is an educational campaign invitation. "
                "Individual circumstances and suitability require adviser review."
            ),
            signoff_name="Steven",
        ),
        _metadata(campaign_id, session_id, "Prepare evaluation preview"),
    )
    if not preview.get("prepared"):
        raise RuntimeError(f"Could not prepare case state: {preview}")
    return preview


def _latest_batch(session_id: str) -> dict[str, Any] | None:
    with _connection() as connection:
        row = connection.execute(
            """
            SELECT * FROM campaign_email_send
            WHERE tenant_id = %s AND fa_id = %s AND session_id = %s
            ORDER BY created_at DESC, send_batch_id DESC
            LIMIT 1
            """,
            (EVAL_FA_ID, EVAL_FA_ID, session_id),
        ).fetchone()
    return dict(row) if row else None


def _member_counts(campaign_id: str, contact_ids: list[str]) -> dict[str, int]:
    if not contact_ids:
        return {}
    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT contact_id::text AS contact_id, email_send_count
            FROM campaign_member
            WHERE tenant_id = %s AND campaign_id = %s
              AND contact_id = ANY(%s::uuid[]) AND is_deleted = FALSE
            """,
            (EVAL_FA_ID, campaign_id, contact_ids),
        ).fetchall()
    result = {contact_id: 0 for contact_id in contact_ids}
    result.update({str(row["contact_id"]): int(row["email_send_count"]) for row in rows})
    return result


def _campaign_send_runs(campaign_id: str) -> int:
    with _connection() as connection:
        row = connection.execute(
            """
            SELECT email_send_runs FROM campaign
            WHERE tenant_id = %s AND campaign_id = %s AND is_deleted = FALSE
            """,
            (EVAL_FA_ID, campaign_id),
        ).fetchone()
    return int(row["email_send_runs"])


def _history(message: str) -> list[ChatHistoryItem]:
    return [ChatHistoryItem("2026-11-10T00:00:00Z", False, message)]


def _prepare_case_state(case: PromptCase, run: int) -> CaseState:
    """Create prerequisite state; callers start timing only after this returns."""
    campaign_id = _campaign_id(case.campaign_name)
    session_id = f"email-eval-{case.case_id}-{run}-{uuid4().hex[:8]}"
    _insert_session(session_id)
    prompt = case.prompt
    history: list[ChatHistoryItem] = []
    preview: dict[str, Any] | None = None

    if case.scenario == "new_signoff":
        history = _history(
            "What name would you like me to use in the email sign-off? "
            "You can also say **cancel email drafting**."
        )
    elif case.scenario in {"subject_edit", "body_revision"}:
        preview = _prepare_preview(campaign_id, session_id)
        history = _history(
            "## Review campaign email\n\nReview the subject, message and recipients."
        )
    elif case.scenario in {
        "valid_confirmation",
        "wrong_confirmation",
        "general_approval",
        "expired_confirmation",
        "repeated_confirmation",
    }:
        preview = _prepare_preview(campaign_id, session_id)
        history = _history(
            "## Review campaign email\n\nEnter the exact confirmation phrase to send."
        )
        if prompt == "<confirmation_phrase>":
            prompt = str(preview["confirmation_phrase"])
        if case.scenario == "expired_confirmation":
            with _connection() as connection:
                connection.execute(
                    """
                    UPDATE campaign_email_send
                    SET expires_at = CURRENT_TIMESTAMP - INTERVAL '1 minute'
                    WHERE tenant_id = %s AND send_batch_id = %s
                    """,
                    (EVAL_FA_ID, preview["send_batch_id"]),
                )
        if case.scenario == "repeated_confirmation":
            confirm_campaign_email(
                _metadata(campaign_id, session_id, prompt), MockEmailTransport()
            )
    elif case.scenario == "cancel_campaign_question":
        history = _history("Which campaign would you like to use for this email?")
    elif case.scenario == "cancel_signoff_question":
        history = _history(
            "What name would you like me to use in the email sign-off?"
        )
    elif case.scenario in {"discard_preview", "exit_preview"}:
        preview = _prepare_preview(campaign_id, session_id)
        history = _history(
            "## Review campaign email\n\nReview the subject, message and recipients."
        )
    elif case.scenario == "stop_content_question":
        history = _history("Please provide both the email subject and message.")
    else:
        raise ValueError(f"Unknown campaign-email scenario: {case.scenario}")

    recipient_ids = (
        [str(item["contact_id"]) for item in preview.get("recipients", [])]
        if preview
        else []
    )
    return CaseState(
        campaign_id=campaign_id,
        session_id=session_id,
        prompt=prompt,
        history=history,
        preview=preview,
        member_counts_before=_member_counts(campaign_id, recipient_ids),
        campaign_send_runs_before=_campaign_send_runs(campaign_id),
    )


def _tool_arguments_correct(
    case: PromptCase, state: CaseState, calls: list[ToolCall]
) -> bool:
    if tuple(call.name for call in calls) != case.expected_tools:
        return False
    if not calls:
        return not case.expected_tools
    target_calls = [call for call in calls if call.name == case.tool]
    if len(target_calls) != 1:
        return False
    arguments = target_calls[0].arguments
    if case.tool == "prepare_campaign_email":
        if str(arguments.get("campaign_id")) != state.campaign_id:
            return False
        if case.expected_signoff is not None:
            return arguments.get("signoff_name") == case.expected_signoff
        if case.expected_subject is not None:
            return arguments.get("subject") == case.expected_subject
        if case.expected_body_fragment is not None:
            body = arguments.get("body")
            return isinstance(body, str) and case.expected_body_fragment.casefold() in body.casefold()
    # Confirmation and discard have no model-supplied arguments. Their trusted
    # campaign/session/latest-message context is MCP request metadata.
    return arguments == {}


def _recipient_failures(batch: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    snapshot = batch.get("recipient_snapshot") or []
    if not isinstance(snapshot, list) or not snapshot:
        return ["recipient snapshot is empty or invalid"]
    ids = [str(item.get("contact_id", "")) for item in snapshot]
    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT contact_id::text AS contact_id, full_name, email, opt_in_email,
                   assigned_to_user_id::text, created_by_user_id::text, is_deleted
            FROM contact
            WHERE tenant_id = %s AND contact_id = ANY(%s::uuid[])
            """,
            (EVAL_FA_ID, ids),
        ).fetchall()
    contacts = {str(row["contact_id"]): row for row in rows}
    if set(ids) != set(contacts):
        failures.append("recipient snapshot contains an unknown contact")
    for item in snapshot:
        contact_id = str(item.get("contact_id", ""))
        contact = contacts.get(contact_id)
        if contact is None:
            continue
        accessible = (
            contact["assigned_to_user_id"] == EVAL_FA_ID
            or contact["created_by_user_id"] == EVAL_FA_ID
        )
        if (
            contact["is_deleted"]
            or not accessible
            or contact["opt_in_email"] is not True
            or not str(contact["email"] or "").strip()
        ):
            failures.append(f"recipient {contact_id} is not eligible for email")
        if item.get("name") != contact["full_name"] or item.get("email") != contact["email"]:
            failures.append(f"recipient snapshot does not match contact {contact_id}")
    return failures


def _response_failures(
    case: PromptCase, state: CaseState, answer: str
) -> list[str]:
    failures: list[str] = []
    lowered = answer.casefold()
    batch = _latest_batch(state.session_id)

    if case.tool == "prepare_campaign_email":
        if batch is None or batch["status"] != "prepared":
            return ["latest email preview is not in prepared status"]
        if str(batch["campaign_id"]) != state.campaign_id:
            failures.append("preview belongs to the wrong campaign")
        if case.expected_signoff and batch["signoff_name"] != case.expected_signoff:
            failures.append("requested sign-off was not stored")
        if case.expected_subject and batch["subject"] != case.expected_subject:
            failures.append("requested subject was not stored")
        if case.expected_body_fragment and case.expected_body_fragment.casefold() not in str(
            batch["message_body"]
        ).casefold():
            failures.append("requested body revision was not stored")
        failures.extend(_recipient_failures(batch))
        if "review campaign email" not in lowered:
            failures.append("response does not present a reviewable preview")
        if "simulated" not in lowered:
            failures.append("response does not identify mock delivery")
        if "confirm email" not in lowered:
            failures.append("response does not include an exact confirmation phrase")
        return failures

    preview_ids = (
        [str(item["contact_id"]) for item in state.preview.get("recipients", [])]
        if state.preview
        else []
    )
    counts_after = _member_counts(state.campaign_id, preview_ids)
    send_runs_after = _campaign_send_runs(state.campaign_id)

    if case.tool == "confirm_campaign_email":
        if batch is None:
            return ["email preview audit row is missing"]
        if case.scenario == "valid_confirmation":
            if batch["status"] != "sent":
                failures.append("valid confirmation did not complete mock delivery")
            results = batch.get("provider_results") or []
            successful_ids = {
                str(item["contact_id"])
                for item in results
                if isinstance(item, dict) and item.get("success")
            }
            if successful_ids != set(preview_ids):
                failures.append("provider results do not match the reviewed recipients")
            for contact_id in successful_ids:
                if counts_after.get(contact_id, 0) != state.member_counts_before.get(contact_id, 0) + 1:
                    failures.append(f"email_send_count was not incremented once for {contact_id}")
            if send_runs_after != state.campaign_send_runs_before + 1:
                failures.append("campaign email_send_runs was not incremented once")
            if "campaign email result" not in lowered or "successful" not in lowered:
                failures.append("response does not contain a successful send summary")
        elif case.scenario == "wrong_confirmation":
            if batch["status"] != "prepared" or "invalid" not in lowered:
                failures.append("incorrect confirmation was not rejected")
        elif case.scenario == "general_approval":
            if batch["status"] != "prepared":
                failures.append("general approval changed the preview state")
            if "exact confirmation phrase" not in lowered or "no email was sent" not in lowered:
                failures.append("general approval response does not enforce exact confirmation")
        elif case.scenario == "expired_confirmation":
            if batch["status"] != "invalidated" or "expired" not in lowered:
                failures.append("expired confirmation was not safely invalidated")
        elif case.scenario == "repeated_confirmation":
            if batch["status"] != "sent":
                failures.append("completed result was not retained")
            if counts_after != state.member_counts_before:
                failures.append("repeated confirmation changed recipient send counts")
            if send_runs_after != state.campaign_send_runs_before:
                failures.append("repeated confirmation changed campaign send runs")
            if "no email was sent again" not in lowered:
                failures.append("response does not explain idempotent confirmation")

        if case.scenario != "valid_confirmation":
            if counts_after != state.member_counts_before:
                failures.append("rejected confirmation changed recipient send counts")
            if send_runs_after != state.campaign_send_runs_before:
                failures.append("rejected confirmation changed campaign send runs")
        return failures

    if case.tool == "discard_campaign_email":
        if "email drafting ended" not in lowered or "no email was sent" not in lowered:
            failures.append("response does not clearly end email drafting")
        if case.scenario in {"discard_preview", "exit_preview"}:
            if batch is None or batch["status"] != "invalidated":
                failures.append("prepared preview was not invalidated")
        elif batch is not None:
            failures.append("discard before preview unexpectedly created an audit row")
        if counts_after != state.member_counts_before:
            failures.append("discard changed campaign-member send counts")
        if send_runs_after != state.campaign_send_runs_before:
            failures.append("discard changed campaign send runs")
    return failures


def _run_case(
    case: PromptCase,
    run: int,
    settings: Any,
    transport: Any,
) -> CaseResult:
    state = _prepare_case_state(case, run)
    calls: list[ToolCall] = []
    client = TimedLLMClient(LLMClient(settings))
    orchestrator = ChatOrchestrator(
        client, settings, RecordingRegistry(MCPToolRegistry(transport), calls)
    )

    started = time.perf_counter()
    answer = ""
    error: str | None = None
    try:
        result = orchestrator.run(
            state.prompt,
            state.history,
            scope=SCOPE,
            campaign_id=state.campaign_id,
            session_id=state.session_id,
        )
        answer = str(result)
    except Exception as exc:  # retain provider/tool failures as failed observations
        error = f"{type(exc).__name__}: {exc}"
    elapsed = time.perf_counter() - started

    arguments_correct = error is None and _tool_arguments_correct(case, state, calls)
    tool_accuracy = (
        error is None
        and tuple(call.name for call in calls) == case.expected_tools
        and arguments_correct
    )
    response_failures = [error] if error else _response_failures(case, state, answer)
    target_times = [call.seconds for call in calls if call.name == case.tool]
    return CaseResult(
        case_id=case.case_id,
        run=run,
        tool=case.tool,
        scenario=case.scenario,
        prompt=state.prompt,
        campaign_name=case.campaign_name,
        campaign_id=state.campaign_id,
        expected_tools=list(case.expected_tools),
        actual_tools=[call.name for call in calls],
        tool_arguments_correct=arguments_correct,
        tool_accuracy=tool_accuracy,
        response_accuracy=not response_failures,
        response_failures=[failure for failure in response_failures if failure],
        end_to_end_seconds=round(elapsed, 3),
        llm_seconds=round(client.seconds, 3),
        llm_calls=client.calls,
        target_tool_seconds=(round(sum(target_times), 3) if target_times else None),
        answer_preview=answer[:500],
        error=error,
    )


def _rate(results: list[CaseResult], attribute: str) -> float:
    return round(sum(bool(getattr(item, attribute)) for item in results) / len(results), 3)


def _response_time(cases: list[PromptCase], results: list[CaseResult]) -> dict[str, Any]:
    prompts: list[dict[str, Any]] = []
    for case in cases:
        runs = [item for item in results if item.case_id == case.case_id]
        tool_times = [
            item.target_tool_seconds
            for item in runs
            if item.target_tool_seconds is not None
        ]
        prompts.append({
            "case_id": case.case_id,
            "tool": case.tool,
            "runs": len(runs),
            "end_to_end_seconds": round(
                statistics.mean(item.end_to_end_seconds for item in runs), 3
            ),
            "llm_seconds": round(statistics.mean(item.llm_seconds for item in runs), 3),
            "tool_seconds": (
                round(statistics.mean(tool_times), 3) if tool_times else None
            ),
            "llm_calls": sum(item.llm_calls for item in runs),
        })
    total = sum(item["end_to_end_seconds"] for item in prompts)
    return {
        "prompts": prompts,
        "prompt_count": len(prompts),
        "total_seconds": round(total, 3),
        "mean_seconds": round(total / len(prompts), 3),
    }


def _summary(results: list[CaseResult]) -> dict[str, Any]:
    by_tool: dict[str, dict[str, Any]] = {}
    for tool in sorted({item.tool for item in results}):
        selected = [item for item in results if item.tool == tool]
        by_tool[tool] = {
            "runs": len(selected),
            "tool_accuracy": _rate(selected, "tool_accuracy"),
            "response_accuracy": _rate(selected, "response_accuracy"),
            "mean_response_seconds": round(
                statistics.mean(item.end_to_end_seconds for item in selected), 3
            ),
        }
    return {
        "runs": len(results),
        "tool_accuracy": _rate(results, "tool_accuracy"),
        "response_accuracy": _rate(results, "response_accuracy"),
        "pass_rate": round(
            sum(item.tool_accuracy and item.response_accuracy for item in results)
            / len(results),
            3,
        ),
        "by_tool": by_tool,
    }


def _print_response_time(response_time: dict[str, Any]) -> None:
    print("\nResponse time (seconds; case setup excluded)")
    print(f"  {'case':<38} {'end-to-end':>10} {'llm':>8} {'tool':>8}")
    for item in response_time["prompts"]:
        tool = item["tool_seconds"]
        print(
            f"  {item['case_id']:<38} {item['end_to_end_seconds']:>10.3f} "
            f"{item['llm_seconds']:>8.3f} "
            f"{'-' if tool is None else f'{tool:.3f}':>8}"
        )
    print(f"  {'total':<38} {response_time['total_seconds']:>10.3f}")
    print(f"  {'mean':<38} {response_time['mean_seconds']:>10.3f}")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate campaign-email MCP tool and response accuracy"
    )
    parser.add_argument(
        "--dataset", choices=sorted(DATASETS), default=None,
        help="Expected loaded dataset; default is detection by table counts",
    )
    parser.add_argument(
        "--repeats", type=int, default=5,
        help="Runs per prompt for timing and model variance (default: 5)",
    )
    parser.add_argument(
        "--mcp-url", default=None,
        help="Use a running FastMCP URL instead of the in-process server",
    )
    parser.add_argument(
        "--delay-seconds", type=float, default=0.0,
        help="Delay between runs to reduce provider rate pressure",
    )
    parser.add_argument(
        "--min-pass-rate", type=float, default=1.0,
        help="Exit non-zero when combined accuracy falls below this value",
    )
    parser.add_argument(
        "--case", action="append", default=None, metavar="CASE_ID",
        help="Run only the named case; may be supplied more than once",
    )
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    if not 1 <= args.repeats <= 20:
        raise SystemExit("--repeats must be between 1 and 20")
    if args.delay_seconds < 0:
        raise SystemExit("--delay-seconds must not be negative")
    if not 0 <= args.min_pass_rate <= 1:
        raise SystemExit("--min-pass-rate must be between 0 and 1")

    # Evaluation must never invoke the external GWM adapter.
    os.environ["EMAIL_DELIVERY_MODE"] = "mock"
    get_settings.cache_clear()
    settings = get_settings()
    if settings.email_delivery_mode != "mock":
        raise SystemExit("Campaign-email evaluation requires EMAIL_DELIVERY_MODE=mock")
    if not settings.llm_configured:
        raise SystemExit("GROQ_API_KEY is not configured in backend/.env")

    dataset = _resolve_dataset(args.dataset)
    cases = list(PROMPT_CASES)
    if args.case:
        known = {case.case_id for case in cases}
        unknown = sorted(set(args.case) - known)
        if unknown:
            raise SystemExit(f"Unknown case(s): {unknown}; available: {sorted(known)}")
        cases = [case for case in cases if case.case_id in args.case]

    print(
        f"Evaluating campaign email tools on {dataset.name}: "
        f"{len(cases)} prompts x {args.repeats} runs (mock delivery)"
    )
    transport = args.mcp_url or _in_process_mcp_server()
    results: list[CaseResult] = []
    for case in cases:
        for run in range(1, args.repeats + 1):
            result = _run_case(case, run, settings, transport)
            results.append(result)
            status = "PASS" if result.tool_accuracy and result.response_accuracy else "FAIL"
            print(
                f"[{status}] {case.case_id} run {run}: "
                f"tools={result.actual_tools} e2e={result.end_to_end_seconds:.3f}s "
                f"llm={result.llm_seconds:.3f}s tool={result.target_tool_seconds}"
                + (f" failures={result.response_failures}" if result.response_failures else "")
            )
            if args.delay_seconds:
                time.sleep(args.delay_seconds)

    summary = _summary(results)
    response_time = _response_time(cases, results)
    print("\nAccuracy summary")
    print(json.dumps(summary, indent=2))
    _print_response_time(response_time)

    RESULTS_DIR.mkdir(exist_ok=True)
    output = RESULTS_DIR / (
        f"campaign_email_{dataset.name}_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.json"
    )
    output.write_text(
        json.dumps(
            {
                "data_source": "synthetic",
                "delivery_mode": "mock",
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
