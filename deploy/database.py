"""Locked, checksummed schema setup and once-only synthetic seeding for demos."""
import hashlib
import re
import sys
from pathlib import Path

import psycopg

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))
from app.config import get_settings

SCHEMA = (
    "create_campaign_chat_sessions.sql", "create_campaign_generation_clarifications.sql",
    "create_campaign_generation_drafts.sql", "create_campaign_chat_messages.sql",
    "create_mock_user_account.sql", "create_campaign.sql", "create_contact.sql",
    "create_campaign_member.sql", "create_campaign_email_send.sql",
    "create_campaign_recommendation_lists.sql",
)
SEEDS = ("mock_user_account.sql", "mock_contact.sql", "mock_campaign.sql", "mock_campaign_member.sql")


def run_database(url, *, seed=False, root=BACKEND / "tables"):
    if not url:
        raise ValueError("DATABASE_URL is required")
    with psycopg.connect(url, connect_timeout=10) as connection:
        # Set limits inside the transaction, not via startup options which
        # managed poolers need not forward. Session pooling preserves SQL state.
        connection.execute("SET LOCAL statement_timeout = '60s'")
        connection.execute("SET LOCAL lock_timeout = '30s'")
        # Transaction-scoped lock serializes overlapping starts and releases on failure.
        connection.execute("SELECT pg_advisory_xact_lock(73421003)")
        connection.execute("""CREATE TABLE IF NOT EXISTS pulse_deploy_migration (
            name TEXT PRIMARY KEY, checksum TEXT NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        for folder, filenames in (("create", SCHEMA), ("mock_data", SEEDS if seed else ())):
            for filename in filenames:
                name = f"{folder}/{filename}"
                source = (root / name).read_text()
                digest = hashlib.sha256(source.encode()).hexdigest()
                row = connection.execute("SELECT checksum FROM pulse_deploy_migration WHERE name=%s", (name,)).fetchone()
                if row:
                    if row[0] != digest:
                        raise ValueError(f"Applied SQL changed: {name}; add an explicit migration")
                    continue
                # Existing seed files contain transaction wrappers. The outer
                # transaction owns the entire bootstrap, lock and ledger instead.
                source = re.sub(r"(?mi)^\s*(BEGIN|COMMIT);\s*$", "", source)
                connection.execute(source, prepare=False)
                connection.execute("INSERT INTO pulse_deploy_migration(name, checksum) VALUES (%s,%s)", (name, digest))
                print(f"Applied {name}", flush=True)


def main():
    try:
        mode = sys.argv[1] if len(sys.argv) == 2 else ""
        if mode not in {"bootstrap", "migrate", "seed"}:
            raise ValueError("Use bootstrap, migrate or seed")
        settings = get_settings()
        run_database(settings.database_url, seed=mode == "seed" or (mode == "bootstrap" and settings.demo_seed_on_start))
    except Exception:
        # Provider/validation exceptions can contain connection strings or input secrets.
        print("Database bootstrap failed. Check configuration, SQL checksums and database availability; no service started.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
