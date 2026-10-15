-- Synthetic PULSE prototype data only; not company GCRM records.
-- Re-running preserves edits to rows that already exist.
BEGIN;

CREATE TABLE IF NOT EXISTS pulse_schema_migration (
    migration_id VARCHAR(100) PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO mock_client (
    tenant_id, contact_id, fa_id, name, date_of_birth, gender,
    available_cash, email, label, opt_in_email, crm_data
)
VALUES
    ('pulse-demo', 'client-001', 'adv-steven-raynaldi', 'Demo Client A', '1968-08-26', 'female', 300000, 'demo.client.a@example.test', 'Client', TRUE, '{"source": "own"}'::jsonb),
    ('pulse-demo', 'client-002', 'adv-steven-raynaldi', 'Demo Client B', '1956-08-26', 'male', 1000000, 'demo.client.b@example.test', 'Client', FALSE, '{"source": "own"}'::jsonb),
    ('pulse-demo', 'client-003', 'adv-steven-raynaldi', 'Demo Client C', '1971-08-26', 'female', 250000, 'demo.client.c@example.test', 'Client', TRUE, '{"source": "own"}'::jsonb),
    ('pulse-demo', 'client-004', 'adv-steven-raynaldi', 'Demo Client D', '1971-08-27', 'male', 300000, 'demo.client.d@example.test', 'Client', FALSE, '{"source": "own"}'::jsonb),
    ('pulse-demo', 'client-005', 'adv-steven-raynaldi', 'Demo Client E', '1968-08-26', 'male', 249999, 'demo.client.e@example.test', 'Client', FALSE, '{"source": "own"}'::jsonb),
    ('pulse-demo', 'client-006', 'adv-steven-raynaldi', 'Demo Client F', '1996-08-26', 'female', 49999, 'demo.client.f@example.test', 'Client', TRUE, '{"source": "own"}'::jsonb),
    ('pulse-demo', 'client-007', 'adv-steven-raynaldi', 'Demo Client G', '1991-08-26', 'male', 50000, 'demo.client.g@example.test', 'Client', FALSE, '{"source": "own"}'::jsonb),
    ('pulse-demo', 'client-008', 'adv-steven-raynaldi', 'Demo Client H', '1982-08-26', 'female', 249999, 'demo.client.h@example.test', 'Client', FALSE, '{"source": "own"}'::jsonb),
    ('pulse-demo', 'client-009', 'adv-steven-raynaldi', 'Demo Client I', '1981-08-26', 'male', 50000, 'demo.client.i@example.test', 'Client', FALSE, '{"source": "own"}'::jsonb),
    ('pulse-demo', 'client-010', 'adv-steven-raynaldi', 'Demo Client J', NULL, 'female', 300000, 'demo.client.j@example.test', 'Prospect', FALSE, '{"source": "own"}'::jsonb),
    ('pulse-demo', 'client-011', 'adv-steven-raynaldi', 'Demo Client K', '1968-08-26', 'male', NULL, 'demo.client.k@example.test', 'Prospect', FALSE, '{"source": "own"}'::jsonb),
    ('pulse-demo', 'client-012', 'adv-steven-raynaldi', 'Demo Client L', '1968-08-26', NULL, 300000, 'demo.client.l@example.test', 'Prospect', FALSE, '{"source": "own"}'::jsonb),
    ('pulse-demo', 'client-013', 'adv-other-demo', 'Other FA Demo Client', '1968-08-26', 'male', 300000, 'other.adviser.client@example.test', 'Client', FALSE, '{"source": "own"}'::jsonb),
    ('other-demo-tenant', 'client-014', 'adv-steven-raynaldi', 'Other Tenant Demo Client', '1968-08-26', 'female', 300000, 'other.tenant.client@example.test', 'Client', FALSE, '{"source": "own"}'::jsonb)
ON CONFLICT DO NOTHING;

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
WHERE (
        (tenant_id = 'pulse-demo' AND contact_id IN (
            'client-001', 'client-002', 'client-003', 'client-004',
            'client-005', 'client-006', 'client-007', 'client-008',
            'client-009', 'client-010', 'client-011', 'client-012',
            'client-013'
        ))
        OR (tenant_id = 'other-demo-tenant' AND contact_id = 'client-014')
    )
  AND NOT EXISTS (
      SELECT 1 FROM pulse_schema_migration
      WHERE migration_id = '20261012_mock_client_crm_fields'
  );

INSERT INTO pulse_schema_migration (migration_id)
VALUES ('20261012_mock_client_crm_fields')
ON CONFLICT DO NOTHING;

COMMIT;
