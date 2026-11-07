import json
from datetime import date
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.campaigns.email import (
    PrepareCampaignEmailArguments,
    render_campaign_email,
)
from app.campaigns.repository import Campaign, Criteria, DEMO_FA, RequestScope
from app.config import Settings
from app.integrations.gwm_email import GWMEmailTransport, MockEmailTransport, build_email_transport
from app.llm.orchestrator import ChatOrchestrator, SYSTEM_PROMPT
from app.store import ChatHistoryItem
import app.llm.orchestrator as orchestrator_module


def settings():
    return Settings(_env_file=None, groq_api_key="test-key", email_delivery_mode="mock")


def test_email_arguments_reject_duplicate_recipients_and_blank_content():
    with pytest.raises(ValidationError):
        PrepareCampaignEmailArguments(
            campaign_id="camp-1",
            recipient_ids=["client-001", "client-001"],
            subject="Subject",
            body="Message",
        )
    with pytest.raises(ValidationError):
        PrepareCampaignEmailArguments(
            campaign_id="camp-1", subject="   ", body="Message"
        )


def test_mock_transport_is_explicit_and_deterministic():
    transport = build_email_transport(settings())
    assert isinstance(transport, MockEmailTransport)
    result = transport.send(
        recipient="demo@example.test", subject="Review", message="Educational message"
    )
    assert result.success is True
    assert result.provider_status == "mock-accepted"


def test_preview_renderer_shows_content_recipients_and_exact_confirmation():
    rendered = render_campaign_email({
        "type": "campaign_email_preview",
        "delivery_mode": "mock",
        "campaign_name": "Legacy Protection Refresh",
        "campaign_id": "camp-1",
        "subject": "Protection review",
        "body": "Hello {{client_name}}",
        "recipients": [{
            "contact_id": "client-001",
            "name": "Demo Client A",
            "email": "demo.client.a@example.test",
        }],
        "excluded_recipients": [{
            "contact_id": "client-002", "reason": "email consent is not recorded"
        }],
        "confirmation_phrase": "CONFIRM EMAIL ABC234",
        "expires_at": "2026-10-15T12:00:00Z",
    })
    assert "Protection review" in rendered
    assert "Demo Client A" in rendered
    assert "Client 2" in rendered
    assert "client-001" not in rendered
    assert "client-002" not in rendered
    assert "demo.client.a@example.test" not in rendered
    assert "CONFIRM EMAIL ABC234" in rendered
    assert "simulated" in rendered


class ConfirmationRegistry:
    def __init__(self):
        self.bound = None
        self.executed = []

    def bind_scope(self, scope, campaign_id=None, session_id=None, latest_user_message=None):
        self.bound = (scope, campaign_id, session_id, latest_user_message)
        return self

    def schemas(self):
        raise AssertionError("Exact confirmation must bypass the LLM and schema discovery")

    def execute(self, name, arguments_json):
        self.executed.append((name, json.loads(arguments_json)))
        return json.dumps({
            "type": "campaign_email_result",
            "send_batch_id": "email-1",
            "campaign_id": "camp-1",
            "status": "sent",
            "sent": True,
            "successful_count": 1,
            "failed_count": 0,
            "results": [{
                "contact_id": "client-001", "name": "Demo Client A",
                "success": True, "message": "Simulated delivery accepted",
            }],
            "repeated_confirmation": False,
            "campaign_members_updated": 1,
        })


def test_exact_confirmation_is_server_routed_without_an_llm_call():
    provider = SimpleNamespace()
    registry = ConfirmationRegistry()
    orchestrator = ChatOrchestrator(provider, settings(), registry)
    result = orchestrator.run(
        "CONFIRM EMAIL ABC234", [], scope=RequestScope(DEMO_FA),
        campaign_id="camp-1", session_id="session-1",
    )
    assert registry.bound[3] == "CONFIRM EMAIL ABC234"
    assert registry.executed == [("confirm_campaign_email", {})]
    assert "Campaign email result" in result
    assert "Campaign members updated:** 1" in result


class PreviewRegistry:
    def bind_scope(self, scope, campaign_id=None, session_id=None, latest_user_message=None):
        return self

    def schemas(self):
        return [{
            "type": "function",
            "function": {
                "name": "prepare_campaign_email",
                "description": "Prepare email",
                "parameters": {"type": "object", "properties": {}},
            },
        }]

    def execute(self, name, arguments_json):
        assert name == "prepare_campaign_email"
        arguments = json.loads(arguments_json)
        assert arguments["subject"] == "Protection review"
        assert arguments["signoff_name"] == "Steven"
        assert arguments["campaign_id"] == "camp-1"
        return json.dumps({
            "type": "campaign_email_preview",
            "delivery_mode": "mock",
            "campaign_name": "Legacy Protection Refresh",
            "campaign_id": "camp-1",
            "subject": "Protection review",
            "body": "Educational information only.",
            "recipients": [{
                "contact_id": "client-001", "name": "Demo Client A",
                "email": "demo.client.a@example.test",
            }],
            "excluded_recipients": [],
            "confirmation_phrase": "CONFIRM EMAIL ABC234",
            "expires_at": "2026-10-15T12:00:00Z",
        })


class PreviewProvider:
    def __init__(self):
        self.calls = 0
        self.messages = None
        self.tools = None

    def create_chat_completion(self, messages, tools):
        self.calls += 1
        self.messages = messages
        self.tools = tools
        call = SimpleNamespace(
            id="email-preview-1",
            function=SimpleNamespace(
                name="prepare_campaign_email",
                arguments=json.dumps({
                    "subject": "Protection review",
                    "body": "Educational information only.",
                }),
            ),
        )
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=None, tool_calls=[call])
        )])


def campaign():
    return Campaign(
        campaign_id="camp-1",
        name="Legacy Protection Refresh",
        criteria=Criteria(age_groups=("50-59",)),
        status="active",
        start_date=date(2026, 1, 1),
        end_date=date(2027, 1, 1),
        campaign_code="LEGACY",
        description="Educational legacy-planning review.",
    )


def test_email_preview_uses_one_compact_model_call(monkeypatch):
    monkeypatch.setattr(orchestrator_module, "get_campaign", lambda *_: campaign())
    monkeypatch.setattr(
        orchestrator_module, "latest_email_draft_context", lambda *_: None
    )
    provider = PreviewProvider()
    orchestrator = ChatOrchestrator(provider, settings(), PreviewRegistry())
    history = [ChatHistoryItem(
        "2026-11-01T00:00:00Z", False,
        "What name would you like me to use in the email sign-off?",
    )]
    result = orchestrator.run(
        "Steven\nFinancial Advisor", history, scope=RequestScope(DEMO_FA),
        campaign_id="camp-1", session_id="session-1",
    )
    assert provider.calls == 1
    assert len(provider.messages) == 2
    assert [tool["function"]["name"] for tool in provider.tools] == [
        "prepare_campaign_email"
    ]
    assert "Legacy Protection Refresh" in provider.messages[0]["content"]
    assert "Financial Advisor" not in provider.messages[0]["content"]
    assert "Review campaign email" in result
    assert "CONFIRM EMAIL ABC234" in result


def test_email_fast_path_asks_for_campaign_without_model_call():
    provider = SimpleNamespace()
    orchestrator = ChatOrchestrator(provider, settings(), PreviewRegistry())
    result = orchestrator.run(
        "Draft an email for clients", [], scope=RequestScope(DEMO_FA),
        campaign_id=None, session_id="session-1",
    )
    assert "Which campaign" in result


def test_email_fast_path_asks_for_signoff_without_model_call(monkeypatch):
    monkeypatch.setattr(orchestrator_module, "get_campaign", lambda *_: campaign())
    monkeypatch.setattr(
        orchestrator_module, "latest_email_draft_context", lambda *_: None
    )
    provider = SimpleNamespace()
    orchestrator = ChatOrchestrator(provider, settings(), PreviewRegistry())
    result = orchestrator.run(
        "Draft an email", [], scope=RequestScope(DEMO_FA),
        campaign_id="camp-1", session_id="session-1",
    )
    assert "What name" in result
    assert "Legacy Protection Refresh" in result


def test_prompt_requires_preview_consent_and_exact_confirmation():
    assert "prepare_campaign_email" in SYSTEM_PROMPT
    assert "exact confirmation phrase" in SYSTEM_PROMPT
    assert "email consent" in SYSTEM_PROMPT
    assert "ask what name the adviser wants in the sign-off" in SYSTEM_PROMPT
    assert "Never infer a sign-off" in SYSTEM_PROMPT


def test_gwm_transport_matches_supplied_send_email_contract(monkeypatch):
    captured = {}

    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def read(self, limit):
            assert limit == 64_000
            return b"Email accepted"

    def urlopen(outbound, timeout):
        captured["request"] = outbound
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("app.integrations.gwm_email.request.urlopen", urlopen)
    transport = GWMEmailTransport(Settings(
        _env_file=None,
        email_delivery_mode="gwm",
        gwm_email_base_url="https://email.example.test",
        gwm_email_sender="advisor@example.test",
        gwm_email_timeout_seconds=12,
    ))
    result = transport.send(
        recipient="client@example.test",
        subject="Your campaign update",
        message="<p>Dear Client,</p>",
    )
    outbound = captured["request"]
    headers = {name.lower(): value for name, value in outbound.header_items()}
    assert outbound.full_url.endswith("/EmailNotification/SendEmail")
    assert headers["accept"] == "text/plain"
    assert json.loads(outbound.data) == {
        "senderEmail": "advisor@example.test",
        "recipientEmail": "client@example.test",
        "subject": "Your campaign update",
        "message": "<p>Dear Client,</p>",
        "base64Attachment": "",
        "contentIDs": [""],
        "cc": "",
    }
    assert captured["timeout"] == 12
    assert result.success is True
