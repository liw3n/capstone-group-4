"""HTTP boundary and response conversion for active campaign discovery."""
from copy import deepcopy

import httpx
from pydantic import SecretStr
import pytest

from app.config import Settings
from app.campaigns.repository import CampaignStorageUnavailable, RequestScope
from app.tools import campaign_catalogue_api as api
from app.tools import discovery

ADVISER = 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'
SCOPE = RequestScope(ADVISER)


def api_record(**updates):
    return {
        'id': 'b1111111-1111-1111-1111-111111111111', 'name': 'Educational campaign',
        'description': 'Review campaign', 'status': 'active',
        'startDate': '2030-01-01', 'endDate': '2030-12-31',
        'criteria': {'ageGroups': ['under35'], 'genders': ['male', 'female'],
                     'cashBands': ['under50k'], 'ageRange': {'min': 40, 'max': 55},
                     'cashRange': {'min': 900000, 'max': 1200000}},
        **updates,
    }


@pytest.fixture
def http_boundary(monkeypatch):
    settings = Settings(_env_file=None)
    monkeypatch.setattr(api, 'get_settings', lambda: settings)
    original = httpx.Client
    def install(handler):
        def client(**kwargs):
            assert kwargs['timeout'] == 10 and kwargs['trust_env'] is False
            return original(**kwargs, transport=httpx.MockTransport(handler))
        monkeypatch.setattr(api.httpx, 'Client', client)
    return install, settings


def test_adviser_identity_mixed_criteria_and_filtering_before_limit(http_boundary):
    install, _ = http_boundary
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(200, json=[api_record(status='inactive', id='inactive'), api_record()])
    install(handle)
    result = discovery.execute_get_active_campaigns({
        'filters': {'age_min': 41, 'genders': ['Female'], 'cash_min': 1000000},
        'fields': ['campaign_id', 'age_groups', 'cash_bands', 'genders'], 'limit': 1,
    }, {'pulse_scope': {'fa_id': ADVISER, 'tenant_id': 'pulse-demo'}})
    assert len(requests) == 1 and requests[0].url.path == '/api/campaigns'
    assert dict(requests[0].url.params) == {'role': 'advisor', 'fa_id': ADVISER}
    assert result['total_count'] == result['returned_count'] == 1 and not result['truncated']
    assert result['rows'][0]['age_groups'] == 'Under 35 or 40–55'
    assert result['rows'][0]['cash_bands'] == 'Below S$50,000 or S$900,000–S$1,200,000'
    assert result['rows'][0]['genders'] == 'Male, Female'
    assert 'campaign_code' not in result['columns']


@pytest.mark.parametrize('status', [401, 403, 404, 500, 503])
def test_api_failure_returns_a_safe_error_instead_of_an_empty_table(http_boundary, status):
    install, _ = http_boundary
    install(lambda _: httpx.Response(status, text='private server error'))
    result = discovery.execute_get_active_campaigns({}, {
        'pulse_scope': {'fa_id': ADVISER, 'tenant_id': 'pulse-demo'},
    })
    assert result['error_code'] == 'storage_unavailable'
    assert 'rows' not in result and 'private' not in result['error']


def test_timeout_never_falls_back_to_direct_sql(http_boundary, monkeypatch):
    from app.campaigns import repository, catalog
    install, _ = http_boundary
    def timeout(request):
        raise httpx.ReadTimeout('private URL', request=request)
    install(timeout)
    def unexpected_database():
        pytest.fail('Discovery must not query PostgreSQL directly')
    monkeypatch.setattr(repository, '_connection', unexpected_database)
    monkeypatch.setattr(catalog, '_connection', unexpected_database)
    with pytest.raises(CampaignStorageUnavailable, match='Campaign API'):
        api.fetch_campaigns(SCOPE)


@pytest.mark.parametrize('payload', [None, {}, [{}], [api_record(criteria={})]])
def test_invalid_api_data_is_rejected(http_boundary, payload):
    install, _ = http_boundary
    install(lambda _: httpx.Response(200, json=payload))
    with pytest.raises(CampaignStorageUnavailable):
        api.fetch_campaigns(SCOPE)


def test_invalid_json_and_fractional_age_are_rejected(http_boundary):
    install, _ = http_boundary
    install(lambda _: httpx.Response(200, text='<html>not JSON</html>'))
    with pytest.raises(CampaignStorageUnavailable):
        api.fetch_campaigns(SCOPE)
    record = deepcopy(api_record())
    record['criteria']['ageRange']['min'] = 40.5
    install(lambda _: httpx.Response(200, json=[record]))
    with pytest.raises(CampaignStorageUnavailable):
        api.fetch_campaigns(SCOPE)


def test_unrepresentable_tenant_is_rejected_before_http(http_boundary):
    install, _ = http_boundary
    install(lambda _: pytest.fail('Must not discard explicit tenant context'))
    with pytest.raises(CampaignStorageUnavailable, match='tenant context'):
        api.fetch_campaigns(RequestScope(ADVISER, 'other-tenant'))


def test_empty_response_explicit_adviser_tenant_and_stable_order(http_boundary):
    install, _ = http_boundary
    install(lambda _: httpx.Response(200, json=[]))
    assert api.fetch_campaigns(RequestScope(ADVISER, ADVISER)) == ()
    install(lambda _: httpx.Response(200, json=[api_record(id='z'), api_record(id='a')]))
    assert [c.campaign_id for c in api.fetch_campaigns(SCOPE)] == ['a', 'z']


def test_hosted_port_configured_origin_and_shared_basic_auth(http_boundary, monkeypatch):
    install, settings = http_boundary
    settings.demo_auth_enabled = True
    settings.demo_auth_username = 'demo'
    settings.demo_auth_password = SecretStr('synthetic-test-password')
    monkeypatch.setenv('PORT', '10000')
    def handle(request):
        assert request.url.host == '127.0.0.1' and request.url.port == 10000
        assert request.headers['authorization'].startswith('Basic ')
        return httpx.Response(200, json=[])
    install(handle)
    assert api.fetch_campaigns(SCOPE) == ()
    settings.campaign_api_base_url = 'http://127.0.0.1:4567'
    def configured(request):
        assert request.url.port == 4567
        return httpx.Response(200, json=[])
    install(configured)
    assert api.fetch_campaigns(SCOPE) == ()
