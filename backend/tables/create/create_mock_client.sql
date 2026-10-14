CREATE TABLE IF NOT EXISTS mock_client (
    tenant_id VARCHAR(64) NOT NULL CHECK (length(btrim(tenant_id)) > 0),
    contact_id VARCHAR(64) NOT NULL CHECK (length(btrim(contact_id)) > 0),
    fa_id VARCHAR(64) NOT NULL CHECK (length(btrim(fa_id)) > 0),
    name VARCHAR(255) NOT NULL CHECK (length(btrim(name)) > 0),
    date_of_birth DATE,
    gender VARCHAR(16) CHECK (gender IN ('male', 'female')),
    available_cash NUMERIC(18, 2)
        CHECK (available_cash >= 0 AND available_cash < 'Infinity'::numeric),
    email VARCHAR(320) NOT NULL
        CHECK (email ~* '^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$'),
    country_code VARCHAR(8) NOT NULL DEFAULT '+65',
    phone VARCHAR(32) NOT NULL DEFAULT '',
    label VARCHAR(16) CHECK (label IN ('Prospect', 'Client')),
    status VARCHAR(16) NOT NULL DEFAULT 'contact'
        CHECK (status IN ('lead', 'contact')),
    bookmarked BOOLEAN NOT NULL DEFAULT FALSE,
    needs_attention BOOLEAN NOT NULL DEFAULT FALSE,
    opt_in_email BOOLEAN NOT NULL DEFAULT FALSE,
    opt_in_sms BOOLEAN NOT NULL DEFAULT FALSE,
    crm_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, contact_id)
);

-- Upgrade local databases created before mock_client became the CRM display
-- source. Backfill values are applied once by mock_data/mock_client.sql.
ALTER TABLE mock_client
    ADD COLUMN IF NOT EXISTS email VARCHAR(320)
        CHECK (email ~* '^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$'),
    ADD COLUMN IF NOT EXISTS country_code VARCHAR(8) NOT NULL DEFAULT '+65',
    ADD COLUMN IF NOT EXISTS phone VARCHAR(32) NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS label VARCHAR(16)
        CHECK (label IN ('Prospect', 'Client')),
    ADD COLUMN IF NOT EXISTS status VARCHAR(16) NOT NULL DEFAULT 'contact'
        CHECK (status IN ('lead', 'contact')),
    ADD COLUMN IF NOT EXISTS bookmarked BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS needs_attention BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS crm_data JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE mock_client
    ALTER COLUMN email TYPE VARCHAR(320);

-- Preserve unknown legacy rows with a null email instead of inventing contact
-- data. Fresh databases and populated legacy demo databases enforce NOT NULL.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM mock_client WHERE email IS NULL) THEN
        ALTER TABLE mock_client ALTER COLUMN email SET NOT NULL;
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_mock_client_scope
    ON mock_client (tenant_id, fa_id, contact_id);

COMMENT ON TABLE mock_client IS 'Synthetic review profiles; matching does not authorize outreach';
