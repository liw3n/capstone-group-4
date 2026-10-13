INSERT INTO mock_client (tenant_id, contact_id, fa_id, name, date_of_birth, gender, available_cash, email)
VALUES
    ('pulse-demo', 'client-001', 'adv-steven-raynaldi', 'Demo Client A', '1968-08-26', 'female', 300000, 'demo.client.a@example.com'),
    ('pulse-demo', 'client-002', 'adv-steven-raynaldi', 'Demo Client B', '1956-08-26', 'male', 1000000, 'demo.client.b@example.com'),
    ('pulse-demo', 'client-003', 'adv-steven-raynaldi', 'Demo Client C', '1971-08-26', 'female', 250000, 'demo.client.c@example.com'),
    ('pulse-demo', 'client-004', 'adv-steven-raynaldi', 'Demo Client D', '1971-08-27', 'male', 300000, 'demo.client.d@example.com'),
    ('pulse-demo', 'client-005', 'adv-steven-raynaldi', 'Demo Client E', '1968-08-26', 'male', 249999, 'demo.client.e@example.com'),
    ('pulse-demo', 'client-006', 'adv-steven-raynaldi', 'Demo Client F', '1996-08-26', 'female', 49999, 'demo.client.f@example.com'),
    ('pulse-demo', 'client-007', 'adv-steven-raynaldi', 'Demo Client G', '1991-08-26', 'male', 50000, 'demo.client.g@example.com'),
    ('pulse-demo', 'client-008', 'adv-steven-raynaldi', 'Demo Client H', '1982-08-26', 'female', 249999, 'demo.client.h@example.com'),
    ('pulse-demo', 'client-009', 'adv-steven-raynaldi', 'Demo Client I', '1981-08-26', 'male', 50000, 'demo.client.i@example.com'),
    ('pulse-demo', 'client-010', 'adv-steven-raynaldi', 'Demo Client J', NULL, 'female', 300000, 'demo.client.j@example.com'),
    ('pulse-demo', 'client-011', 'adv-steven-raynaldi', 'Demo Client K', '1968-08-26', 'male', NULL, 'demo.client.k@example.com'),
    ('pulse-demo', 'client-012', 'adv-steven-raynaldi', 'Demo Client L', '1968-08-26', NULL, 300000, 'demo.client.l@example.com'),
    ('pulse-demo', 'client-013', 'adv-other-demo', 'Other FA Demo Client', '1968-08-26', 'male', 300000, 'demo.client.m@example.com'),
    ('other-demo-tenant', 'client-014', 'adv-steven-raynaldi', 'Other Tenant Demo Client', '1968-08-26', 'female', 300000, 'demo.client.n@example.com')
ON CONFLICT DO NOTHING;