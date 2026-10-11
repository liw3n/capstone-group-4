"""Exercise discovery through MCP; PostgreSQL is tested separately."""
import asyncio
from contextlib import contextmanager
from dataclasses import replace
from datetime import date
import json

from fastmcp import Client
import pytest

from app.campaigns import repository
from app.tools import discovery
from app.tools.mcp_registry import MCPToolRegistry
from campaign_fixtures import CAMPAIGNS, DEMO_FA
from test_campaign_mcp import server

LIST_ACTIVE = repository.list_active_campaigns


@pytest.fixture(autouse=True)
def data(monkeypatch, campaign_rows):
    monkeypatch.setattr(discovery, 'current_date', lambda: date(2026, 8, 26))
    def campaigns(scope, as_of, ids=None, names=None):
        candidates = (*CAMPAIGNS, replace(CAMPAIGNS[0], campaign_id='paused', status='paused'),
                      replace(CAMPAIGNS[0], campaign_id='future', start_date=date(2027, 1, 1)))
        return tuple(c for c in candidates if c.tenant_id == scope.tenant_id
                     and scope.fa_id in c.fa_ids and c.start_date <= as_of <= c.end_date
                     and c.status == 'active' and (ids is None or c.campaign_id in ids)
                     and (names is None or c.name.lower() in [n.lower() for n in names]))
    monkeypatch.setattr(repository, 'list_active_campaigns', campaigns)


def call(tool, args=None, scope=None, campaign_id=None):
    registry = MCPToolRegistry(server).bind_scope(scope or repository.RequestScope(DEMO_FA), campaign_id)
    return json.loads(registry.execute(tool, json.dumps(args or {})))


@pytest.mark.parametrize('args', [{}, {'fields': None}])
def test_defaults_include_campaign_ids_and_full_details(args):
    result = call('get_active_campaigns', args, campaign_id='camp-1')
    assert result['total_count'] == 2  # Selection must not narrow general discovery.
    assert result['columns'] == discovery.DEFAULT_FIELDS
    assert result['rows'][0] == {
        'campaign_id': 'camp-1', 'name': 'Legacy Protection Refresh',
        'start_date': '2026-08-01', 'end_date': '2026-12-31',
        'age_groups': ['55to64', '65plus'], 'genders': [], 'cash_bands': ['250kTo1m', 'above1m'],
    }
    assert result['table'].startswith('| Campaign ID | Name | Start Date | End Date | Age Groups |')
    assert '_' not in result['table'].splitlines()[0]


def test_projection_and_exact_filters():
    result = call('get_active_campaigns', {'campaign_names': ['LEGACY PROTECTION REFRESH'],
                                         'fields': ['cash_min']})
    assert result['rows'] == [{'name': CAMPAIGNS[0].name, 'cash_min': None}]
    assert call('get_active_campaigns', {'campaign_ids': []})['rows'] == []
    assert call('get_active_campaigns', {'campaign_ids': ['unknown']})['rows'] == []
    assert call('get_active_campaigns', {'campaign_ids': ['camp-1'],
                                       'campaign_names': [CAMPAIGNS[1].name]})['rows'] == []
    result = call('get_active_campaigns', {'fields': ['campaign_id', 'campaign_id']})
    assert result['columns'] == ['name', 'campaign_id']




def test_scope_validation_and_safe_failure(monkeypatch):
    tool = 'get_active_campaigns'
    for metadata in [None, {}, {'pulse_scope': 'bad'}, {'pulse_scope': {'fa_id': '', 'tenant_id': 'pulse-demo'}}]:
        assert discovery.execute_discovery(tool, {}, metadata)['error_code'] == 'missing_context'
    for scope in [repository.RequestScope('other'), repository.RequestScope(DEMO_FA, 'other')]:
        assert call(tool, scope=scope)['rows'] == []
    for args in [{'tenant_id': 'other'}, {'fa_id': 'other'}, {'limit': True}, {'limit': 0},
                 {'limit': 1001}, {'campaign_ids': ['bad id']}, {'ctx': {}}]:
        assert call(tool, args)['error'] == 'Invalid tool arguments'
    async def unscoped():
        async with Client(server) as client:
            return await client.call_tool(tool, {})
    assert asyncio.run(unscoped()).data['error_code'] == 'missing_context'
    assert 'context' in json.loads(MCPToolRegistry(server).execute(tool, '{}'))['error']
    def fail(*args):
        raise repository.CampaignStorageUnavailable('Campaign database is temporarily unavailable')
    monkeypatch.setattr(repository, 'list_active_campaigns', fail)
    result = call(tool)
    assert result['error_code'] == 'storage_unavailable' and 'rows' not in result




@pytest.mark.parametrize('as_of', [date(2026, 8, 1), date(2026, 12, 31)])
def test_active_dates_are_inclusive(as_of, monkeypatch):
    monkeypatch.setattr(discovery, 'current_date', lambda: as_of)
    assert call('get_active_campaigns')['total_count'] == 2


def test_expired_campaigns_and_empty_results(monkeypatch):
    monkeypatch.setattr(discovery, 'current_date', lambda: date(2027, 2, 1))
    assert call('get_active_campaigns')['rows'] == []


def test_table_escapes_cells():
    table = discovery.markdown_table(['campaign_name'], [{'campaign_name': '<b>A|B\nC</b>'}])
    assert '&lt;b&gt;A&#124;B C&lt;/b&gt;' in table
    assert len(table.splitlines()) == 3


def test_repository_query_enforces_scope_and_parameterizes_filters(monkeypatch):
    captured = []
    class Connection:
        def execute(self, sql, parameters):
            captured.append((sql, parameters))
            return self
        def fetchall(self):
            return [{
                'campaign_id': 'camp-1', 'tenant_id': 'pulse-demo', 'name': 'Synthetic campaign',
                'status': 'active', 'start_date': date(2026, 8, 1), 'end_date': date(2026, 12, 31),
                'age_groups': ['55to64'], 'genders': [], 'cash_bands': [],
                'age_min': None, 'age_max': None, 'cash_min': 100, 'cash_max': None,
            }]
    @contextmanager
    def connection():
        yield Connection()
    monkeypatch.setattr(repository, '_connection', connection)
    result = LIST_ACTIVE(repository.RequestScope(DEMO_FA), date(2026, 8, 26), ['camp-1'], ["O'Reilly"])
    sql, params = captured[0]
    assert 'c.tenant_id = %s AND a.fa_id = %s' in sql
    assert "c.status = 'active'" in sql and 'c.start_date <= %s AND c.end_date >= %s' in sql
    assert "O'Reilly" not in sql and params[-1] == ["o'reilly"]
    assert result[0].criteria.cash_min == 100.0 and result[0].criteria.age_groups == ('55to64',)


def test_schema_and_invalid_fields():
    for fields in [[], ['tenant_id'], ['name', 'unknown']]:
        assert call('get_active_campaigns', {'fields': fields})['error'] == 'Invalid tool arguments'
    schemas = MCPToolRegistry(server).schemas()
    names = {s['function']['name'] for s in schemas}
    assert {'get_active_campaigns', 'recommend_clients_for_campaign', 'campaign_follow_up'} <= names
    assert 'get_fa_clients' not in names
    for tool in ['get_active_campaigns']:
        schema = next(s['function']['parameters'] for s in schemas if s['function']['name'] == tool)
        assert not {'ctx', 'tenant_id', 'fa_id'} & schema['properties'].keys()
        assert schema['properties']['limit']['maximum'] == 1000


def test_removed_client_tool_cannot_execute_discovery():
    metadata = {'pulse_scope': {'fa_id': DEMO_FA, 'tenant_id': 'pulse-demo'}}
    result = discovery.execute_discovery('get_fa_clients', {}, metadata)
    assert result['error'] == 'Unknown discovery tool'
    assert 'rows' not in result


def test_campaign_limits_still_report_truncation():
    result = call('get_active_campaigns', {'limit': 1})
    assert result['total_count'] == 2 and result['returned_count'] == 1
    assert result['truncated']
