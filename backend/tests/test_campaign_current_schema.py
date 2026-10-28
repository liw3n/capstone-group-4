"""Regression checks for the current campaign/contact schema and model-owned calls."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import date
import json
from uuid import UUID

import pytest

from app.campaigns import repository
from app.campaigns import matching
from app.campaigns.matching import recommend_clients_for_campaign
from app.campaigns.repository import CampaignStorageUnavailable, RequestScope
from app.contacts import catalog as contacts
from app.llm.orchestrator import ChatOrchestrator
from app.tools import discovery
from app.tools.mcp_registry import MCPToolRegistry
from app.store import ChatHistoryItem
from test_campaign_mcp import server
from test_orchestrator import FakeClient, completion, message, settings, tool_call

ADVISER = 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'
CAMPAIGN_ID = 'b2222222-2222-2222-2222-222222222222'
OTHER_TENANT = 'e0000000-0000-0000-0000-000000000001'


def campaign_row(**updates):
    row = {
        'campaign_id': UUID(CAMPAIGN_ID), 'name': 'First Home Starter Bundle',
        'status': None, 'start_date': date(2026, 8, 1), 'end_date': date(2026, 12, 31),
        'audience_criteria': {
            'ageGroups': ['under35', '35-44'], 'genders': ['Male', 'Female'],
            'cashBands': ['under50k', '50k-250k'],
        },
    }
    return {**row, **updates}


def fake_database(monkeypatch, rows):
    calls = []
    class Connection:
        def execute(self, query, params):
            calls.append((query, params))
            return self
        def fetchone(self):
            return deepcopy(rows[0]) if rows else None
        def fetchall(self):
            return deepcopy(rows)
    @contextmanager
    def connection():
        yield Connection()
    monkeypatch.setattr(repository, '_connection', connection)
    return calls


def test_current_campaign_json_preserves_every_filter_and_normalizes_bands(monkeypatch):
    calls = fake_database(monkeypatch, [campaign_row()])
    campaign = repository.get_campaign(CAMPAIGN_ID, RequestScope(ADVISER))
    assert campaign.campaign_id == CAMPAIGN_ID
    assert campaign.status == 'active'  # Current seeds have a nullable status.
    assert campaign.criteria.age_groups == ('under35', '35to44')
    assert campaign.criteria.genders == ('male', 'female')
    assert campaign.criteria.cash_bands == ('under50k', '50kTo250k')
    sql, params = calls[0]
    assert 'FROM campaign AS c' in sql and 'c.is_deleted = FALSE' in sql
    assert 'c.created_by_user_id = %s' in sql
    assert params == (CAMPAIGN_ID, ADVISER, ADVISER)


@pytest.mark.parametrize('criteria, expected', [
    ({'cashCustomMax': 250000}, (None, None, None, 250000)),
    ({'ageCustomMax': 45}, (None, 45, None, None)),
    ({'ageRange': {'min': 40, 'max': 55}, 'cashRange': {'min': 500000}},
     (40, 55, 500000, None)),
])
def test_custom_bounds_do_not_depend_on_unrelated_fields(criteria, expected):
    parsed = repository._campaign_from_row(campaign_row(audience_criteria=criteria), RequestScope(ADVISER))
    assert (parsed.criteria.age_min, parsed.criteria.age_max,
            parsed.criteria.cash_min, parsed.criteria.cash_max) == expected


@pytest.mark.parametrize('criteria', [None, [], {'ageGroups': ['unsupported']},
    {'genders': 'Male'}, {'cashCustomMin': -1}, {'ageCustomMax': 44.5},
    {'cashCustomMin': 100, 'cashCustomMax': 99}])
def test_missing_or_invalid_targeting_fails_closed(criteria):
    with pytest.raises(CampaignStorageUnavailable, match='criteria'):
        repository._campaign_from_row(campaign_row(audience_criteria=criteria), RequestScope(ADVISER))


def test_explicit_tenant_scope_is_not_replaced_by_adviser(monkeypatch):
    calls = fake_database(monkeypatch, [campaign_row()])
    repository.get_campaign(CAMPAIGN_ID, RequestScope(ADVISER, OTHER_TENANT))
    assert calls[0][1] == (CAMPAIGN_ID, OTHER_TENANT, ADVISER)


def test_current_contacts_use_same_synthetic_portfolio_values_as_crm(monkeypatch):
    client_id = UUID('d0000000-0000-0000-0000-000000000006')
    calls = fake_database(monkeypatch, [{
        'contact_id': client_id, 'full_name': 'Synthetic Current Contact',
        'date_of_birth': date(1996, 3, 26),
    }])
    requested = []
    def portfolio(ids):
        requested.append(ids)
        return {client_id: 'Female'}, {client_id: 45000.0}
    monkeypatch.setattr(contacts, '_call_mock_portfolio_api', portfolio)
    clients = repository.list_clients_for_fa(RequestScope(ADVISER))
    assert requested == [[client_id]]
    assert clients[0].contact_id == str(client_id)
    assert clients[0].gender == 'Female' and clients[0].available_cash == 45000
    sql, params = calls[0]
    assert 'FROM contact' in sql and 'assigned_to_user_id = %s' in sql
    assert 'created_by_user_id = %s' in sql and 'is_deleted = FALSE' in sql
    assert params == (ADVISER, ADVISER, ADVISER)
    monkeypatch.setattr(matching, 'get_campaign', lambda *_: repository._campaign_from_row(
        campaign_row(), RequestScope(ADVISER)))
    result = recommend_clients_for_campaign(CAMPAIGN_ID, RequestScope(ADVISER))
    assert result['matched_count'] == 1 and result['incomplete_count'] == 0


@pytest.mark.parametrize('history', [[], [
    ChatHistoryItem('2026-10-28T00:00:00Z', False, 'Please supply the campaign ID.'),
]])
def test_model_requested_lookup_then_matching_runs_through_real_mcp(monkeypatch, history):
    calls = fake_database(monkeypatch, [campaign_row()])
    monkeypatch.setattr(discovery, 'current_date', lambda: date(2026, 10, 28))
    monkeypatch.setattr(repository, '_load_clients', lambda scope: (
        repository.Client('synthetic-client', scope.fa_id, 'Synthetic Client',
                          '1996-03-26', 'Female', 45000, scope.tenant_id),
    ))
    responses = [
        completion(message(tool_calls=[tool_call('lookup', 'resolve_campaign',
            '{"campaign_name":"first home starter bundle campaign"}')])),
        completion(message(tool_calls=[tool_call('match', 'recommend_clients_for_campaign',
            json.dumps({'campaign_id': CAMPAIGN_ID}))])),
        completion(message(content='Synthetic Client matches the campaign criteria.')),
    ]
    provider = FakeClient(responses)
    result = ChatOrchestrator(provider, settings(), MCPToolRegistry(server)).run(
        'Which clients do you recommend for first home starter bundle campaign?',
        history, scope=RequestScope(ADVISER),
    )
    assert 'Synthetic Client' in result
    assert len(provider.calls) == 3
    lookup_result = json.loads(provider.calls[-2]['messages'][-1]['content'])
    assert lookup_result['status'] == 'matched'
    assert lookup_result['campaign_id'] == CAMPAIGN_ID
    assert 'table' not in lookup_result and 'criteria' not in lookup_result
    matching_result = json.loads(provider.calls[-1]['messages'][-1]['content'])
    assert matching_result['matched_count'] == 1
    assert len(calls) == 2


def test_no_backend_forced_lookup_when_model_answers_directly(monkeypatch):
    calls = fake_database(monkeypatch, [campaign_row()])
    provider = FakeClient([completion(message(content='Which campaign do you mean?'))])
    result = ChatOrchestrator(provider, settings(), MCPToolRegistry(server)).run(
        'Which clients should I target?', [], scope=RequestScope(ADVISER))
    assert 'Which campaign' in result
    assert calls == [] and len(provider.calls) == 1


def test_known_id_can_be_used_by_model_without_lookup(monkeypatch):
    calls = fake_database(monkeypatch, [campaign_row()])
    monkeypatch.setattr(repository, '_load_clients', lambda _: ())
    provider = FakeClient([
        completion(message(tool_calls=[tool_call('match', 'recommend_clients_for_campaign',
            json.dumps({'campaign_id': CAMPAIGN_ID}))])),
        completion(message(content='No clients match.')),
    ])
    ChatOrchestrator(provider, settings(), MCPToolRegistry(server)).run(
        'Who matches this campaign?', [], scope=RequestScope(ADVISER), campaign_id=CAMPAIGN_ID)
    assert len(calls) == 1 and len(provider.calls) == 2
