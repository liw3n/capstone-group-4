"""Exercise discovery through MCP; PostgreSQL is tested separately."""
import asyncio
from contextlib import contextmanager
from dataclasses import replace
from datetime import date
import json

from fastmcp import Client
import pytest

from app.campaigns import repository
from app.campaigns.repository import Criteria
from app.tools import discovery
from app.tools.mcp_registry import MCPToolRegistry
from campaign_fixtures import CAMPAIGNS, DEMO_FA
from test_campaign_mcp import server

LIST_ACTIVE = repository.list_active_campaigns
DISCOVERY_CAMPAIGNS = tuple(replace(c, description=f"Educational campaign {i}.") for i, c in enumerate(CAMPAIGNS, 1))


@pytest.fixture(autouse=True)
def data(monkeypatch, campaign_rows):
    monkeypatch.setattr(discovery, 'current_date', lambda: date(2026, 8, 26))
    def campaigns(scope):
        if scope != repository.RequestScope(DEMO_FA):
            return ()
        candidates = (*DISCOVERY_CAMPAIGNS, replace(DISCOVERY_CAMPAIGNS[0], campaign_id='paused', status='paused'))
        return candidates
    monkeypatch.setattr(discovery, 'fetch_campaigns', campaigns)


def call(tool, args=None, scope=None, campaign_id=None):
    registry = MCPToolRegistry(server).bind_scope(scope or repository.RequestScope(DEMO_FA), campaign_id)
    return json.loads(registry.execute(tool, json.dumps(args or {})))


@pytest.mark.parametrize('args', [{}, {'fields': None}])
def test_defaults_include_description_and_readable_audience(args):
    result = call('get_active_campaigns', args, campaign_id='camp-1')
    assert result['total_count'] == 2  # Selection must not narrow general discovery.
    assert result['columns'] == discovery.DEFAULT_FIELDS
    assert result['rows'][0] == {
        'name': 'Legacy Protection Refresh',
        'description': 'Educational campaign 1.',
        'start_date': '2026-08-01', 'end_date': '2026-12-31',
        'age_groups': '55–64 or 65 and above', 'genders': 'Any',
        'cash_bands': 'S$250,000 to below S$1,000,000 or S$1,000,000 and above',
    }
    assert result['table'].startswith('| Campaign Name | Description | Start Date | End Date | Age Group |')
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
        assert discovery.execute_get_active_campaigns({}, metadata)['error_code'] == 'missing_context'
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
    monkeypatch.setattr(discovery, 'fetch_campaigns', fail)
    result = call(tool)
    assert result['error_code'] == 'storage_unavailable' and 'rows' not in result




@pytest.mark.parametrize('as_of', [date(2026, 8, 1), date(2026, 12, 31)])
def test_reporting_date_does_not_change_active_status(as_of, monkeypatch):
    monkeypatch.setattr(discovery, 'current_date', lambda: as_of)
    assert call('get_active_campaigns')['total_count'] == 2


def test_status_active_campaigns_remain_visible_after_schedule(monkeypatch):
    monkeypatch.setattr(discovery, 'current_date', lambda: date(2027, 2, 1))
    assert call('get_active_campaigns')['total_count'] == 2


def test_empty_exact_name_filter_keeps_discovery_response_unchanged():
    result = call('get_active_campaigns', {'campaign_names': ['First Home Starter Bundle campaign']})
    assert result['rows'] == []  # Preserve exact filter semantics for other callers.
    assert 'lookup_guidance' not in result
    assert 'lookup_guidance' not in call('get_active_campaigns')


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
    # The current schema stores UUID identities and JSON targeting criteria.
    adviser = 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'
    original_fetchall = Connection.fetchall
    def current_rows(self):
        row = original_fetchall(self)[0]
        row['audience_criteria'] = {'ageGroups': ['55-64'], 'cashCustomMin': 100}
        return [row]
    monkeypatch.setattr(Connection, 'fetchall', current_rows)
    result = LIST_ACTIVE(repository.RequestScope(adviser), date(2026, 8, 26), ['camp-1'], ["O'Reilly"])
    sql, params = captured[0]
    assert 'FROM campaign AS c' in sql
    assert 'c.tenant_id = %s AND c.created_by_user_id = %s' in sql
    assert params[:2] == (adviser, adviser)
    assert "COALESCE(c.status, 'active') = 'active'" in sql and 'c.start_date <= %s AND c.end_date >= %s' in sql
    assert "O'Reilly" not in sql and params[-1] == ["o'reilly"]
    assert result[0].criteria.cash_min == 100.0 and result[0].criteria.age_groups == ('55to64',)


def test_schema_and_invalid_fields():
    for fields in [[], ['tenant_id'], ['name', 'unknown'], ['campaign_code']]:
        assert call('get_active_campaigns', {'fields': fields})['error'] == 'Invalid tool arguments'
    schemas = MCPToolRegistry(server).schemas()
    names = {s['function']['name'] for s in schemas}
    assert {'get_active_campaigns', 'recommend_clients_for_campaign', 'campaign_follow_up'} <= names
    assert 'get_fa_clients' not in names
    for tool in ['get_active_campaigns']:
        schema = next(s['function']['parameters'] for s in schemas if s['function']['name'] == tool)
        assert not {'ctx', 'tenant_id', 'fa_id'} & schema['properties'].keys()
        assert schema['properties']['limit']['maximum'] == 1000


@pytest.mark.parametrize("arguments", [
    {"tool": "get_fa_clients"},
    {"tenant_id": "other"},
    {"fa_id": "other"},
    {"fields": ["unknown"]},
    {"limit": True},
])
def test_handler_rejects_invalid_arguments_before_repository_access(arguments, monkeypatch):
    def unexpected_read(*args):
        pytest.fail("Invalid arguments must not reach the repository")

    monkeypatch.setattr(discovery, "fetch_campaigns", unexpected_read)
    metadata = {"pulse_scope": {"fa_id": DEMO_FA, "tenant_id": "pulse-demo"}}
    assert discovery.execute_get_active_campaigns(arguments, metadata) == {
        "data_source": "synthetic",
        "error_code": "invalid_arguments",
        "error": "Invalid tool arguments",
    }


def test_handler_matches_mcp_response():
    arguments = {"campaign_ids": ["camp-1"], "fields": ["name", "start_date"]}
    metadata = {"pulse_scope": {"fa_id": DEMO_FA, "tenant_id": "pulse-demo"}}
    assert discovery.execute_get_active_campaigns(arguments, metadata) == call(
        "get_active_campaigns", arguments
    )


def test_campaign_limits_still_report_truncation():
    result = call('get_active_campaigns', {'limit': 1})
    assert result['total_count'] == 2 and result['returned_count'] == 1
    assert result['truncated']


def test_display_notice_omits_demo_wording_and_preserves_source_metadata():
    result = call("get_active_campaigns")
    assert result["data_source"] == "synthetic"
    assert "synthetic" not in result["disclaimer"].lower()
    assert "demo" not in result["disclaimer"].lower()
    assert "not a product suitability assessment or financial advice" in result["disclaimer"]
    assert "consent checks and confirmation" in result["disclaimer"]


def test_age_gender_cash_overlap_and_filtering_before_limit():
    result = call('get_active_campaigns', {'filters': {'age_min': 41}, 'limit': 1})
    assert result['total_count'] == 2 and result['truncated']
    assert result['columns'] == discovery.DEFAULT_FIELDS
    result = call('get_active_campaigns', {'filters': {'age_min': 45}, 'limit': 1})
    assert result['total_count'] == 1 and not result['truncated']
    assert result['rows'][0]['name'] == 'Legacy Protection Refresh'
    assert call('get_active_campaigns', {'filters': {'age_min': 45, 'cash_max': 49999}})['rows'] == []


def test_custom_mixed_and_unrestricted_criteria(monkeypatch):
    custom = replace(CAMPAIGNS[0], criteria=Criteria(age_min=40, age_max=55,
        genders=('male', 'female'), cash_min=500000, cash_max=2000000), start_date=None, end_date=None)
    monkeypatch.setattr(discovery, 'fetch_campaigns', lambda *args: (custom,))
    result = call('get_active_campaigns', {'filters': {'age_min': 41, 'genders': ['Female']}})
    assert result['rows'][0]['age_groups'] == '40–55'
    assert result['rows'][0]['cash_bands'] == 'S$500,000–S$2,000,000'
    assert result['rows'][0]['genders'] == 'Male, Female'
    assert result['rows'][0]['start_date'] is None
    assert call('get_active_campaigns', {'filters': {'age_min': 56}})['rows'] == []
    mixed = replace(custom, criteria=Criteria(age_groups=('under35',), age_min=40, age_max=45,
        cash_bands=('under50k',), cash_min=900000, cash_max=1200000))
    monkeypatch.setattr(discovery, 'fetch_campaigns', lambda *args: (mixed,))
    assert call('get_active_campaigns', {'filters': {'age_min': 41}})['rows'][0]['age_groups'] == 'Under 35 or 40–45'
    assert call('get_active_campaigns', {'filters': {'age_min': 35, 'age_max': 39}})['rows'] == []
    assert call('get_active_campaigns', {'filters': {'cash_min': 100000, 'cash_max': 200000}})['rows'] == []
    unrestricted = replace(custom, criteria=Criteria())
    monkeypatch.setattr(discovery, 'fetch_campaigns', lambda *args: (unrestricted,))
    assert call('get_active_campaigns', {'filters': {'genders': ['Male'], 'age_min': 90, 'cash_min': 2000000}})['total_count'] == 1


def test_preset_cash_boundaries_and_inclusive_custom_endpoints(monkeypatch):
    band = replace(CAMPAIGNS[0], criteria=Criteria(cash_bands=('under50k',)))
    monkeypatch.setattr(discovery, 'fetch_campaigns', lambda *args: (band,))
    assert call('get_active_campaigns', {'filters': {'cash_min': 50000}})['rows'] == []
    assert call('get_active_campaigns', {'filters': {'cash_min': 49999.99}})['total_count'] == 1
    custom = replace(band, criteria=Criteria(cash_min=50000, cash_max=250000))
    monkeypatch.setattr(discovery, 'fetch_campaigns', lambda *args: (custom,))
    assert call('get_active_campaigns', {'filters': {'cash_min': 250000}})['total_count'] == 1
    assert call('get_active_campaigns', {'filters': {'cash_min': 250000, 'cash_min_exclusive': True}})['rows'] == []
    assert call('get_active_campaigns', {'filters': {'cash_max': 50000, 'cash_max_exclusive': True}})['rows'] == []


def test_text_date_filters_and_projection_are_independent():
    for filters in ({'name_contains': 'LEGACY'}, {'description_contains': 'CAMPAIGN 1'}):
        result = call('get_active_campaigns', {'filters': filters})
        assert result['total_count'] == 1 and result['columns'] == discovery.DEFAULT_FIELDS
    assert call('get_active_campaigns', {'filters': {'start_date_from': '2026-09-01'}})['rows'] == []
    assert call('get_active_campaigns', {'filters': {'end_date_to': '2026-12-31'}})['total_count'] == 2


@pytest.mark.parametrize('filters', [
    {'age_min': 41, 'age_max': 40}, {'age_min': True}, {'age_min': 40.5},
    {'age_min': -1}, {'age_max': 131}, {'cash_min': -1}, {'cash_min': '100000'},
    {'cash_min': 200, 'cash_max': 100}, {'genders': ['Unknown']},
    {'cash_min_exclusive': True}, {'cash_min': 100, 'cash_max': 100, 'cash_max_exclusive': True},
    {'start_date_from': '2026-12-31', 'start_date_to': '2026-01-01'},
    {'campaign_codes': ['']}, {'status': 'inactive'}, {'tenant_id': 'other'},
])
def test_invalid_filters_rejected_before_read(filters, monkeypatch):
    monkeypatch.setattr(discovery, 'fetch_campaigns', lambda *args: pytest.fail('Unexpected read'))
    assert discovery.execute_get_active_campaigns({'filters': filters}, {
        'pulse_scope': {'fa_id': DEMO_FA, 'tenant_id': 'pulse-demo'},
    })['error_code'] == 'invalid_arguments'


def test_rendering_date_empty_result_truncation_and_excel_position():
    result = call('get_active_campaigns', {'filters': {'age_min': 41}, 'limit': 1})
    rendered = discovery.render_active_campaigns(result)
    assert rendered.startswith('**Current date: 26 August 2026 (Singapore)**')
    assert 'Age: 41 and above' in rendered and 'overlapping eligibility' in rendered
    assert rendered.index(result['table']) < rendered.index('[Download Excel (.xlsx)]')
    assert 'Showing 1 of 2' in rendered
    empty = discovery.render_active_campaigns(call('get_active_campaigns', {'campaign_ids': []}))
    assert 'No active campaigns match your filters.' in empty
    assert 'Download Excel' in empty
