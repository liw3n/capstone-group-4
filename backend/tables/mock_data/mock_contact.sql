-- Synthetic PULSE prototype data only; not company GCRM records.
-- Re-running preserves edits to rows that already exist.
BEGIN;

INSERT INTO contact (
    tenant_id, contact_id, contact_type, full_name, mobile, mobile_country_code, email,
    date_of_birth, opt_in_email, e_statement_opt_in,
    data_source, created_by_user_id
)
VALUES
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000001', 'Client', 'Demo Client A', '91111111', '+65', 'demo.client.a@example.test', '1968-08-26', TRUE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000002', 'Client', 'Demo Client B', '92222222', '+65', 'demo.client.b@example.test', '1956-08-26', FALSE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000003', 'Client', 'Demo Client C', '93333333', '+65', 'demo.client.c@example.test', '1971-06-26', TRUE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000004', 'Client', 'Demo Client D', '94444444', '+65', 'demo.client.d@example.test', '1971-08-27', FALSE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000005', 'Client', 'Demo Client E', '95555555', '+65', 'demo.client.e@example.test', '1968-04-26', FALSE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000006', 'Client', 'Demo Client F', '96666666', '+65', 'demo.client.f@example.test', '1996-03-26', TRUE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000007', 'Client', 'Demo Client G', '97777777', '+65', 'demo.client.g@example.test', '1991-08-26', FALSE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000008', 'Client', 'Demo Client H', '98888888', '+65', 'demo.client.h@example.test','1982-08-26', FALSE, TRUE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000009', 'Client', 'Demo Client I', '99999999', '+65', 'demo.client.i@example.test', '1981-08-26', FALSE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000010', 'Prospect', 'Demo Client J', '90000000', '+65', 'demo.client.j@example.test', NULL, FALSE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000011', 'Prospect', 'Demo Client K', '91234567', '+65', 'demo.client.k@example.test', '1968-08-26', FALSE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000012', 'Prospect', 'Demo Client L', '92345678', '+65', 'demo.client.l@example.test', '1968-08-26', FALSE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000013', 'Client', 'Demo Client M', '80000013', '+65', 'demo.client.m@example.test', '1960-02-15', TRUE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000014', 'Client', 'Demo Client N', '80000014', '+65', 'demo.client.n@example.test', '1955-07-10', TRUE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000015', 'Client', 'Demo Client O', '80000015', '+65', 'demo.client.o@example.test', '1965-04-21', FALSE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000016', 'Client', 'Demo Client P', '80000016', '+65', 'demo.client.p@example.test', '1969-09-03', TRUE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000017', 'Client', 'Demo Client Q', '80000017', '+65', 'demo.client.q@example.test', '1958-12-11', TRUE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000018', 'Client', 'Demo Client R', '80000018', '+65', 'demo.client.r@example.test', '1966-06-27', FALSE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000019', 'Client', 'Demo Client S', '80000019', '+65', 'demo.client.s@example.test', '1970-01-08', TRUE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000020', 'Client', 'Demo Client T', '80000020', '+65', 'demo.client.t@example.test', '1962-08-14', TRUE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000021', 'Client', 'Demo Client U', '80000021', '+65', 'demo.client.u@example.test', '1997-03-12', TRUE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000022', 'Client', 'Demo Client V', '80000022', '+65', 'demo.client.v@example.test', '1990-06-30', TRUE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000023', 'Client', 'Demo Client W', '80000023', '+65', 'demo.client.w@example.test', '2001-05-07', FALSE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000024', 'Client', 'Demo Client X', '80000024', '+65', 'demo.client.x@example.test', '1988-02-18', TRUE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000025', 'Client', 'Demo Client Y', '80000025', '+65', 'demo.client.y@example.test', '1994-10-01', TRUE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000026', 'Client', 'Demo Client Z', '80000026', '+65', 'demo.client.z@example.test', '1987-12-04', FALSE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000027', 'Client', 'Demo Client AA', '80000027', '+65', 'demo.client.aa@example.test', '1999-07-22', TRUE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000028', 'Client', 'Demo Client AB', '80000028', '+65', 'demo.client.ab@example.test', '1992-04-09', TRUE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000029', 'Client', 'Demo Client AC', '80000029', '+65', 'demo.client.ac@example.test', '1978-03-15', TRUE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000030', 'Client', 'Demo Client AD', '80000030', '+65', 'demo.client.ad@example.test', '1983-11-21', TRUE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000031', 'Client', 'Demo Client AE', '80000031', '+65', 'demo.client.ae@example.test', '1980-06-06', FALSE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000032', 'Client', 'Demo Client AF', '80000032', '+65', 'demo.client.af@example.test', '1975-02-13', TRUE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000033', 'Client', 'Demo Client AG', '80000033', '+65', 'demo.client.ag@example.test', '1986-04-20', TRUE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000034', 'Client', 'Demo Client AH', '80000034', '+65', 'demo.client.ah@example.test', '1973-09-08', FALSE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000035', 'Client', 'Demo Client AI', '80000035', '+65', 'demo.client.ai@example.test', '1984-01-30', TRUE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'd0000000-0000-0000-0000-000000000036', 'Client', 'Demo Client AJ', '80000036', '+65', 'demo.client.aj@example.test', '1977-12-19', TRUE, FALSE, 'Manual', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11')
ON CONFLICT (tenant_id, contact_id) DO NOTHING;

COMMIT;
