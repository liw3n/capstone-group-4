-- Synthetic PULSE prototype only; not a production GCRM migration.
-- Additive and repeatable. This does not alter the existing chat tables.
BEGIN;

CREATE TABLE IF NOT EXISTS mock_campaign (
    tenant_id VARCHAR(64) NOT NULL CHECK (length(btrim(tenant_id)) > 0),
    campaign_id VARCHAR(69) NOT NULL
        CHECK (campaign_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{0,68}$'),
    name VARCHAR(255) NOT NULL CHECK (length(btrim(name)) > 0),
    status VARCHAR(16) NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'active', 'paused', 'completed')),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    age_groups TEXT[] NOT NULL DEFAULT '{}'
        CHECK (age_groups <@ ARRAY['under35', '35to44', '45to54', '55to64', '65plus']::text[]
               AND array_position(age_groups, NULL) IS NULL),
    genders TEXT[] NOT NULL DEFAULT '{}'
        CHECK (genders <@ ARRAY['male', 'female']::text[]
               AND array_position(genders, NULL) IS NULL),
    cash_bands TEXT[] NOT NULL DEFAULT '{}'
        CHECK (cash_bands <@ ARRAY['under50k', '50kTo250k', '250kTo1m', 'above1m']::text[]
               AND array_position(cash_bands, NULL) IS NULL),
    age_min SMALLINT CHECK (age_min BETWEEN 0 AND 129),
    age_max SMALLINT CHECK (age_max BETWEEN 0 AND 129),
    cash_min NUMERIC(18, 2) CHECK (cash_min >= 0 AND cash_min < 'Infinity'::numeric),
    cash_max NUMERIC(18, 2) CHECK (cash_max >= 0 AND cash_max < 'Infinity'::numeric),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, campaign_id),
    CHECK (end_date >= start_date),
    CHECK (age_min IS NULL OR age_max IS NULL OR age_min <= age_max),
    CHECK (cash_min IS NULL OR cash_max IS NULL OR cash_min <= cash_max)
);

CREATE TABLE IF NOT EXISTS mock_campaign_advisor (
    tenant_id VARCHAR(64) NOT NULL,
    campaign_id VARCHAR(69) NOT NULL,
    fa_id VARCHAR(64) NOT NULL CHECK (length(btrim(fa_id)) > 0),
    PRIMARY KEY (tenant_id, campaign_id, fa_id),
    FOREIGN KEY (tenant_id, campaign_id)
        REFERENCES mock_campaign (tenant_id, campaign_id)
);

CREATE INDEX IF NOT EXISTS idx_mock_campaign_advisor_scope
    ON mock_campaign_advisor (tenant_id, fa_id, campaign_id);

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
    PRIMARY KEY (tenant_id, contact_id)
);

CREATE INDEX IF NOT EXISTS idx_mock_client_scope
    ON mock_client (tenant_id, fa_id, contact_id);

COMMENT ON TABLE mock_campaign IS 'Synthetic campaign criteria; not company GCRM schema';
COMMENT ON TABLE mock_campaign_advisor IS 'Synthetic tenant-scoped campaign access assignments';
COMMENT ON TABLE mock_client IS 'Synthetic review profiles; matching does not authorize outreach';
COMMIT;
