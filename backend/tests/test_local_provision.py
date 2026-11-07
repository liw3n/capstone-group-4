"""Run setup's actual SQL phase without Terraform, FakeCloud or .env writes."""
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
import pytest

BACKEND = Path(__file__).parents[1]


def sql_phase():
    source = (BACKEND / 'setup.sh').read_text()
    start = source.index('run_sql_file() {')
    end = source.index('if [[ "${DEPLOY_FAKECLOUD_ECS:-0}" != "1" ]]')
    return source[start:end]


def run_phase(env):
    return subprocess.run(['bash', '-euo', 'pipefail', '-c', sql_phase()],
                          env={**os.environ, 'BACKEND_DIR': str(BACKEND), **env},
                          text=True, capture_output=True, timeout=30)


@pytest.fixture
def fake_psql(tmp_path):
    executable = tmp_path / 'psql'
    executable.write_text(f'#!{sys.executable}\n' + '''
import json, os, pathlib, sys
args = sys.argv[1:]
filename = args[args.index('--file') + 1] if '--file' in args else None
source = pathlib.Path(filename).read_text() if filename else sys.stdin.read()
with open(os.environ['PROVISION_CAPTURE'], 'a') as output:
    output.write(json.dumps({'file': filename, 'sql': source}) + '\\n')
if os.environ.get('PROVISION_FAIL_ON') and os.environ['PROVISION_FAIL_ON'] in source:
    print('Synthetic SQL failure', file=sys.stderr)
    sys.exit(12)
''')
    executable.chmod(0o755)
    capture = tmp_path / 'capture.jsonl'
    env = {'PATH': f'{tmp_path}{os.pathsep}{os.environ["PATH"]}',
           'PROVISION_CAPTURE': str(capture), 'rds_host': 'synthetic.invalid', 'rds_port': '5432'}
    return env, capture


def test_local_setup_registers_snapshot_before_seeding_and_guards_only_member_index(fake_psql):
    env, capture = fake_psql
    definition = BACKEND / 'tables/create/create_campaign_member.sql'
    original = sha256(definition.read_bytes()).hexdigest()
    result = run_phase(env)
    assert result.returncode == 0, result.stderr
    calls = [json.loads(line) for line in capture.read_text().splitlines()]
    snapshot = next(i for i, call in enumerate(calls) if 'CREATE TABLE IF NOT EXISTS campaign_recommendation_lists' in call['sql'])
    seed = next(i for i, call in enumerate(calls) if 'INSERT INTO user_account' in call['sql'])
    assert snapshot < seed
    member = next(call for call in calls if 'CREATE TABLE IF NOT EXISTS campaign_member (' in call['sql'])
    assert member['file'] is None  # Transformed stream, never a rewritten schema file.
    assert 'CREATE UNIQUE INDEX IF NOT EXISTS ux_campaign_member_tenant_campaign_contact' in member['sql']
    assert sha256(definition.read_bytes()).hexdigest() == original


def test_local_setup_stops_on_other_sql_errors(fake_psql):
    env, capture = fake_psql
    result = run_phase({**env, 'PROVISION_FAIL_ON': 'CREATE TABLE IF NOT EXISTS campaign_recommendation_lists'})
    assert result.returncode == 12
    assert 'Synthetic SQL failure' in result.stderr
    assert 'INSERT INTO user_account' not in capture.read_text()


def test_repeated_local_sql_provision_preserves_edits_and_snapshots():
    url = os.environ.get('PULSE_PROVISION_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Set PULSE_PROVISION_TEST_DATABASE_URL to a disposable local pulse database')
    params = conninfo_to_dict(url)
    if params.get('dbname') != 'pulse':
        pytest.fail('Local setup uses the pulse database; use a disposable PostgreSQL server')
    schema = 'pulse_provision_test_' + uuid4().hex
    definition = BACKEND / 'tables/create/create_campaign_member.sql'
    original = sha256(definition.read_bytes()).hexdigest()
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        try:
            options = f'-c search_path={schema},public'
            env = {'rds_host': params.get('host', '127.0.0.1'), 'rds_port': params.get('port', '5432'),
                   'PGOPTIONS': options}
            with psycopg.connect(make_conninfo(url, options=options), autocommit=True) as connection:
                result = run_phase(env)
                assert result.returncode == 0, result.stderr
                assert connection.execute("SELECT to_regclass('campaign_recommendation_lists')").fetchone()[0]
                index = connection.execute("SELECT to_regclass('ux_campaign_member_tenant_campaign_contact')::oid").fetchone()[0]
                assert index
                counts = connection.execute('SELECT (SELECT count(*) FROM contact), (SELECT count(*) FROM campaign_member)').fetchone()
                contact_id = connection.execute('SELECT contact_id FROM contact ORDER BY contact_id LIMIT 1').fetchone()[0]
                connection.execute('UPDATE contact SET full_name = %s WHERE contact_id = %s', ('Adviser-edited synthetic name', contact_id))
                list_id = uuid4()
                connection.execute("""INSERT INTO campaign_recommendation_lists
                    (list_id, tenant_id, fa_id, campaign_id, expires_at, payload)
                    VALUES (%s, 'test', 'test', 'test', now() + interval '1 day', '{}'::jsonb)""", (list_id,))
                result = run_phase(env)
                assert result.returncode == 0, result.stderr
                assert connection.execute('SELECT full_name FROM contact WHERE contact_id = %s', (contact_id,)).fetchone()[0] == 'Adviser-edited synthetic name'
                assert connection.execute('SELECT (SELECT count(*) FROM contact), (SELECT count(*) FROM campaign_member)').fetchone() == counts
                assert connection.execute('SELECT count(*) FROM campaign_recommendation_lists WHERE list_id = %s', (list_id,)).fetchone()[0] == 1
                assert connection.execute("SELECT to_regclass('ux_campaign_member_tenant_campaign_contact')::oid").fetchone()[0] == index
                assert sha256(definition.read_bytes()).hexdigest() == original
        finally:
            admin.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
