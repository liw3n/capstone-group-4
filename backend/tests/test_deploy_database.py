"""Opt-in bootstrap tests create disposable databases on a local test server."""
import importlib.util
import os
import hashlib
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4
from unittest.mock import MagicMock

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest

spec = importlib.util.spec_from_file_location("deploy_database", Path(__file__).parents[2] / "deploy/database.py")
database = importlib.util.module_from_spec(spec)
spec.loader.exec_module(database)


def test_baseline_seeds_match_first_deployed_commit():
    # Immutable digests from deployed commit 2ab0408; works in shallow checkouts.
    expected = {
        "mock_user_account.sql": "2dbb46a8e4e4faadea10abf59b211feb87ecd670e557f98b5dcfe51f5da8f76f",
        "mock_contact.sql": "cac2e4b7111aaa59ebe96c93f05d79d50803aac40170134c732a7115efba2024",
        "mock_campaign.sql": "e0612b2fe1869291a1d310795a24e95584d241f3aafe60bfb4b1779e3cf13441",
        "mock_campaign_member.sql": "4c28ddc50a30e3c10e60cb92c29c35b91c3ff9c0d56eee88eb6d905223c4ff19",
    }
    for name, digest in expected.items():
        assert hashlib.sha256((database.BACKEND / "tables/mock_data" / name).read_bytes()).hexdigest() == digest


@pytest.mark.parametrize("edited_dob", [False, True])
def test_upgrade_original_demo_preserves_edits(isolated_url, monkeypatch, edited_dob):
    updates = database.SEED_UPDATES
    with monkeypatch.context() as patch:
        patch.setattr(database, "SEED_UPDATES", ())
        patch.setattr(database, "SCHEMA", database.SCHEMA[:-1])
        database.run_database(isolated_url, seed=True)
    with psycopg.connect(isolated_url) as c:
        assert c.execute("SELECT count(*) FROM contact").fetchone()[0] == 36
        before = dict(c.execute("SELECT name, checksum FROM pulse_deploy_migration").fetchall())
        c.execute("UPDATE contact SET full_name='Tester edit' WHERE contact_id='d0000000-0000-0000-0000-000000000001'")
        c.execute("UPDATE campaign SET name='Tester campaign'")
        # Removal must not be undone by the new membership additions.
        c.execute("UPDATE contact SET is_deleted=true WHERE contact_id='d0000000-0000-0000-0000-000000000030'")
        if edited_dob:
            c.execute("UPDATE contact SET date_of_birth='1990-01-02', updated_at=now() WHERE contact_id='d0000000-0000-0000-0000-000000000010'")
    # Data updates must also work with DEMO_SEED_ON_START disabled after first boot.
    database.run_database(isolated_url, seed=False)
    with psycopg.connect(isolated_url) as c:
        assert c.execute("SELECT count(*) FROM contact").fetchone()[0] == 100
        assert c.execute("SELECT full_name FROM contact WHERE contact_id='d0000000-0000-0000-0000-000000000001'").fetchone()[0] == 'Tester edit'
        dob = c.execute("SELECT date_of_birth FROM contact WHERE contact_id='d0000000-0000-0000-0000-000000000010'").fetchone()[0]
        assert str(dob) == ('1990-01-02' if edited_dob else '1989-11-12')
        assert c.execute("SELECT count(*) FROM campaign WHERE name <> 'Tester campaign'").fetchone()[0] == 0
        assert c.execute("SELECT count(*) FROM campaign_member WHERE campaign_id='b2222222-2222-2222-2222-222222222222' AND contact_id='d0000000-0000-0000-0000-000000000030'").fetchone()[0] == 0
        after = dict(c.execute("SELECT name, checksum FROM pulse_deploy_migration").fetchall())
        assert all(after[name] == digest for name, digest in before.items())
        assert all(f'mock_data/{name}' in after for name in updates)
        c.execute("DELETE FROM contact WHERE contact_id='d0000000-0000-0000-0000-000000000100'")
        c.execute("UPDATE campaign_member SET is_deleted=true WHERE campaign_id='b2222222-2222-2222-2222-222222222222' AND contact_id='d0000000-0000-0000-0000-000000000033'")
    database.run_database(isolated_url, seed=True)
    with psycopg.connect(isolated_url) as c:
        assert c.execute("SELECT count(*) FROM contact").fetchone()[0] == 99
        assert c.execute("SELECT count(*) FROM campaign_member WHERE campaign_id='b2222222-2222-2222-2222-222222222222' AND contact_id='d0000000-0000-0000-0000-000000000033' AND NOT is_deleted").fetchone()[0] == 0


def test_unseeded_database_does_not_receive_demo_updates(isolated_url):
    database.run_database(isolated_url, seed=False)
    with psycopg.connect(isolated_url) as c:
        assert c.execute("SELECT count(*) FROM contact").fetchone()[0] == 0


def test_fresh_seed_includes_versioned_additions(isolated_url):
    database.run_database(isolated_url, seed=True)
    with psycopg.connect(isolated_url) as c:
        assert c.execute("SELECT count(*) FROM contact").fetchone()[0] == 100
        assert c.execute("SELECT count(*) FROM campaign_member WHERE campaign_id='b2222222-2222-2222-2222-222222222222'").fetchone()[0] == 13


def test_failed_data_update_rolls_back_upgrade(isolated_url, tmp_path, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(database, "SEED_UPDATES", ())
        patch.setattr(database, "SCHEMA", database.SCHEMA[:-1])
        database.run_database(isolated_url, seed=True)
    root = tmp_path / 'tables'
    shutil.copytree(database.BACKEND / 'tables', root)
    (root / 'mock_data' / database.SEED_UPDATES[1]).write_text('SELECT missing_sensitive_column;')
    with pytest.raises(database.BootstrapError, match='20261107_add_demo_members.sql'):
        database.run_database(isolated_url, seed=True, root=root)
    with psycopg.connect(isolated_url) as c:
        assert c.execute('SELECT count(*) FROM contact').fetchone()[0] == 36
        assert c.execute("SELECT to_regclass('campaign_recommendation_lists')").fetchone()[0] is None
        assert c.execute("SELECT count(*) FROM pulse_deploy_migration WHERE name LIKE '%20261107%'").fetchone()[0] == 0


def test_update_preserves_preexisting_soft_deleted_membership(isolated_url, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(database, 'SEED_UPDATES', ())
        database.run_database(isolated_url, seed=True)
    with psycopg.connect(isolated_url) as c:
        c.execute("""INSERT INTO campaign_member(tenant_id, campaign_id, contact_id,
            added_by_user_id, is_deleted) VALUES (
            'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
            'b2222222-2222-2222-2222-222222222222',
            'd0000000-0000-0000-0000-000000000033',
            'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', true)""")
    database.run_database(isolated_url, seed=True)
    with psycopg.connect(isolated_url) as c:
        rows = c.execute("SELECT is_deleted FROM campaign_member WHERE campaign_id='b2222222-2222-2222-2222-222222222222' AND contact_id='d0000000-0000-0000-0000-000000000033'").fetchall()
        assert rows == [(True,)]


def test_safe_checksum_error_reports_file_not_secrets(monkeypatch, capsys):
    monkeypatch.setattr(database.sys, "argv", ["database.py", "bootstrap"])
    monkeypatch.setattr(database, "get_settings", lambda: MagicMock())
    def fail(*args, **kwargs):
        raise database.BootstrapError("Applied SQL changed: mock_data/mock_contact.sql; add an explicit migration")
    monkeypatch.setattr(database, "run_database", fail)
    assert database.main() == 1
    assert 'mock_data/mock_contact.sql' in capsys.readouterr().err


def test_database_error_does_not_expose_connection_details(monkeypatch, capsys):
    monkeypatch.setattr(database.sys, "argv", ["database.py", "bootstrap"])
    monkeypatch.setattr(database, "get_settings", lambda: MagicMock())
    def fail(*args, **kwargs):
        raise psycopg.OperationalError('postgresql://secret-password@private-host')
    monkeypatch.setattr(database, "run_database", fail)
    assert database.main() == 1
    output = capsys.readouterr().err
    assert 'unavailable' in output
    assert 'secret-password' not in output and 'private-host' not in output


def test_bootstrap_sets_transaction_limits_without_startup_options(monkeypatch):
    connection = MagicMock()
    connect = MagicMock()
    connect.return_value.__enter__.return_value = connection
    monkeypatch.setattr(database.psycopg, "connect", connect)
    monkeypatch.setattr(database, "SCHEMA", ())
    database.run_database("postgresql://synthetic.invalid/postgres?sslmode=require")
    connect.assert_called_once_with(
        "postgresql://synthetic.invalid/postgres?sslmode=require", connect_timeout=10
    )
    statements = [call.args[0] for call in connection.execute.call_args_list]
    assert statements[:3] == [
        "SET LOCAL statement_timeout = '60s'",
        "SET LOCAL lock_timeout = '30s'",
        "SELECT pg_advisory_xact_lock(73421003)",
    ]


@pytest.fixture
def isolated_url():
    url = os.environ.get("PULSE_DEPLOY_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set PULSE_DEPLOY_TEST_DATABASE_URL to a local test server with CREATEDB permission")
    name = "pulse_deploy_test_" + uuid4().hex
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        yield make_conninfo(url, dbname=name)
    finally:
        with psycopg.connect(url, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))


def test_bootstrap_restarts_preserve_seed_edits(isolated_url):
    url = isolated_url
    database.run_database(url, seed=False)
    database.run_database(url, seed=True)
    with psycopg.connect(url) as connection:
        count = connection.execute("SELECT count(*) FROM campaign").fetchone()[0]
        assert count > 0
        connection.execute("UPDATE campaign SET name='Adviser edited synthetic campaign'")
    database.run_database(url, seed=True)
    with psycopg.connect(url) as connection:
        assert connection.execute("SELECT count(*) FROM campaign WHERE name='Adviser edited synthetic campaign'").fetchone()[0] == count


def test_failed_bootstrap_rolls_back(isolated_url, tmp_path, monkeypatch):
    url = isolated_url
    (tmp_path / "create").mkdir()
    (tmp_path / "create/broken.sql").write_text("CREATE TABLE test_partial(id int); SELECT absent_column;")
    monkeypatch.setattr(database, "SCHEMA", ("broken.sql",))
    with pytest.raises(database.BootstrapError, match="SQL execution failed: create/broken.sql"):
        database.run_database(url, root=tmp_path)
    with psycopg.connect(url) as connection:
        assert connection.execute("SELECT to_regclass('test_partial')").fetchone()[0] is None
        assert connection.execute("SELECT to_regclass('pulse_deploy_migration')").fetchone()[0] is None


def test_changed_applied_sql_is_rejected(isolated_url, tmp_path, monkeypatch):
    url = isolated_url
    (tmp_path / "create").mkdir()
    source = tmp_path / "create/initial.sql"
    source.write_text("CREATE TABLE checksum_example(id int);")
    monkeypatch.setattr(database, "SCHEMA", ("initial.sql",))
    database.run_database(url, root=tmp_path)
    source.write_text("CREATE TABLE checksum_example(id text);")
    with pytest.raises(ValueError, match="Applied SQL changed"):
        database.run_database(url, root=tmp_path)


def test_overlapping_starts_apply_each_file_once(isolated_url):
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: database.run_database(isolated_url, seed=True), range(2)))
    with psycopg.connect(isolated_url) as connection:
        assert connection.execute("SELECT count(*) FROM pulse_deploy_migration").fetchone()[0] == len(database.SCHEMA) + len(database.SEEDS) + len(database.SEED_UPDATES)
