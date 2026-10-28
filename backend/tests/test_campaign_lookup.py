"""Campaign identity resolution is scoped and never executes downstream tools."""
from dataclasses import replace
from datetime import date
import json

import pytest

from app.campaigns import repository
from app.campaigns.repository import RequestScope
from app.tools import discovery
from app.tools.campaign_lookup import execute_resolve_campaign
from app.tools.mcp_registry import MCPToolRegistry
from campaign_fixtures import CAMPAIGNS, DEMO_FA
from test_campaign_mcp import server

METADATA = {'pulse_scope': {'fa_id': DEMO_FA, 'tenant_id': 'pulse-demo'}}


@pytest.fixture(autouse=True)
def campaigns(monkeypatch):
    calls = []
    def list_campaigns(scope, as_of):
        calls.append((scope, as_of))
        if scope != RequestScope(DEMO_FA):
            return ()
        return CAMPAIGNS
    monkeypatch.setattr(repository, 'list_active_campaigns', list_campaigns)
    monkeypatch.setattr(discovery, 'current_date', lambda: date(2026, 10, 28))
    return calls


def resolve(name, scope=None):
    return json.loads(MCPToolRegistry(server).bind_scope(scope or RequestScope(DEMO_FA)).execute(
        'resolve_campaign', json.dumps({'campaign_name': name})))


@pytest.mark.parametrize('name', [
    'First Home Starter Bundle', 'first home starter bundle campaign',
    ' THE FIRST-HOME STARTER BUNDLE CAMPAIGN ', 'first home',
])
def test_resolves_conversational_name_to_compact_identity(name, campaigns):
    result = resolve(name)
    assert result == {
        'data_source': 'synthetic', 'as_of_date': '2026-10-28', 'status': 'matched',
        'campaign_id': 'camp-2', 'name': 'First Home Starter Bundle',
    }
    assert campaigns == [(RequestScope(DEMO_FA), date(2026, 10, 28))]


def test_exact_name_wins_over_other_partial_matches(monkeypatch):
    monkeypatch.setattr(repository, 'list_active_campaigns', lambda *_: (
        replace(CAMPAIGNS[0], name='Welcome Campaign'),
        replace(CAMPAIGNS[1], name='Welcome Campaign Plus'),
    ))
    assert resolve('Welcome Campaign')['campaign_id'] == 'camp-1'


def test_ambiguous_names_return_candidates_without_choosing(monkeypatch):
    monkeypatch.setattr(repository, 'list_active_campaigns', lambda *_: tuple(
        replace(CAMPAIGNS[0], campaign_id=f'candidate-{i}', name=f'Home Plan {i}')
        for i in range(7)
    ))
    result = resolve('home campaign')
    assert result['status'] == 'ambiguous'
    assert result['candidate_count'] == 7 and len(result['candidates']) == 5
    assert result['truncated'] is True and 'campaign_id' not in result


@pytest.mark.parametrize('name', ['unknown', 'campaign', 'the campaign', 'starterbundle', "x' OR 1=1"])
def test_missing_or_non_word_matches_do_not_guess(name):
    result = resolve(name)
    assert result['status'] == 'not_found' and result['candidate_count'] == 0
    assert 'campaign_id' not in result


@pytest.mark.parametrize('scope', [RequestScope('other'), RequestScope(DEMO_FA, 'other')])
def test_scoped_lookup_never_exposes_another_adviser_or_tenant(scope):
    result = resolve('first home', scope)
    assert result['status'] == 'not_found' and 'candidates' not in result


@pytest.mark.parametrize('arguments', [
    {}, {'campaign_name': ''}, {'campaign_name': '   '}, {'campaign_name': 123},
    {'campaign_name': 'x' * 256}, {'campaign_name': 'home', 'fa_id': 'other'},
])
def test_invalid_arguments_fail_before_database_access(arguments, campaigns):
    assert execute_resolve_campaign(arguments, METADATA)['error_code'] == 'invalid_arguments'
    assert not campaigns


@pytest.mark.parametrize('metadata', [None, {}, {'pulse_scope': {}}, {'pulse_scope': 'bad'}])
def test_missing_scope_fails_before_database_access(metadata, campaigns):
    assert execute_resolve_campaign({'campaign_name': 'home'}, metadata)['error_code'] == 'missing_context'
    assert not campaigns


def test_storage_failure_has_safe_error_without_candidate_ids(monkeypatch):
    def fail(*_):
        raise repository.CampaignStorageUnavailable('Campaign database is temporarily unavailable')
    monkeypatch.setattr(repository, 'list_active_campaigns', fail)
    result = resolve('home')
    assert result['error_code'] == 'storage_unavailable'
    assert 'campaign_id' not in result and 'candidates' not in result


def test_mcp_schema_exposes_name_only_and_registry_requires_scope():
    schemas = MCPToolRegistry(server).schemas()
    lookup = next(item['function'] for item in schemas if item['function']['name'] == 'resolve_campaign')
    assert set(lookup['parameters']['properties']) == {'campaign_name'}
    assert lookup['parameters']['required'] == ['campaign_name']
    assert lookup['parameters']['properties']['campaign_name']['maxLength'] == 255
    assert 'context' in json.loads(MCPToolRegistry(server).execute(
        'resolve_campaign', '{"campaign_name":"home"}'))['error']
