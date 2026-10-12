-- Synthetic PULSE prototype only; not a production GCRM migration.
-- Versioned additive migration: PostgreSQL becomes authoritative for campaign UI state.
BEGIN;

CREATE TABLE IF NOT EXISTS pulse_schema_migration (
    migration_id VARCHAR(100) PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

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

-- Backfill the browser-only fields for the two existing synthetic campaigns once.
UPDATE mock_campaign
SET description = 'Q4 push on estate and legacy planning for our established client base. Priority is on clients approaching or past retirement who hold meaningful liquid assets but have not reviewed their protection cover in the last three years. Lead with the wealth transfer angle, not the premium.',
    client_message = 'Your protection plan was built for a different stage of life. We are offering complimentary legacy planning reviews this quarter — a 45-minute session covering how your current cover would pass on, what it would be worth after tax, and where the gaps sit. No obligation, and we can do it over a call.',
    origin = 'marketing', audience_source = 'contacts', channel = 'BANCA-SG',
    team_ids = '{}', advisor_ids = '{}', created_by = 'Marketing',
    created_at = '2026-08-17 00:00:00+08'
WHERE tenant_id = 'pulse-demo' AND campaign_id = 'camp-1'
  AND NOT EXISTS (
      SELECT 1 FROM pulse_schema_migration
      WHERE migration_id = '20261012_campaign_source_of_truth'
  );

UPDATE mock_campaign
SET description = 'Acquisition campaign aimed at younger clients and prospects entering the property market. Bundles mortgage protection with a starter critical illness rider at a reduced first-year premium. Marketing owns the digital spend; advisors handle follow-up on qualified leads only.',
    client_message = 'Buying your first home is the point most people are most exposed — a mortgage, and nothing standing behind it. Our starter bundle covers the loan and adds early-stage critical illness protection, at a reduced premium for the first year. Happy to walk you through the numbers.',
    origin = 'marketing', audience_source = 'contacts', channel = 'BANCA-SG',
    team_ids = ARRAY['marina-bay-branch']::text[], advisor_ids = '{}',
    created_by = 'Marketing', created_at = '2026-08-23 00:00:00+08'
WHERE tenant_id = 'pulse-demo' AND campaign_id = 'camp-2'
  AND NOT EXISTS (
      SELECT 1 FROM pulse_schema_migration
      WHERE migration_id = '20261012_campaign_source_of_truth'
  );

INSERT INTO pulse_schema_migration (migration_id)
VALUES ('20261012_campaign_source_of_truth')
ON CONFLICT DO NOTHING;

-- Keep the routing metadata and access table consistent for the checked-in demo
-- campaigns. The prototype has one sign-in adviser; broader directory routing
-- must not claim access that the database does not grant.
UPDATE mock_campaign
SET advisor_ids = ARRAY['adv-steven-raynaldi']::text[]
WHERE tenant_id = 'pulse-demo' AND campaign_id IN ('camp-1', 'camp-2')
  AND NOT EXISTS (
      SELECT 1 FROM pulse_schema_migration
      WHERE migration_id = '20261012_campaign_assignment_alignment'
  );

INSERT INTO pulse_schema_migration (migration_id)
VALUES ('20261012_campaign_assignment_alignment')
ON CONFLICT DO NOTHING;

COMMIT;
