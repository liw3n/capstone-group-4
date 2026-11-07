"""Opt-in integration checks in disposable schemas, never the app's live schema."""
from datetime import date
import json
import os
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest

from app import config, main
from app.campaigns import clock, recommendation_lists as lists
from app.campaigns.repository import RequestScope
from app.tools.campaign import execute_recommendation

ADVISER = 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'
CAMPAIGN = 'b2222222-2222-2222-2222-222222222222'
SCOPE = RequestScope(ADVISER)
META = {'pulse_scope': {'fa_id': ADVISER, 'tenant_id': 'pulse-demo'}}
TABLES = Path(__file__).parents[1] / 'tables'


@pytest.fixture
def database(monkeypatch):
    url = os.environ.get('PULSE_RECOMMENDATION_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Set PULSE_RECOMMENDATION_TEST_DATABASE_URL for disposable-schema checks')
    schema = 'pulse_recommendation_test_' + uuid4().hex
    settings = config.get_settings()
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        scoped_url = make_conninfo(url, options=f'-c search_path={schema},public')
        try:
            with psycopg.connect(scoped_url, autocommit=True) as connection:
                for filename in ('create_mock_user_account.sql', 'create_campaign.sql', 'create_contact.sql',
                                 'create_campaign_recommendation_lists.sql', 'create_campaign_recommendation_lists.sql'):
                    connection.execute((TABLES / 'create' / filename).read_text())
                for filename in ('mock_user_account.sql', 'mock_contact.sql', 'mock_campaign.sql'):
                    connection.execute((TABLES / 'mock_data' / filename).read_text())
                connection.execute("""INSERT INTO contact
                    (tenant_id, contact_id, contact_type, full_name, mobile, created_by_user_id)
                    SELECT %s, gen_random_uuid(), 'Client', 'Extra synthetic ' || i, 'synthetic', %s
                    FROM generate_series(1, 25) AS i""", (ADVISER, ADVISER))
                connection.execute("UPDATE campaign SET audience_criteria = '{}'::jsonb WHERE campaign_id = %s", (CAMPAIGN,))
                local = settings.model_copy(update={'database_url': scoped_url})
                monkeypatch.setattr(config, 'get_settings', lambda: local)
                monkeypatch.setattr(lists, 'get_settings', lambda: local)
                monkeypatch.setattr(clock, 'current_date', lambda: date(2026, 11, 7))
                yield connection
        finally:
            admin.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


def test_full_snapshot_survives_connections_and_downloads_all_125_clients(database, monkeypatch):
    preview = execute_recommendation(CAMPAIGN, 100, META)
    assert preview['matched_count'] == 125 and len(preview['clients']) == 10
    list_id = UUID(preview['list_id'])
    stored = database.execute('SELECT payload FROM campaign_recommendation_lists WHERE list_id = %s', (list_id,)).fetchone()[0]
    assert len(stored['clients']) == 125
    assert stored['clients'][-1]['contact_id'] not in json.dumps(preview)
    # New connection through load_list, then both API aliases; no provider needed.
    assert len(lists.load_list(SCOPE, list_id)['clients']) == 125
    monkeypatch.setattr(main, 'get_orchestrator', lambda: pytest.fail('Download must not call Groq'))
    for prefix in ('/chat', '/api/chat'):
        response = TestClient(main.app).get(f'{prefix}/recommendation-lists/{list_id}?fa_id={ADVISER}')
        assert response.status_code == 200 and len(response.json()['clients']) == 125


def test_cross_adviser_tenant_and_expired_downloads_are_blocked(database):
    list_id = UUID(execute_recommendation(CAMPAIGN, 100, META)['list_id'])
    for scope in (RequestScope(str(uuid4())), RequestScope(ADVISER, str(uuid4()))):
        with pytest.raises(lists.RecommendationListNotFound):
            lists.load_list(scope, list_id)
    database.execute("UPDATE campaign_recommendation_lists SET expires_at = now() - interval '1 second' WHERE list_id = %s", (list_id,))
    response = TestClient(main.app).get(f'/api/chat/recommendation-lists/{list_id}?fa_id={ADVISER}')
    assert response.status_code == 410


def test_current_access_is_rechecked_before_export(database):
    list_id = UUID(execute_recommendation(CAMPAIGN, 100, META)['list_id'])
    database.execute('UPDATE contact SET assigned_to_user_id = %s WHERE full_name = %s', (uuid4(), 'Demo Client A'))
    with pytest.raises(lists.RecommendationListExpired, match='access has changed'):
        lists.load_list(SCOPE, list_id)
    database.execute('UPDATE campaign SET is_deleted = TRUE WHERE campaign_id = %s', (CAMPAIGN,))
    with pytest.raises(lists.RecommendationListNotFound):
        lists.load_list(SCOPE, list_id)
