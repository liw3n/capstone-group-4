-- Synthetic data only. Re-running preserves edits to existing demo rows.
BEGIN;

INSERT INTO mock_campaign (tenant_id, campaign_id, name, status, start_date, end_date, age_groups, genders, cash_bands, age_min, age_max, cash_min, cash_max)
VALUES
    ('pulse-demo', 'camp-1', 'Legacy Protection Refresh', 'active', '2026-08-01', '2026-12-31', ARRAY['55to64', '65plus']::text[], ARRAY[]::text[], ARRAY['250kTo1m', 'above1m']::text[], NULL, NULL, NULL, NULL),
    ('pulse-demo', 'camp-2', 'First Home Starter Bundle', 'active', '2026-08-01', '2026-12-31', ARRAY['under35', '35to44']::text[], ARRAY[]::text[], ARRAY['under50k', '50kTo250k']::text[], NULL, NULL, NULL, NULL)
ON CONFLICT DO NOTHING;

INSERT INTO mock_campaign_advisor (tenant_id, campaign_id, fa_id)
VALUES
    ('pulse-demo', 'camp-1', 'adv-steven-raynaldi'),
    ('pulse-demo', 'camp-2', 'adv-steven-raynaldi')
ON CONFLICT DO NOTHING;

INSERT INTO mock_client (tenant_id, contact_id, fa_id, name, date_of_birth, gender, available_cash)
VALUES
    ('pulse-demo', 'client-001', 'adv-steven-raynaldi', 'Demo Client A', '1968-08-26', 'female', 300000),
    ('pulse-demo', 'client-002', 'adv-steven-raynaldi', 'Demo Client B', '1956-08-26', 'male', 1000000),
    ('pulse-demo', 'client-003', 'adv-steven-raynaldi', 'Demo Client C', '1971-08-26', 'female', 250000),
    ('pulse-demo', 'client-004', 'adv-steven-raynaldi', 'Demo Client D', '1971-08-27', 'male', 300000),
    ('pulse-demo', 'client-005', 'adv-steven-raynaldi', 'Demo Client E', '1968-08-26', 'male', 249999),
    ('pulse-demo', 'client-006', 'adv-steven-raynaldi', 'Demo Client F', '1996-08-26', 'female', 49999),
    ('pulse-demo', 'client-007', 'adv-steven-raynaldi', 'Demo Client G', '1991-08-26', 'male', 50000),
    ('pulse-demo', 'client-008', 'adv-steven-raynaldi', 'Demo Client H', '1982-08-26', 'female', 249999),
    ('pulse-demo', 'client-009', 'adv-steven-raynaldi', 'Demo Client I', '1981-08-26', 'male', 50000),
    ('pulse-demo', 'client-010', 'adv-steven-raynaldi', 'Demo Client J', NULL, 'female', 300000),
    ('pulse-demo', 'client-011', 'adv-steven-raynaldi', 'Demo Client K', '1968-08-26', 'male', NULL),
    ('pulse-demo', 'client-012', 'adv-steven-raynaldi', 'Demo Client L', '1968-08-26', NULL, 300000),
    ('pulse-demo', 'client-013', 'adv-other-demo', 'Other FA Demo Client', '1968-08-26', 'male', 300000),
    ('other-demo-tenant', 'client-014', 'adv-steven-raynaldi', 'Other Tenant Demo Client', '1968-08-26', 'female', 300000)
ON CONFLICT DO NOTHING;

COMMIT;
