"""Bound recommendations before MCP/Groq; export the complete scoped snapshot."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from uuid import UUID

from fastapi.testclient import TestClient
import pytest

from app import main
from app.campaigns import matching, recommendation_lists as lists, repository
from app.campaigns.repository import Campaign, Client, Criteria, RequestScope
from app.llm.orchestrator import ChatOrchestrator
from app.tools import campaign
from app.tools.mcp_registry import MCPToolRegistry
from test_campaign_mcp import server
from test_orchestrator import FakeClient, completion, message, settings, tool_call

LIST_ID = '66666666-6666-4666-8666-666666666666'
SCOPE = RequestScope('adviser-a', 'tenant-a')
META = {'pulse_scope': {'fa_id': SCOPE.fa_id, 'tenant_id': SCOPE.tenant_id}}


@pytest.fixture
def broad_campaign(monkeypatch):
    from datetime import date
    from app.campaigns import clock
    monkeypatch.setattr(clock, 'current_date', lambda: date(2026, 11, 7))
    monkeypatch.setattr(matching, 'get_campaign', lambda *_: Campaign(
        'broad', 'Broad synthetic campaign', Criteria(age_groups=('under35',))))
    snapshots = []
    def save(scope, result, session_id):
        snapshots.append((scope, deepcopy(result), session_id))
        return {'list_id': LIST_ID, 'expires_at': '2026-11-08T00:00:00Z'}
    monkeypatch.setattr(campaign, 'save_list', save)
    return snapshots


def book(monkeypatch, matched, incomplete=0):
    rows = [Client(f'match-{i:04}', 'adviser-a', f'Matching Client {i}', '2000-01-01', 'Female', 10000)
            for i in range(matched)]
    rows += [Client(f'gap-{i:04}', 'adviser-a', f'Incomplete Client {i}', None, 'Male', 10000)
             for i in range(incomplete)]
    monkeypatch.setattr(matching, 'list_clients_for_fa', lambda _: tuple(rows))


@pytest.mark.parametrize('count', [0, 1, 10])
def test_small_results_are_complete_and_do_not_need_snapshot_storage(monkeypatch, broad_campaign, count):
    book(monkeypatch, count)
    result = campaign.execute_recommendation('broad', 100, META)
    assert len(result['clients']) == result['matched_count'] == count
    assert result['truncated'] is False and result['list_id'] is None
    assert not broad_campaign
    assert campaign.render_recommendation_download(result) == ''


@pytest.mark.parametrize('limit', [1, 10, 100])
def test_full_book_is_saved_but_only_bounded_previews_leave_tool(monkeypatch, broad_campaign, limit):
    book(monkeypatch, 150, 25)
    result = campaign.execute_recommendation('broad', limit, {**META, 'session_id': 'session'})
    assert result['evaluated_count'] == 175 and result['matched_count'] == 150
    assert result['incomplete_count'] == 25
    assert len(result['clients']) == len(result['incomplete_clients']) == min(limit, 10)
    assert result['truncated'] is True and result['incomplete_truncated'] is True
    assert result['list_id'] == LIST_ID
    scope, full, session = broad_campaign[0]
    assert scope == SCOPE and session == 'session'
    assert len(full['clients']) == 150 and len(full['incomplete_clients']) == 25
    footer = campaign.render_recommendation_download(result)
    assert f'#recommendation-excel-{LIST_ID}' in footer
    assert 'Available for 24 hours' in footer
    assert 'Matching Client' not in footer and 'Incomplete Client' not in footer
    assert '| Contact' not in footer and '150 matching clients' not in footer


def test_storage_failure_returns_an_error_instead_of_a_fake_complete_list(monkeypatch, broad_campaign):
    book(monkeypatch, 11)
    def fail(*_):
        raise repository.CampaignStorageUnavailable('Snapshot unavailable')
    monkeypatch.setattr(campaign, 'save_list', fail)
    result = campaign.execute_recommendation('broad', 100, META)
    assert result['error_code'] == 'storage_unavailable' and 'clients' not in result


def test_large_incomplete_group_is_bounded_even_without_matches(monkeypatch, broad_campaign):
    book(monkeypatch, 0, 25)
    result = campaign.execute_recommendation('broad', 100, META)
    assert result['matched_count'] == 0 and result['clients'] == []
    assert result['incomplete_count'] == 25 and len(result['incomplete_clients']) == 10
    assert len(broad_campaign[0][1]['incomplete_clients']) == 25
    assert result['list_id'] == LIST_ID


def test_model_receives_preview_and_id_but_never_full_snapshot_through_real_mcp(monkeypatch, broad_campaign):
    book(monkeypatch, 150, 25)
    groq_reply = (
        '### Eligible clients (synthetic)\n\n150 matching clients out of 175 evaluated.\n\n'
        'Showing 10 matches.\n\n| Contact ID | Client Name | Eligibility Reasons |\n'
        '| --- | --- | --- |\n' + '\n'.join(
            f'| match-{i:04} | Matching Client {i} | Meets the campaign criteria |' for i in range(10)
        ) + '\n\n25 incomplete profiles. These are not financial advice.'
    )
    provider = FakeClient([
        completion(message(tool_calls=[tool_call('recommend', 'recommend_clients_for_campaign',
                                                '{"campaign_id":"broad","limit":100}')])),
        completion(message(content=groq_reply)),
    ])
    answer = ChatOrchestrator(provider, settings(), MCPToolRegistry(server)).run(
        'Which clients match Broad synthetic campaign?', [], scope=SCOPE)
    tool_result = json.loads(provider.calls[1]['messages'][-1]['content'])
    assert tool_result['matched_count'] == 150 and tool_result['list_id'] == LIST_ID
    assert len(tool_result['clients']) == len(tool_result['incomplete_clients']) == 10
    assert 'match-0149' not in json.dumps(provider.calls)
    assert 'gap-0024' not in json.dumps(provider.calls)
    assert '150 matching clients' in answer and f'#recommendation-excel-{LIST_ID}' in answer
    assert answer.answer.startswith(groq_reply + '\n\n')
    for i in range(10):
        assert answer.answer.count(f'match-{i:04}') == 1
    assert answer.answer.count('| Contact ID |') == 1
    assert answer.answer.count('Download full results (.xlsx)') == 1
    assert len(provider.calls) == 2
    assert not any(call['structured'] for call in provider.calls)
    assert len(broad_campaign[0][1]['clients']) == 150


def test_small_recommendation_keeps_groq_reply_exactly_without_backend_report(monkeypatch, broad_campaign):
    book(monkeypatch, 3)
    groq_reply = 'Three synthetic clients match. Matching Client 0, Matching Client 1, Matching Client 2.'
    provider = FakeClient([
        completion(message(tool_calls=[tool_call('recommend', 'recommend_clients_for_campaign', '{"campaign_id":"broad"}')])),
        completion(message(content=groq_reply)),
    ])
    answer = ChatOrchestrator(provider, settings(), MCPToolRegistry(server)).run('Recommend clients for Broad synthetic campaign', [], scope=SCOPE)
    assert answer.answer == groq_reply
    assert not broad_campaign


def test_repeated_calls_do_not_duplicate_download_footer(monkeypatch, broad_campaign):
    book(monkeypatch, 25)
    provider = FakeClient([
        completion(message(tool_calls=[tool_call('first', 'recommend_clients_for_campaign', '{"campaign_id":"broad"}')])),
        completion(message(tool_calls=[tool_call('again', 'recommend_clients_for_campaign', '{"campaign_id":"broad"}')])),
        completion(message(content='There are matching clients; review the preview.')),
    ])
    answer = ChatOrchestrator(provider, settings(), MCPToolRegistry(server)).run('Recommend clients for Broad synthetic campaign', [], scope=SCOPE)
    assert answer.answer.count('Download full results (.xlsx)') == 1


def test_existing_correct_model_download_link_is_not_appended_again(monkeypatch, broad_campaign):
    book(monkeypatch, 25)
    groq_reply = f'Results ready. [Download full results (.xlsx)](#recommendation-excel-{LIST_ID})'
    provider = FakeClient([
        completion(message(tool_calls=[tool_call('recommend', 'recommend_clients_for_campaign', '{"campaign_id":"broad"}')])),
        completion(message(content=groq_reply)),
    ])
    answer = ChatOrchestrator(provider, settings(), MCPToolRegistry(server)).run('Recommend clients for Broad synthetic campaign', [], scope=SCOPE)
    assert answer.answer == groq_reply


def test_mixed_recommendation_and_performance_preserves_entire_groq_answer(monkeypatch, broad_campaign):
    book(monkeypatch, 25)
    class Registry:
        def bind_scope(self, *args, **kwargs):
            return self
        def schemas(self):
            return [{'type': 'function', 'function': {'name': name, 'parameters': {}}}
                    for name in ('recommend_clients_for_campaign', 'get_campaign_contact_performance')]
        def execute(self, name, arguments):
            return json.dumps(campaign.execute_recommendation('broad', 10, META) if name == 'recommend_clients_for_campaign'
                              else {'email_coverage_percent': 75})
    groq_reply = '25 clients match. Preview: Matching Client 0.\n\nCampaign performance: 75% email coverage.'
    provider = FakeClient([
        completion(message(tool_calls=[
            tool_call('recommend', 'recommend_clients_for_campaign', '{"campaign_id":"broad"}'),
            tool_call('performance', 'get_campaign_contact_performance', '{"campaign":"Broad synthetic campaign"}'),
        ])),
        completion(message(content=groq_reply)),
    ])
    answer = ChatOrchestrator(provider, settings(), Registry()).run('Recommend clients and report campaign performance', [], scope=SCOPE)
    assert answer.answer.startswith(groq_reply + '\n\n')
    assert answer.answer.count('Matching Client 0') == 1
    assert answer.answer.count('75% email coverage') == 1
    assert answer.answer.count('Download full results (.xlsx)') == 1


def fake_storage(monkeypatch, row):
    calls = []
    class Connection:
        def execute(self, sql, params):
            calls.append((sql, params))
            return self
        def fetchone(self):
            return row
    @contextmanager
    def connect():
        yield Connection()
    monkeypatch.setattr(lists, 'connection', connect)
    return calls


def test_snapshot_insert_preserves_all_rows_and_scopes_expiry_cleanup(monkeypatch):
    calls = fake_storage(monkeypatch, None)
    full = {'campaign_id': 'broad', 'clients': [{'contact_id': str(i)} for i in range(151)]}
    result = lists.save_list(SCOPE, full, 'session')
    UUID(result['list_id'])
    assert calls[0][1][:2] == ('tenant-a', 'adviser-a')
    assert calls[1][1][1:5] == ('tenant-a', 'adviser-a', 'session', 'broad')
    assert len(calls[1][1][-1].obj['clients']) == 151
    assert datetime.fromisoformat(result['expires_at']) > datetime.now(timezone.utc)


def test_unknown_cross_scope_ids_do_not_reveal_a_list(monkeypatch):
    calls = fake_storage(monkeypatch, None)
    with pytest.raises(lists.RecommendationListNotFound):
        lists.load_list(SCOPE, UUID(LIST_ID))
    sql, params = calls[0]
    assert 'tenant_id = %s AND fa_id = %s' in sql
    assert params == (UUID(LIST_ID), 'tenant-a', 'adviser-a')


def test_expired_lists_fail_before_reading_campaign_or_clients(monkeypatch):
    fake_storage(monkeypatch, {'payload': {}, 'expires_at': datetime.now(timezone.utc) - timedelta(seconds=1)})
    monkeypatch.setattr(repository, 'get_campaign', lambda *_: pytest.fail('Expired list must not load records'))
    with pytest.raises(lists.RecommendationListExpired):
        lists.load_list(SCOPE, UUID(LIST_ID))


def test_reassigned_contacts_invalidate_download(monkeypatch):
    fake_storage(monkeypatch, {
        'expires_at': datetime.now(timezone.utc) + timedelta(hours=1),
        'payload': {'campaign_id': 'broad', 'clients': [{'contact_id': 'reassigned'}], 'incomplete_clients': []},
    })
    monkeypatch.setattr(repository, 'get_campaign', lambda *_: None)
    monkeypatch.setattr(repository, 'list_clients_for_fa', lambda _: ())
    with pytest.raises(lists.RecommendationListExpired, match='access has changed'):
        lists.load_list(SCOPE, UUID(LIST_ID))


@pytest.mark.parametrize('prefix', ['/chat', '/api/chat'])
def test_download_routes_return_full_snapshot_without_llm_or_caching(monkeypatch, prefix):
    full = {'clients': [{'contact_id': str(i)} for i in range(150)]}
    received = []
    def load(scope, list_id):
        received.append((scope, list_id))
        return full
    monkeypatch.setattr(main, 'load_list', load)
    monkeypatch.setattr(main, 'get_orchestrator', lambda: pytest.fail('Export must not call Groq'))
    response = TestClient(main.app).get(f'{prefix}/recommendation-lists/{LIST_ID}?fa_id=adviser-a')
    assert response.status_code == 200 and len(response.json()['clients']) == 150
    assert response.headers['cache-control'] == 'no-store'
    assert received == [(RequestScope('adviser-a'), UUID(LIST_ID))]


@pytest.mark.parametrize('error, status', [
    (lists.RecommendationListNotFound('Not found'), 404),
    (lists.RecommendationListExpired('Expired'), 410),
    (repository.CampaignStorageUnavailable('Unavailable'), 503),
])
def test_download_errors_are_actionable(monkeypatch, error, status):
    def fail(*_):
        raise error
    monkeypatch.setattr(main, 'load_list', fail)
    response = TestClient(main.app).get(f'/api/chat/recommendation-lists/{LIST_ID}?fa_id=adviser-a')
    assert response.status_code == status


def test_download_requires_valid_list_id_and_adviser(monkeypatch):
    monkeypatch.setattr(main, 'load_list', lambda *_: pytest.fail('Invalid request must not read storage'))
    client = TestClient(main.app)
    assert client.get(f'/api/chat/recommendation-lists/{LIST_ID}').status_code == 422
    assert client.get('/api/chat/recommendation-lists/invalid?fa_id=adviser').status_code == 422
