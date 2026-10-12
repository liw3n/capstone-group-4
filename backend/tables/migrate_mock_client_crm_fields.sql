-- Synthetic PULSE prototype only; not a production GCRM migration.
-- Adds the minimum CRM presentation fields needed for mock_client to be the
-- frontend and MCP source of truth.
BEGIN;

CREATE TABLE IF NOT EXISTS pulse_schema_migration (
    migration_id VARCHAR(100) PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE mock_client
    ADD COLUMN IF NOT EXISTS email VARCHAR(320) NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS country_code VARCHAR(8) NOT NULL DEFAULT '+65',
    ADD COLUMN IF NOT EXISTS phone VARCHAR(32) NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS label VARCHAR(16)
        CHECK (label IN ('Prospect', 'Client')),
    ADD COLUMN IF NOT EXISTS status VARCHAR(16) NOT NULL DEFAULT 'contact'
        CHECK (status IN ('lead', 'contact')),
    ADD COLUMN IF NOT EXISTS bookmarked BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS needs_attention BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS crm_data JSONB NOT NULL DEFAULT '{}'::jsonb;

UPDATE mock_client
SET email = CASE contact_id
        WHEN 'client-001' THEN 'demo.client.a@example.test'
        WHEN 'client-002' THEN 'demo.client.b@example.test'
        WHEN 'client-003' THEN 'demo.client.c@example.test'
        WHEN 'client-004' THEN 'demo.client.d@example.test'
        WHEN 'client-005' THEN 'demo.client.e@example.test'
        WHEN 'client-006' THEN 'demo.client.f@example.test'
        WHEN 'client-007' THEN 'demo.client.g@example.test'
        WHEN 'client-008' THEN 'demo.client.h@example.test'
        WHEN 'client-009' THEN 'demo.client.i@example.test'
        WHEN 'client-010' THEN 'demo.client.j@example.test'
        WHEN 'client-011' THEN 'demo.client.k@example.test'
        WHEN 'client-012' THEN 'demo.client.l@example.test'
        WHEN 'client-013' THEN 'other.adviser.client@example.test'
        WHEN 'client-014' THEN 'other.tenant.client@example.test'
        ELSE email
    END,
    label = CASE
        WHEN contact_id IN ('client-010', 'client-011', 'client-012') THEN 'Prospect'
        ELSE 'Client'
    END,
    crm_data = jsonb_build_object('source', 'own')
WHERE NOT EXISTS (
    SELECT 1 FROM pulse_schema_migration
    WHERE migration_id = '20261012_mock_client_crm_fields'
);

INSERT INTO pulse_schema_migration (migration_id)
VALUES ('20261012_mock_client_crm_fields')
ON CONFLICT DO NOTHING;

COMMIT;
