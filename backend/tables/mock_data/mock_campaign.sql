-- Synthetic PULSE prototype data only; not company GCRM records.
-- Full rows support clean provisioning. Guarded updates upgrade older local
-- databases once without overwriting later adviser or marketing edits.
BEGIN;

CREATE TABLE IF NOT EXISTS pulse_schema_migration (
    migration_id VARCHAR(100) PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO mock_campaign (
    tenant_id, campaign_id, name, status, start_date, end_date,
    age_groups, genders, cash_bands, age_min, age_max, cash_min, cash_max,
    description, client_message, origin, audience_source, channel,
    team_ids, advisor_ids, created_by, created_at
)
VALUES
    (
        'pulse-demo', 'camp-1', 'Legacy Protection Refresh', 'active',
        '2026-08-01', '2026-12-31',
        ARRAY['55to64', '65plus']::text[], ARRAY[]::text[],
        ARRAY['250kTo1m', 'above1m']::text[], NULL, NULL, NULL, NULL,
        'Q4 push on estate and legacy planning for our established client base. Priority is on clients approaching or past retirement who hold meaningful liquid assets but have not reviewed their protection cover in the last three years. Lead with the wealth transfer angle, not the premium.',
        'Your protection plan was built for a different stage of life. We are offering complimentary legacy planning reviews this quarter — a 45-minute session covering how your current cover would pass on, what it would be worth after tax, and where the gaps sit. No obligation, and we can do it over a call.',
        'marketing', 'contacts', 'BANCA-SG', ARRAY[]::text[],
        ARRAY['adv-steven-raynaldi']::text[], 'Marketing',
        '2026-08-17 00:00:00+08'
    ),
    (
        'pulse-demo', 'camp-2', 'First Home Starter Bundle', 'active',
        '2026-08-01', '2026-12-31',
        ARRAY['under35', '35to44']::text[], ARRAY[]::text[],
        ARRAY['under50k', '50kTo250k']::text[], NULL, NULL, NULL, NULL,
        'Acquisition campaign aimed at younger clients and prospects entering the property market. Bundles mortgage protection with a starter critical illness rider at a reduced first-year premium. Marketing owns the digital spend; advisors handle follow-up on qualified leads only.',
        'Buying your first home is the point most people are most exposed — a mortgage, and nothing standing behind it. Our starter bundle covers the loan and adds early-stage critical illness protection, at a reduced premium for the first year. Happy to walk you through the numbers.',
        'marketing', 'contacts', 'BANCA-SG',
        ARRAY['marina-bay-branch']::text[],
        ARRAY['adv-steven-raynaldi']::text[], 'Marketing',
        '2026-08-23 00:00:00+08'
    )
ON CONFLICT DO NOTHING;

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
