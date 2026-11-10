"""Evaluation checks using fake clocks/services; no database or Groq access."""
from dataclasses import asdict
import json
from types import SimpleNamespace

import pytest

from evaluation import evaluate_client_recommendation as evaluation


@pytest.fixture
def fake_services(monkeypatch):
    clock = SimpleNamespace(now=0.)
    monkeypatch.setattr(evaluation.time, 'perf_counter', lambda: clock.now)
    state = SimpleNamespace(campaign_id='campaign-a', tool_error=False,
                            raise_error=False, skip_tool=False, executed=[])

    class Client:
        def create_chat_completion(self, *_args):
            clock.now += 2
            if state.raise_error:
                raise RuntimeError('secret-provider-detail')
            return 'completion'

    class Registry:
        def __init__(self, _transport):
            pass

        def schemas(self):
            clock.now += .1
            return [{'name': 'normal-tools'}]

        def bind_scope(self, scope, **kwargs):
            assert scope == evaluation.SCOPE and kwargs.get('campaign_id') is None
            return self

        def execute(self, name, arguments):
            state.executed.append((name, json.loads(arguments)))
            if name == evaluation.LOOKUP:
                clock.now += .2
                return json.dumps({'status': 'matched', 'campaign_id': state.campaign_id})
            clock.now += .8
            if state.tool_error:
                return json.dumps({'error': 'secret-database-detail', 'error_code': 'storage_unavailable'})
            return json.dumps({
                'campaign_id': state.campaign_id, 'evaluated_count': 20,
                'matched_count': 12, 'incomplete_count': 0, 'excluded_count': 8,
                'returned_count': 10, 'as_of_date': '2026-11-10', 'list_id': 'snapshot-a',
            })

    class Orchestrator:
        def __init__(self, client, _settings, registry):
            self.client, self.registry = client, registry

        def run(self, prompt, history, *, scope):
            assert prompt == evaluation.PROMPTS[0].prompt and history == []
            registry = self.registry.bind_scope(scope)
            registry.schemas()
            self.client.create_chat_completion([], [])
            if state.skip_tool:
                return 'Which campaign do you mean?'
            registry.execute(evaluation.LOOKUP, '{"campaign_name":"Young Families Cover Check"}')
            registry.execute(evaluation.RECOMMEND, '{"campaign_id":"campaign-a"}')
            self.client.create_chat_completion([], [])
            return 'Synthetic matches for adviser review.'

    monkeypatch.setattr(evaluation, 'MCPToolRegistry', Registry)
    monkeypatch.setattr(evaluation, 'ChatOrchestrator', Orchestrator)
    return state, Client()


def measure(client):
    return evaluation.measure_run(evaluation.PROMPTS[0], 1, object(), object(), client, 'campaign-a')


def test_orchestrator_model_and_tool_boundaries_are_timed(fake_services):
    state, client = fake_services
    row = measure(client)
    assert row['status'] == 'completed'
    assert row['end_to_end_seconds'] == pytest.approx(5.1)
    assert row['llm_seconds'] == 4 and row['llm_calls'] == 2
    assert row['mcp_tool_seconds'] == pytest.approx(1)
    assert row['lookup_tool_seconds'] == pytest.approx(.2)
    assert row['recommendation_tool_seconds'] == pytest.approx(.8)
    assert [call[0] for call in state.executed] == [evaluation.LOOKUP, evaluation.RECOMMEND]
    assert row['tool_calls'][-1]['evaluated_count'] == 20
    assert row['tool_calls'][-1]['snapshot_created'] is True
    assert 'snapshot-a' not in json.dumps(row)


@pytest.mark.parametrize('field,expected', [
    ('skip_tool', 'no_recommendation_result'), ('raise_error', 'RuntimeError'),
    ('tool_error', 'tool_error'), ('campaign_id', 'unexpected_campaign'),
])
def test_failures_are_excluded_from_completed_latency(fake_services, field, expected):
    state, client = fake_services
    setattr(state, field, 'wrong-campaign' if field == 'campaign_id' else True)
    row = measure(client)
    assert row['status'] == 'error' and row['error'] == expected
    assert row['end_to_end_seconds'] > 0 and 'secret-' not in json.dumps(row)
    if field == 'tool_error':
        assert row['tool_calls'][-1]['error_code'] == 'storage_unavailable'
    summary = evaluation.summarise([row])
    assert summary['completed'] == 0 and summary['errors'] == 1
    assert summary['completed_latency_seconds']['end_to_end_seconds']['mean'] is None
    assert summary['failed_end_to_end_seconds']['mean'] == row['end_to_end_seconds']


def test_unrelated_tool_is_blocked_before_execution(fake_services):
    state, _ = fake_services
    calls = []
    registry = evaluation.TimedRegistry(evaluation.MCPToolRegistry(None), calls)
    with pytest.raises(ValueError, match='Unrelated tool'):
        registry.execute('prepare_campaign_email', '{}')
    assert state.executed == []
    assert calls[0]['name'] == 'prepare_campaign_email' and calls[0]['error'] == 'ValueError'


def test_summary_percentiles_keep_failures_separate(fake_services):
    _, client = fake_services
    row = measure(client)
    failure = {**row, 'status': 'error', 'end_to_end_seconds': .01}
    result = evaluation.summarise([row, failure, {**row, 'end_to_end_seconds': 10}])
    assert (result['attempts'], result['completed'], result['errors']) == (3, 2, 1)
    stats = result['completed_latency_seconds']['end_to_end_seconds']
    assert stats['mean'] == pytest.approx(7.55) and stats['median'] == pytest.approx(7.55)
    assert stats['min'] == pytest.approx(5.1) and stats['max'] == stats['p95'] == 10
    assert result['failed_end_to_end_seconds']['mean'] == .01


@pytest.mark.parametrize('args', [
    ['--repeats', '0'], ['--repeats', '21'], ['--delay-seconds', '-1'],
    ['--delay-seconds', 'nan'], ['--delay-seconds', 'inf'],
    ['--dataset', 'small', '--case', 'large-1-young-families'],
])
def test_bad_options_stop_before_external_access(args):
    with pytest.raises(SystemExit) as error:
        evaluation.parse_arguments(args)
    assert error.value.code == 2


def test_listing_is_offline_and_both_sizes_use_identical_prompts(monkeypatch, capsys):
    def external_access(*_args):
        pytest.fail('Listing must not access database or provider settings')
    monkeypatch.setattr(evaluation, '_resolve_dataset', external_access)
    monkeypatch.setattr(evaluation, 'get_settings', external_access)
    assert evaluation.main(['--list-cases', '--dataset', 'small']) == 0
    output = capsys.readouterr().out
    assert 'small-1-young-families' in output and 'large-1-young-families' not in output
    assert output.count('small-') == 6
    assert [c.prompt for c in evaluation.CASES['small']] == [c.prompt for c in evaluation.CASES['large']]


@pytest.mark.parametrize('failed', [False, True])
def test_main_writes_report_and_returns_failure_status(monkeypatch, tmp_path, failed):
    spec = evaluation.DATASETS['small']
    monkeypatch.setattr(evaluation, 'RESULTS_DIR', tmp_path)
    monkeypatch.setattr(evaluation, '_resolve_dataset', lambda name: spec)
    monkeypatch.setattr(evaluation, '_campaign_id', lambda name: 'campaign-a')
    monkeypatch.setattr(evaluation, 'get_campaign', lambda *_: object())
    monkeypatch.setattr(evaluation, 'require_active', lambda *_: None)
    monkeypatch.setattr(evaluation, 'get_settings', lambda: SimpleNamespace(llm_configured=True, llm_model='fake-model'))
    monkeypatch.setattr(evaluation, '_in_process_mcp_server', lambda: object())
    monkeypatch.setattr(evaluation, 'LLMClient', lambda settings: object())
    delays = []
    monkeypatch.setattr(evaluation.time, 'sleep', delays.append)

    def run(case, run, *_args):
        return {
            'case_id': case.case_id, 'run': run, 'status': 'error' if failed else 'completed',
            'expected_outcome': case.expected_outcome,
            'error': 'RuntimeError' if failed else None,
            'end_to_end_seconds': 2., 'llm_seconds': 1., 'mcp_tool_seconds': .5,
            'lookup_tool_seconds': .1, 'recommendation_tool_seconds': .4,
        }
    monkeypatch.setattr(evaluation, 'measure_run', run)
    assert evaluation.main(['--dataset', 'small', '--case', 'small-1-young-families',
                            '--repeats', '2', '--delay-seconds', '.5']) == int(failed)
    reports = list(tmp_path.glob('client_recommendation_latency_small_*.json'))
    assert len(reports) == 1
    report = json.loads(reports[0].read_text())
    assert report['dataset'] == asdict(spec) and report['summary']['attempts'] == 2
    assert len(report['results']) == 2 and len(report['cases']) == 1
    assert report['measurement']['fresh_history'] is True
    assert 'Excel download' in report['measurement']['excludes'] and delays == [.5]


def test_dataset_mismatch_stops_before_model_or_output(monkeypatch, tmp_path):
    def mismatch(_name):
        raise SystemExit('Dataset counts do not match')
    monkeypatch.setattr(evaluation, '_resolve_dataset', mismatch)
    monkeypatch.setattr(evaluation, 'RESULTS_DIR', tmp_path)
    monkeypatch.setattr(evaluation, 'get_settings', lambda: pytest.fail('Must not prepare model'))
    with pytest.raises(SystemExit, match='Dataset counts'):
        evaluation.main(['--dataset', 'large'])
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('count', [20, 10000])
@pytest.mark.parametrize('recover', [False, True])
def test_real_orchestrator_mcp_lookup_and_matching_with_fake_provider(monkeypatch, count, recover):
    from datetime import date
    from app.campaigns import clock, matching, repository
    from app.campaigns.repository import Campaign, Client, Criteria
    from app.config import Settings
    from app.tools import campaign
    from test_campaign_mcp import server
    from test_orchestrator import FakeClient, completion, message, tool_call

    monkeypatch.setattr(clock, 'current_date', lambda: date(2026, 11, 10))
    record = Campaign('latency-eval', 'Young Families Cover Check', Criteria(age_groups=('under35',)))
    monkeypatch.setattr(repository, 'list_active_campaigns', lambda *_: (record,))
    def get_campaign(campaign_id, _scope):
        if campaign_id != 'latency-eval':
            raise repository.CampaignUnavailable('Campaign unavailable')
        return record
    monkeypatch.setattr(matching, 'get_campaign', get_campaign)
    monkeypatch.setattr(matching, 'list_clients_for_fa', lambda *_: tuple(
        Client(f'client-{i:05}', evaluation.EVAL_FA_ID, f'Synthetic {i}',
               '2000-01-01', 'Female', 10000) for i in range(count)))
    snapshots = []

    def save(scope, payload, session_id):
        snapshots.append((scope, len(payload['clients']), session_id))
        return {'list_id': '66666666-6666-4666-8666-666666666666', 'expires_at': '2026-11-11T00:00:00Z'}
    monkeypatch.setattr(campaign, 'save_list', save)
    responses = [
        completion(message(tool_calls=[tool_call('lookup', evaluation.LOOKUP,
            '{"campaign_name":"Young Families Cover Check"}')])),
    ]
    if recover:
        responses.append(completion(message(tool_calls=[tool_call('wrong', evaluation.RECOMMEND,
            '{"campaign_id":"wrong"}')])) )
    responses.extend([
        completion(message(tool_calls=[tool_call('recommend', evaluation.RECOMMEND,
            '{"campaign_id":"latency-eval"}')])),
        completion(message(content='Synthetic campaign criteria matches for adviser review.')),
    ])
    provider = FakeClient(responses)
    settings = Settings(_env_file=None, groq_api_key='test-key')
    row = evaluation.measure_run(evaluation.PROMPTS[0], 1, settings, server, provider, 'latency-eval')
    assert row['status'] == 'completed' and row['llm_calls'] == 3 + int(recover)
    assert row['recovered'] is recover and row['tool_error_count'] == int(recover)
    assert evaluation.summarise([row])['recovered'] == int(recover)
    assert row['end_to_end_seconds'] >= row['llm_seconds'] + row['mcp_tool_seconds']
    assert [call['name'] for call in row['tool_calls']] == [evaluation.LOOKUP] + [evaluation.RECOMMEND] * (1 + int(recover))
    if recover:
        assert row['tool_calls'][1]['error_code'] == 'campaign_unavailable'
    assert row['tool_calls'][-1]['evaluated_count'] == count
    assert row['tool_calls'][-1]['matched_count'] == count
    assert row['tool_calls'][-1]['returned_count'] == 10
    assert snapshots == [(evaluation.SCOPE, count, None)]
    model_result = json.loads(provider.calls[-1]['messages'][-1]['content'])
    assert len(model_result['clients']) == 10
    assert 'Synthetic 0' not in json.dumps(row)


@pytest.mark.parametrize('outcome', ['clarification', 'not_found'])
def test_expected_nonmatching_outcomes_are_completed(monkeypatch, outcome):
    from app.campaigns import repository
    from app.config import Settings
    from test_campaign_mcp import server
    from test_orchestrator import FakeClient, completion, message, tool_call

    case = next(case for case in evaluation.PROMPTS if case.expected_outcome == outcome)
    monkeypatch.setattr(repository, 'list_active_campaigns', lambda *_: ())
    responses = []
    if outcome == 'not_found':
        responses.append(completion(message(tool_calls=[tool_call('lookup', evaluation.LOOKUP,
            '{"campaign_name":"Nonexistent Evaluation Campaign Z9"}')])) )
    responses.append(completion(message(content=(
        'Which campaign would you like recommendations for?' if outcome == 'clarification'
        else 'No accessible active campaign matches that name. Please check the campaign name.'
    ))))
    row = evaluation.measure_run(case, 1, Settings(_env_file=None, groq_api_key='test-key'),
                                 server, FakeClient(responses), None)
    assert row['status'] == 'completed' and row['error'] is None
    assert row['recovered'] is False and row['recommendation_tool_seconds'] == 0
    assert row['llm_calls'] == (1 if outcome == 'clarification' else 2)
    if outcome == 'clarification':
        assert row['tool_calls'] == []
    else:
        assert row['tool_calls'][0]['lookup_status'] == 'not_found'
        assert row['tool_calls'][0]['error'] is None


def test_case_names_exist_in_both_sql_fixtures_and_only_three_prompts_are_substituted():
    from pathlib import Path
    fixtures = Path(evaluation.BACKEND_DIR) / 'tables' / 'eval_data'
    for size in ('small', 'large'):
        source = (fixtures / f'eval_{size}.sql').read_text()
        for case in evaluation.CASES[size]:
            if case.expected_outcome == 'recommendation':
                assert case.campaign in source
    assert len(evaluation.PROMPTS) == 6
    assert evaluation.PROMPTS[1].prompt == 'Who should I target for the legacy protection refresh campaign?'
    assert evaluation.PROMPTS[2].prompt == 'Which clients do you recommend?'
    assert evaluation.PROMPTS[3].prompt == 'Which clients do you recommend for Nonexistent Evaluation Campaign Z9?'
