-- Synthetic PULSE evaluation dataset (small); not company GCRM records.
-- 5 campaigns, 20 contacts and 66 campaign_member rows for one demo adviser.
-- Identifiers are deterministic so evaluation prompts can name campaigns and
-- compute expected results. Re-running is idempotent.
BEGIN;

INSERT INTO user_account (tenant_id, user_id)
VALUES ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11')
ON CONFLICT (tenant_id, user_id) DO NOTHING;

INSERT INTO campaign (
    tenant_id, campaign_id, campaign_code, name, description, status,
    start_date, end_date, audience_source, client_messaging, audience_criteria,
    email_send_runs, created_by_user_id
)
SELECT 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'::uuid,
       ('5a000000-0000-0000-0000-' || lpad(c.n::text, 12, '0'))::uuid,
       'DEMO-S-' || lpad(c.n::text, 3, '0'),
       c.name, c.description, 'active',
       DATE '2026-09-01', DATE '2027-06-30', 'contacts', c.messaging,
       c.criteria::jsonb, 1,
       'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'::uuid
FROM (VALUES
    (1, 'Legacy Protection Refresh',
     'Synthetic demo: estate and legacy planning reviews for established clients.',
     'We are offering complimentary legacy planning reviews this quarter.',
     '{"ageGroups": ["55to64", "65plus"], "genders": [], "cashBands": ["250kTo1m", "above1m"]}'),
    (2, 'Young Families Cover Check',
     'Synthetic demo: protection gap check-ins for younger households.',
     'A short review can confirm your family cover still fits your needs.',
     '{"ageGroups": ["under35", "35to44"], "genders": [], "cashBands": []}'),
    (3, 'Retirement Income Review',
     'Synthetic demo: educational sessions on retirement income planning.',
     'Learn how different income sources can work together in retirement.',
     '{"ageGroups": ["45to54", "55to64"], "genders": [], "cashBands": ["50kTo250k", "250kTo1m"]}'),
    (4, 'Education Savings Kickstart',
     'Synthetic demo: education savings awareness for parents.',
     'Starting early can make education goals easier to plan for.',
     '{"ageGroups": ["35to44", "45to54"], "genders": [], "cashBands": []}'),
    (5, 'Year-End Portfolio Health Check',
     'Synthetic demo: year-end portfolio review invitations.',
     'Book a year-end review to revisit your goals and risk profile.',
     '{"ageGroups": [], "genders": [], "cashBands": ["250kTo1m", "above1m"]}')
) AS c(n, name, description, messaging, criteria)
ON CONFLICT (tenant_id, campaign_id) DO NOTHING;

INSERT INTO contact (
    tenant_id, contact_id, contact_type, full_name, mobile, mobile_country_code, email,
    date_of_birth, opt_in_email, e_statement_opt_in, data_source, created_by_user_id
)
SELECT 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'::uuid,
       ('5c000000-0000-0000-0000-' || lpad(n::text, 12, '0'))::uuid,
       CASE WHEN n % 4 = 0 THEN 'Prospect' ELSE 'Client' END,
       'Small Demo Client ' || lpad(n::text, 2, '0'),
       (80000000 + n)::text, '+65',
       'small.demo.client.' || n || '@example.test',
       DATE '1950-01-01' + (n * 997 % 18000),
       n % 3 <> 0, n % 2 = 0, 'Manual',
       'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'::uuid
FROM generate_series(1, 20) AS n
ON CONFLICT (tenant_id, contact_id) DO NOTHING;

-- Each campaign gets 13-14 members (contacts where (n + k) % 3 <> 0).
-- engagement_status mixes 0 = contacted/no reply,
-- 1 = engaged and 2 = declined, so every campaign has unreplied members.
INSERT INTO campaign_member (
    tenant_id, campaign_id, contact_id, added_at, added_by_user_id,
    is_deleted, email_send_count, emailed_at, engagement_status
)
SELECT 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'::uuid,
       ('5a000000-0000-0000-0000-' || lpad(k::text, 12, '0'))::uuid,
       ('5c000000-0000-0000-0000-' || lpad(n::text, 12, '0'))::uuid,
       TIMESTAMPTZ '2026-09-01 09:00:00+08' + make_interval(days => (n * k) % 20),
       'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'::uuid,
       FALSE,
       CASE WHEN (n + k) % 5 = 0 THEN 0 ELSE 1 + (n % 2) END,
       CASE WHEN (n + k) % 5 = 0 THEN NULL
            ELSE TIMESTAMPTZ '2026-09-25 10:00:00+08' + make_interval(days => (n * 3 + k) % 40)
       END,
       (n * 2 + k * 3 + n / 4) % 3
FROM generate_series(1, 5) AS k
CROSS JOIN generate_series(1, 20) AS n
WHERE (n + k) % 3 <> 0
ON CONFLICT DO NOTHING;

COMMIT;
