import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.campaigns.email import (
    PrepareCampaignEmailArguments,
    render_campaign_email,
)
from app.campaigns.repository import DEMO_FA, RequestScope
from app.config import Settings
from app.integrations.gwm_email import MockEmailTransport, build_email_transport
from app.llm.orchestrator import ChatOrchestrator, SYSTEM_PROMPT


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
    assert "client-002" in rendered
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
            "contact_events_recorded": 1,
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
    assert "Contact events recorded:** 1" in result


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
        assert json.loads(arguments_json)["subject"] == "Protection review"
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

    def create_chat_completion(self, messages, tools):
        self.calls += 1
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


def test_email_preview_is_rendered_directly_after_the_model_tool_call():
    provider = PreviewProvider()
    orchestrator = ChatOrchestrator(provider, settings(), PreviewRegistry())
    result = orchestrator.run(
        "Draft an email", [], scope=RequestScope(DEMO_FA),
        campaign_id="camp-1", session_id="session-1",
    )
    assert provider.calls == 1
    assert "Review campaign email" in result
    assert "CONFIRM EMAIL ABC234" in result


def test_prompt_requires_preview_consent_and_exact_confirmation():
    assert "prepare_campaign_email" in SYSTEM_PROMPT
    assert "exact confirmation phrase" in SYSTEM_PROMPT
    assert "email consent" in SYSTEM_PROMPT
