"""Opt-in PostgreSQL checks for confirmed email and member persistence."""

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
from app.integrations.gwm_email import MockEmailTransport


TABLES = Path(__file__).parents[1] / "tables"
CREATE = TABLES / "create"
MOCK = TABLES / "mock_data"
ADVISER = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
CAMPAIGN = "b2222222-2222-2222-2222-222222222222"
SESSION = "session-email-test"


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
                    "create_mock_user_account.sql",
                    "create_campaign.sql",
                    "create_contact.sql",
                    "create_campaign_member.sql",
                    "create_campaign_email_send.sql",
                ):
                    connection.execute((CREATE / filename).read_text())
                for filename in (
                    "mock_user_account.sql", "mock_contact.sql", "mock_campaign.sql"
                ):
                    connection.execute((MOCK / filename).read_text())
                connection.execute(
                    "INSERT INTO campaign_chat_sessions (fa_id, session_id) VALUES (%s, %s)",
                    (ADVISER, SESSION),
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
        "pulse_scope": {"fa_id": ADVISER, "tenant_id": "pulse-demo"},
        "campaign_id": CAMPAIGN,
        "session_id": SESSION,
        "latest_user_message": message,
    }


def test_confirmed_mock_email_updates_members_and_campaign_once(email_database):
    preview = email_module.prepare_campaign_email(
        PrepareCampaignEmailArguments(
            subject="Legacy protection review",
            body="Hello {{client_name}}, this is educational information only. "
                 "Individual circumstances and suitability require adviser review.",
            signoff_name="Steven Raynaldi",
        ),
        metadata(),
    )
    assert preview["prepared"] is True
    recipient_ids = [item["contact_id"] for item in preview["recipients"]]
    assert recipient_ids
    send_runs_before = email_database.execute(
        "SELECT email_send_runs FROM campaign WHERE tenant_id = %s AND campaign_id = %s",
        (ADVISER, CAMPAIGN),
    ).fetchone()[0]

    confirmed = email_module.confirm_campaign_email(
        metadata(preview["confirmation_phrase"]), MockEmailTransport()
    )
    assert confirmed["status"] == "sent"
    assert confirmed["successful_count"] == len(recipient_ids)
    assert confirmed["campaign_members_updated"] == len(recipient_ids)
    rows = email_database.execute(
        """SELECT contact_id::text, email_send_count, emailed_at
           FROM campaign_member
           WHERE tenant_id = %s AND campaign_id = %s
           ORDER BY contact_id""",
        (ADVISER, CAMPAIGN),
    ).fetchall()
    assert [row[0] for row in rows] == sorted(recipient_ids)
    assert all(row[1] == 1 and row[2] is not None for row in rows)
    assert email_database.execute(
        "SELECT email_send_runs FROM campaign WHERE tenant_id = %s AND campaign_id = %s",
        (ADVISER, CAMPAIGN),
    ).fetchone()[0] == send_runs_before + 1

    repeated = email_module.confirm_campaign_email(
        metadata(preview["confirmation_phrase"]), MockEmailTransport()
    )
    assert repeated["repeated_confirmation"] is True
    assert email_database.execute(
        "SELECT sum(email_send_count) FROM campaign_member WHERE campaign_id = %s",
        (CAMPAIGN,),
    ).fetchone()[0] == len(recipient_ids)

    discarded = email_module.discard_campaign_email(metadata("Cancel email"))
    assert discarded["discarded"] is False
    assert email_database.execute(
        "SELECT status FROM campaign_email_send WHERE send_batch_id = %s",
        (preview["send_batch_id"],),
    ).fetchone()[0] == "sent"


def test_confirmation_must_match_latest_preview_exactly(email_database):
    preview = email_module.prepare_campaign_email(
        PrepareCampaignEmailArguments(
            subject="Review", body="Educational review.", signoff_name="Steven Raynaldi"
        ),
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
        "SELECT count(*) FROM campaign_member"
    ).fetchone()[0] == 0


def test_discard_invalidates_preview_and_prevents_confirmation(email_database):
    preview = email_module.prepare_campaign_email(
        PrepareCampaignEmailArguments(
            subject="Review", body="Educational review.", signoff_name="Steven Raynaldi"
        ),
        metadata(),
    )

    discarded = email_module.discard_campaign_email(metadata("Discard this email"))

    assert discarded == {
        "type": "campaign_email_discarded",
        "discarded": True,
        "send_batch_id": preview["send_batch_id"],
        "campaign_id": CAMPAIGN,
        "sent": False,
    }
    assert email_database.execute(
        "SELECT status FROM campaign_email_send WHERE send_batch_id = %s",
        (preview["send_batch_id"],),
    ).fetchone()[0] == "invalidated"

    confirmation = email_module.confirm_campaign_email(
        metadata(preview["confirmation_phrase"]), MockEmailTransport()
    )
    assert confirmation["error_code"] == "invalid_confirmation"
    assert email_database.execute(
        "SELECT count(*) FROM campaign_member"
    ).fetchone()[0] == 0
