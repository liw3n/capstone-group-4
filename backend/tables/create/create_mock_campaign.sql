-- Synthetic PULSE prototype only; not a production GCRM migration.
-- Additive and repeatable. This does not alter the existing chat tables.

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
    description TEXT NOT NULL DEFAULT '',
    client_message TEXT NOT NULL DEFAULT '',
    banner_data_url TEXT,
    origin VARCHAR(16) NOT NULL DEFAULT 'marketing'
        CHECK (origin IN ('marketing', 'advisor')),
    audience_source VARCHAR(16) NOT NULL DEFAULT 'contacts'
        CHECK (audience_source IN ('contacts', 'leads')),
    channel VARCHAR(64),
    team_ids TEXT[] NOT NULL DEFAULT '{}',
    advisor_ids TEXT[] NOT NULL DEFAULT '{}',
    created_by_advisor_id VARCHAR(64),
    created_by VARCHAR(255) NOT NULL DEFAULT 'Marketing',
    include_ids TEXT[] NOT NULL DEFAULT '{}',
    exclude_ids TEXT[] NOT NULL DEFAULT '{}',
    lead_ids TEXT[] NOT NULL DEFAULT '{}',
    lead_stats_uploaded INTEGER NOT NULL DEFAULT 0
        CHECK (lead_stats_uploaded >= 0),
    lead_stats_added INTEGER NOT NULL DEFAULT 0
        CHECK (lead_stats_added >= 0),
    lead_stats_removed INTEGER NOT NULL DEFAULT 0
        CHECK (lead_stats_removed >= 0),
    actions JSONB NOT NULL DEFAULT '{}'::jsonb,
    email_log JSONB NOT NULL DEFAULT '[]'::jsonb,
    lead_contacts JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, campaign_id),
    CHECK (end_date >= start_date),
    CHECK (age_min IS NULL OR age_max IS NULL OR age_min <= age_max),
    CHECK (cash_min IS NULL OR cash_max IS NULL OR cash_min <= cash_max)
);

-- Upgrade local databases created before the CRM-facing campaign fields were
-- folded into this canonical table definition. All additions are repeatable.
ALTER TABLE mock_campaign
    ADD COLUMN IF NOT EXISTS description TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS client_message TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS banner_data_url TEXT,
    ADD COLUMN IF NOT EXISTS origin VARCHAR(16) NOT NULL DEFAULT 'marketing'
        CHECK (origin IN ('marketing', 'advisor')),
    ADD COLUMN IF NOT EXISTS audience_source VARCHAR(16) NOT NULL DEFAULT 'contacts'
        CHECK (audience_source IN ('contacts', 'leads')),
    ADD COLUMN IF NOT EXISTS channel VARCHAR(64),
    ADD COLUMN IF NOT EXISTS team_ids TEXT[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS advisor_ids TEXT[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS created_by_advisor_id VARCHAR(64),
    ADD COLUMN IF NOT EXISTS created_by VARCHAR(255) NOT NULL DEFAULT 'Marketing',
    ADD COLUMN IF NOT EXISTS include_ids TEXT[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS exclude_ids TEXT[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS lead_ids TEXT[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS lead_stats_uploaded INTEGER NOT NULL DEFAULT 0
        CHECK (lead_stats_uploaded >= 0),
    ADD COLUMN IF NOT EXISTS lead_stats_added INTEGER NOT NULL DEFAULT 0
        CHECK (lead_stats_added >= 0),
    ADD COLUMN IF NOT EXISTS lead_stats_removed INTEGER NOT NULL DEFAULT 0
        CHECK (lead_stats_removed >= 0),
    ADD COLUMN IF NOT EXISTS actions JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS email_log JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS lead_contacts JSONB NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON TABLE mock_campaign IS 'Synthetic campaign criteria; not company GCRM schema';
