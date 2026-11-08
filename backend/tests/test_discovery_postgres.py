"""Opt-in current-schema discovery checks in disposable PostgreSQL schemas."""
from datetime import date
from uuid import uuid4

import pytest
import httpx
from fastapi.testclient import TestClient
from app import main
from app.config import Settings
from app.tools import campaign_catalogue_api

from app.campaigns import repository
from app.tools.discovery import execute_get_active_campaigns
from test_campaign_current_postgres import current_database, ADVISER, FIRST_HOME


@pytest.fixture(autouse=True)
def catalogue_http(monkeypatch, current_database):
    # Run the actual REST route/SQL while redirecting only the HTTP transport.
    client = TestClient(main.app, raise_server_exceptions=False)
    original = httpx.Client
    def endpoint(request):
        response = client.get(request.url.path, params=dict(request.url.params))
        return httpx.Response(response.status_code, content=response.content, headers=dict(response.headers))
    monkeypatch.setattr(campaign_catalogue_api.httpx, 'Client',
        lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(endpoint)))
    monkeypatch.setattr(campaign_catalogue_api, 'get_settings', lambda: Settings(_env_file=None))


def discover(arguments=None, tenant='pulse-demo'):
    return execute_get_active_campaigns(arguments or {}, {
        'pulse_scope': {'fa_id': ADVISER, 'tenant_id': tenant},
    })


@pytest.mark.parametrize(('status', 'deleted', 'expected'), [
    ('active', False, 1), ('inactive', False, 0), ('draft', False, 0),
    ('paused', False, 0), (None, False, 1), ('active', True, 0),
])
def test_status_and_deletion_are_exact_discovery_conditions(current_database, status, deleted, expected):
    current_database.execute('UPDATE campaign SET status=%s,is_deleted=%s WHERE campaign_id=%s',
                             (status, deleted, FIRST_HOME))
    result = discover({'campaign_ids': [FIRST_HOME]})
    assert result['total_count'] == expected


@pytest.mark.parametrize(('start', 'end'), [
    ('2030-01-01', '2030-12-31'), ('2020-01-01', '2020-12-31'),
])
def test_active_discovery_ignores_schedule_and_decodes_current_schema(current_database, start, end):
    current_database.execute('UPDATE campaign SET status=%s,start_date=%s,end_date=%s WHERE campaign_id=%s',
                             ('active', start, end, FIRST_HOME))
    result = discover({'campaign_ids': [FIRST_HOME]})
    assert result['total_count'] == 1
    row = result['rows'][0]
    assert 'campaign_code' not in row and row['description']
    assert row['start_date'] == start and row['end_date'] == end
    assert row['age_groups'] == 'Under 35 or 35–44'
    assert row['genders'] == 'Male, Female'


def test_discovery_uses_endpoint_creator_restriction_without_changing_other_tools(current_database):
    other = str(uuid4())
    current_database.execute('INSERT INTO user_account(tenant_id,user_id) VALUES (%s,%s)', (ADVISER, other))
    current_database.execute('UPDATE campaign SET created_by_user_id=%s WHERE campaign_id=%s', (other, FIRST_HOME))
    assert discover({'campaign_ids': [FIRST_HOME]})['total_count'] == 0
    assert discover({'campaign_ids': [FIRST_HOME]}, tenant=other)['error_code'] == 'storage_unavailable'
    scope = repository.RequestScope(ADVISER)
    assert repository.list_active_campaigns(scope, date(2026,10,28), [FIRST_HOME]) == ()
    with pytest.raises(repository.CampaignUnavailable):
        repository.get_campaign(FIRST_HOME, scope)


def test_custom_and_preset_audiences_are_preserved_in_filtered_database_results(current_database):
    current_database.execute('''UPDATE campaign SET audience_criteria =
        '{"ageGroups":["under35"],"ageCustomMin":40,"ageCustomMax":45,
          "genders":["Male","Female"],"cashBands":["under50k"],
          "cashCustomMin":900000,"cashCustomMax":1200000}'::jsonb
        WHERE campaign_id=%s''', (FIRST_HOME,))
    result = discover({'campaign_ids': [FIRST_HOME], 'filters': {'age_min': 41, 'genders': ['Male']}})
    assert result['total_count'] == 1
    assert result['rows'][0]['age_groups'] == 'Under 35 or 40–45'
    assert 'S$900,000–S$1,200,000' in result['rows'][0]['cash_bands']
    assert discover({'campaign_ids': [FIRST_HOME], 'filters': {'age_min':35, 'age_max':39}})['rows'] == []
