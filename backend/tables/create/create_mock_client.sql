CREATE TABLE IF NOT EXISTS mock_client (
    tenant_id VARCHAR(64) NOT NULL CHECK (length(btrim(tenant_id)) > 0),
    contact_id VARCHAR(64) NOT NULL CHECK (length(btrim(contact_id)) > 0),
    fa_id VARCHAR(64) NOT NULL CHECK (length(btrim(fa_id)) > 0),
    name VARCHAR(255) NOT NULL CHECK (length(btrim(name)) > 0),
    date_of_birth DATE,
    gender VARCHAR(16) CHECK (gender IN ('male', 'female')),
    available_cash NUMERIC(18, 2)
        CHECK (available_cash >= 0 AND available_cash < 'Infinity'::numeric),
    opt_in_email BOOLEAN NOT NULL DEFAULT FALSE,
    opt_in_sms BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    email VARCHAR(255) CHECK (email ~* '^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$'),
    PRIMARY KEY (tenant_id, contact_id)
);

CREATE INDEX IF NOT EXISTS idx_mock_client_scope
    ON mock_client (tenant_id, fa_id, contact_id);

COMMENT ON TABLE mock_client IS 'Synthetic review profiles; matching does not authorize outreach';