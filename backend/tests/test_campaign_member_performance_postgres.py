"""Opt-in PostgreSQL checks for adviser-scoped campaign_member performance."""
from datetime import datetime
from pathlib import Path
import os
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest

from app import config
from app.campaigns import repository
from app.campaigns.repository import RequestScope

TABLES = Path(__file__).parents[1] / "tables"
CREATE = TABLES / "create"
SEED = TABLES / "mock_data"
FA = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
OTHER_FA = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a12"
CAMPAIGN = "b1111111-1111-1111-1111-111111111111"
NOW = datetime(2026, 10, 12, 18, tzinfo=ZoneInfo("Asia/Singapore"))


@pytest.fixture
def database(monkeypatch):
    database_url = os.environ.get("PULSE_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set PULSE_TEST_DATABASE_URL to a disposable PostgreSQL database")
    schema = "pulse_member_test_" + uuid4().hex
    with psycopg.connect(database_url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        scoped_url = make_conninfo(database_url, options="-c search_path=" + schema)
        try:
            with psycopg.connect(scoped_url, autocommit=True) as connection:
                for filename in (
                    "create_mock_user_account.sql", "create_campaign.sql",
                    "create_contact.sql", "create_campaign_member.sql",
                ):
                    connection.execute((CREATE / filename).read_text())
                for filename in (
                    "mock_user_account.sql", "mock_contact.sql",
                    "mock_campaign.sql", "mock_campaign_member.sql",
                ):
                    connection.execute((SEED / filename).read_text())
                monkeypatch.setattr(config, "get_settings",
                                    lambda: SimpleNamespace(database_url=scoped_url))
                yield connection
        finally:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_member_email_totals_and_week_boundaries(database):
    scope = RequestScope(fa_id=FA, tenant_id=FA)
    current_week = datetime(2026, 10, 12, tzinfo=NOW.tzinfo)
    last_week = datetime(2026, 10, 5, tzinfo=NOW.tzinfo)
    result = repository.get_campaign_member_metrics(
        scope, CAMPAIGN, NOW, current_week, last_week, last_week, current_week
    )
    assert result["campaign_members_total"] == 5
    assert result["clients_emailed_total"] == 5
    assert result["email_sends_total"] == 7
    assert result["members_added_this_week"] == 0
    assert result["members_added_last_week"] == 0

    second = repository.get_campaign_member_metrics(
        scope, "b2222222-2222-2222-2222-222222222222",
        NOW, current_week, last_week, last_week, current_week
    )
    assert second["campaign_members_total"] == 3
    assert second["members_added_this_week"] == 1
    assert second["members_added_last_week"] == 2
    assert second["members_added_requested_week"] == 2


def test_ranking_includes_zero_campaigns_and_excludes_other_adviser(database):
    scope = RequestScope(fa_id=FA, tenant_id=FA)
    rows = repository.rank_campaigns_by_member_metric(
        scope, "clients_emailed", None, NOW, NOW
    )
    assert [(str(row["campaign_id"]), row["count_value"]) for row in rows] == [
        ("b1111111-1111-1111-1111-111111111111", 5),
        ("b2222222-2222-2222-2222-222222222222", 3),
        ("b3333333-3333-3333-3333-333333333333", 0),
    ]
    database.execute(
        "INSERT INTO user_account (tenant_id, user_id) VALUES (%s, %s)",
        (FA, OTHER_FA),
    )
    database.execute(
        """UPDATE campaign_member SET added_by_user_id = %s
           WHERE tenant_id = %s AND campaign_id = %s
           AND contact_id = 'd0000000-0000-0000-0000-000000000001'""",
        (OTHER_FA, FA, CAMPAIGN),
    )
    scoped = repository.get_campaign_member_metrics(
        scope, CAMPAIGN, NOW, NOW, NOW
    )
    assert scoped["campaign_members_total"] == 4
    assert repository.rank_campaigns_by_member_metric(
        RequestScope(fa_id=OTHER_FA, tenant_id=FA), "clients_emailed", None, NOW, NOW
    ) == ()
