INSERT INTO mock_campaign (tenant_id, campaign_id, name, status, start_date, end_date, age_groups, genders, cash_bands, age_min, age_max, cash_min, cash_max)
VALUES
    ('pulse-demo', 'camp-1', 'Legacy Protection Refresh', 'active', '2026-08-01', '2026-12-31', ARRAY['55to64', '65plus']::text[], ARRAY[]::text[], ARRAY['250kTo1m', 'above1m']::text[], NULL, NULL, NULL, NULL),
    ('pulse-demo', 'camp-2', 'First Home Starter Bundle', 'active', '2026-08-01', '2026-12-31', ARRAY['under35', '35to44']::text[], ARRAY[]::text[], ARRAY['under50k', '50kTo250k']::text[], NULL, NULL, NULL, NULL)
ON CONFLICT DO NOTHING;