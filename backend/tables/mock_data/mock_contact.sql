-- Synthetic PULSE prototype data only; not company GCRM records.
-- Re-running preserves edits to rows that already exist.
BEGIN;

INSERT INTO contact (
    tenant_id, contact_id, contact_type, full_name, mobile, email,
    date_of_birth, opt_in_email, e_statement_opt_in,
    data_source, created_by_user_id
)
VALUES
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000001', 'Client', 'Demo Client A', '+65 91111111', 'demo.client.a@example.test', '1968-08-26', TRUE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000002', 'Client', 'Demo Client B', '+65 92222222', 'demo.client.b@example.test', '1956-08-26', FALSE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000003', 'Client', 'Demo Client C', '+65 93333333', 'demo.client.c@example.test', '1971-06-26', TRUE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000004', 'Client', 'Demo Client D', '+65 94444444', 'demo.client.d@example.test', '1971-08-27', FALSE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000005', 'Client', 'Demo Client E', '+65 95555555', 'demo.client.e@example.test', '1968-04-26', FALSE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000006', 'Client', 'Demo Client F', '+65 96666666', 'demo.client.f@example.test', '1996-03-26', TRUE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000007', 'Client', 'Demo Client G', '+65 97777777', 'demo.client.g@example.test', '1991-08-26', FALSE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000008', 'Client', 'Demo Client H', '+65 98888888', 'demo.client.h@example.test','1982-08-26', FALSE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000009', 'Client', 'Demo Client I', '+65 99999999', 'demo.client.i@example.test', '1981-08-26', FALSE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000010', 'Prospect', 'Demo Client J', '+65 90000000', 'demo.client.j@example.test', NULL, FALSE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000011', 'Prospect', 'Demo Client K', '+65 91234567', 'demo.client.k@example.test', '1968-08-26', FALSE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000012', 'Prospect', 'Demo Client L', '+65 92345678', 'demo.client.l@example.test', '1968-08-26', FALSE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11')
ON CONFLICT (tenant_id, contact_id) DO NOTHING;

COMMIT;