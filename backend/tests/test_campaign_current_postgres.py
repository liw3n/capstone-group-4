"""Opt-in current-schema checks in an isolated schema, never public demo tables."""
from datetime import date
import os
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest

from app import config
from app.campaigns import repository
from app.campaigns.matching import recommend_clients_for_campaign
from app.campaigns.repository import CampaignInactive, RequestScope
from app.contacts.catalog import list_contacts
from app.tools.campaign_lookup import execute_resolve_campaign

TABLES = Path(__file__).parents[1] / 'tables'
ADVISER = 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'
FIRST_HOME = 'b2222222-2222-2222-2222-222222222222'
LEGACY = 'b1111111-1111-1111-1111-111111111111'


@pytest.fixture
def current_database(monkeypatch):
    url = os.environ.get('PULSE_CURRENT_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Set PULSE_CURRENT_TEST_DATABASE_URL for isolated current-schema checks')
    schema = 'pulse_current_test_' + uuid4().hex
    settings = config.get_settings()
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        scoped_url = make_conninfo(url, options=f'-c search_path={schema},public')
        try:
            with psycopg.connect(scoped_url, autocommit=True) as connection:
                for name in ('create_mock_user_account.sql', 'create_campaign.sql', 'create_contact.sql'):
                    connection.execute((TABLES / 'create' / name).read_text())
                for name in ('mock_user_account.sql', 'mock_contact.sql', 'mock_campaign.sql'):
                    connection.execute((TABLES / 'mock_data' / name).read_text())
                monkeypatch.setattr(config, 'get_settings', lambda: settings.model_copy(
                    update={'database_url': scoped_url}))
                yield connection
        finally:
            admin.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


def test_discovery_and_matching_use_current_rows_and_crm_enrichment(current_database):
    scope = RequestScope(ADVISER)
    campaigns = repository.list_active_campaigns(scope, date(2026, 10, 28))
    assert len(campaigns) == 3
    assert {row.campaign_id for row in repository.list_active_campaigns(
        scope, date(2026, 10, 28), campaign_names=['FIRST HOME STARTER BUNDLE'])} == {FIRST_HOME}
    result = recommend_clients_for_campaign(FIRST_HOME, scope)
    assert result['evaluated_count'] == 12
    assert result['matched_count'] == 3 and result['incomplete_count'] == 1
    assert [client['name'] for client in result['clients']] == [
        'Demo Client F', 'Demo Client G', 'Demo Client H']
    crm_ids = {str(contact['id']) for contact in list_contacts(scope)}
    assert all(client['contact_id'] in crm_ids for client in result['clients'])
    # Current portfolio mock values are below the legacy campaign's cash floor.
    assert recommend_clients_for_campaign(LEGACY, scope)['matched_count'] == 0
    assert repository.get_campaign_by_name('first home starter bundle', scope).campaign_id == FIRST_HOME
    resolved = execute_resolve_campaign({'campaign_name': 'first home starter bundle campaign'},
                                       {'pulse_scope': {'fa_id': ADVISER, 'tenant_id': 'pulse-demo'}})
    assert resolved['status'] == 'matched' and resolved['campaign_id'] == FIRST_HOME
    assert 'table' not in resolved and 'criteria' not in resolved


def test_live_criteria_status_and_soft_delete_are_observed(current_database):
    scope = RequestScope(ADVISER)
    current_database.execute("""UPDATE campaign SET audience_criteria =
        '{"ageGroups":["under35","35-44"],"genders":["Female"],"cashBands":["under50k","50k-250k"]}'::jsonb
        WHERE campaign_id = %s""", (FIRST_HOME,))
    result = recommend_clients_for_campaign(FIRST_HOME, scope)
    assert [client['name'] for client in result['clients']] == ['Demo Client F', 'Demo Client H']
    current_database.execute('UPDATE campaign SET status = %s WHERE campaign_id = %s', ('paused', FIRST_HOME))
    with pytest.raises(CampaignInactive):
        recommend_clients_for_campaign(FIRST_HOME, scope)
    assert repository.list_active_campaigns(scope, date(2026, 10, 28), [FIRST_HOME]) == ()
    current_database.execute('UPDATE campaign SET is_deleted = TRUE WHERE campaign_id = %s', (FIRST_HOME,))
    with pytest.raises(repository.CampaignUnavailable):
        repository.get_campaign(FIRST_HOME, scope)


def test_other_adviser_assignment_and_explicit_tenant_are_excluded(current_database):
    scope = RequestScope(ADVISER)
    other = str(uuid4())
    current_database.execute('UPDATE contact SET assigned_to_user_id = %s WHERE full_name = %s',
                             (other, 'Demo Client G'))
    assert recommend_clients_for_campaign(FIRST_HOME, scope)['matched_count'] == 2
    current_database.execute('UPDATE contact SET is_deleted = TRUE WHERE full_name = %s', ('Demo Client F',))
    assert recommend_clients_for_campaign(FIRST_HOME, scope)['matched_count'] == 1
    assert repository.list_active_campaigns(RequestScope(other), date(2026, 10, 28)) == ()
    assert repository.list_active_campaigns(RequestScope(ADVISER, other), date(2026, 10, 28)) == ()
    assert repository.list_clients_for_fa(RequestScope(ADVISER, other)) == ()
    resolved = execute_resolve_campaign({'campaign_name': 'First Home Starter Bundle'},
                                       {'pulse_scope': {'fa_id': ADVISER, 'tenant_id': other}})
    assert resolved['status'] == 'not_found' and 'campaign_id' not in resolved
