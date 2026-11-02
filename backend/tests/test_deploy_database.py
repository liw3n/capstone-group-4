"""Opt-in bootstrap tests create disposable databases on a local test server."""
import importlib.util
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest

spec = importlib.util.spec_from_file_location("deploy_database", Path(__file__).parents[2] / "deploy/database.py")
database = importlib.util.module_from_spec(spec)
spec.loader.exec_module(database)


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
    with pytest.raises(psycopg.Error):
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
        assert connection.execute("SELECT count(*) FROM pulse_deploy_migration").fetchone()[0] == len(database.SCHEMA) + len(database.SEEDS)
