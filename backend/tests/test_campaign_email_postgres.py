"""Opt-in PostgreSQL test for email confirmation and contact-event persistence."""

from pathlib import Path
import os
from types import SimpleNamespace
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest

from app import config
from app.campaigns import email as email_module
from app.campaigns.email import PrepareCampaignEmailArguments
from app.campaigns.repository import DEMO_FA, RequestScope
from app.integrations.gwm_email import MockEmailTransport


TABLES = Path(__file__).parents[1] / "tables"
CREATE = TABLES / "create"
MOCK = TABLES / "mock_data"


@pytest.fixture
def email_database(monkeypatch):
    database_url = os.environ.get("PULSE_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set PULSE_TEST_DATABASE_URL to a local disposable PostgreSQL database")
    schema = "pulse_email_test_" + uuid4().hex
    with psycopg.connect(database_url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        scoped_url = make_conninfo(database_url, options="-c search_path=" + schema)
        try:
            with psycopg.connect(scoped_url, autocommit=True) as connection:
                for filename in (
                    "create_campaign_chat_sessions.sql",
                    "create_mock_campaign.sql",
                    "create_mock_client.sql",
                    "create_mock_campaign_advisor.sql",
                    "create_campaign_email_send.sql",
                    "create_mock_campaign_contact_event.sql",
                ):
                    connection.execute((CREATE / filename).read_text())
                for filename in (
                    "mock_campaign.sql", "mock_client.sql", "mock_campaign_advisor.sql"
                ):
                    connection.execute((MOCK / filename).read_text())
                connection.execute(
                    "INSERT INTO campaign_chat_sessions (fa_id, session_id) VALUES (%s, %s)",
                    (DEMO_FA, "session-email-test"),
                )
                runtime_settings = SimpleNamespace(
                    database_url=scoped_url, email_delivery_mode="mock"
                )
                monkeypatch.setattr(config, "get_settings", lambda: runtime_settings)
                monkeypatch.setattr(email_module, "get_settings", lambda: runtime_settings)
                yield connection
        finally:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def metadata(message="Draft an email"):
    return {
        "pulse_scope": {"fa_id": DEMO_FA, "tenant_id": "pulse-demo"},
        "campaign_id": "camp-1",
        "session_id": "session-email-test",
        "latest_user_message": message,
    }


def test_confirmed_mock_email_records_each_recipient_once(email_database):
    preview = email_module.prepare_campaign_email(
        PrepareCampaignEmailArguments(
            subject="Legacy protection review",
            body="Hello {{client_name}}, this is educational information only. "
                 "Individual circumstances and suitability require adviser review.",
        ),
        metadata(),
    )
    assert preview["prepared"] is True
    assert [item["contact_id"] for item in preview["recipients"]] == [
        "client-001", "client-003"
    ]
    assert {item["contact_id"] for item in preview["excluded_recipients"]} == {
        "client-002", "client-012"
    }

    confirmed = email_module.confirm_campaign_email(
        metadata(preview["confirmation_phrase"]), MockEmailTransport()
    )
    assert confirmed["status"] == "sent"
    assert confirmed["successful_count"] == 2
    assert confirmed["contact_events_recorded"] == 2
    rows = email_database.execute(
        """
        SELECT contact_id, engagement_status, channel, delivery_mode, send_batch_id
        FROM mock_campaign_contact_event ORDER BY contact_id
        """
    ).fetchall()
    assert [(row[0], row[1], row[2], row[3]) for row in rows] == [
        ("client-001", 0, "email", "mock"),
        ("client-003", 0, "email", "mock"),
    ]
    assert all(row[4] == preview["send_batch_id"] for row in rows)

    repeated = email_module.confirm_campaign_email(
        metadata(preview["confirmation_phrase"]), MockEmailTransport()
    )
    assert repeated["repeated_confirmation"] is True
    assert email_database.execute(
        "SELECT count(*) FROM mock_campaign_contact_event"
    ).fetchone()[0] == 2


def test_confirmation_must_match_latest_preview_exactly(email_database):
    preview = email_module.prepare_campaign_email(
        PrepareCampaignEmailArguments(subject="Review", body="Educational review."),
        metadata(),
    )
    result = email_module.confirm_campaign_email(
        metadata("Please send it"), MockEmailTransport()
    )
    assert result["error_code"] == "confirmation_required"
    assert email_database.execute(
        "SELECT status FROM campaign_email_send WHERE send_batch_id = %s",
        (preview["send_batch_id"],),
    ).fetchone()[0] == "prepared"
    assert email_database.execute(
        "SELECT count(*) FROM mock_campaign_contact_event"
    ).fetchone()[0] == 0
