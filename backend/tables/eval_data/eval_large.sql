-- Synthetic PULSE evaluation dataset (large); not company GCRM records.
-- 100 campaigns, 10,000 contacts and exactly 25,000 campaign_member rows for
-- one demo adviser. Identifiers are deterministic so evaluation prompts can
-- name campaigns and compute expected results. Re-running is idempotent.
BEGIN;

INSERT INTO user_account (tenant_id, user_id)
VALUES ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11')
ON CONFLICT (tenant_id, user_id) DO NOTHING;

-- Campaigns 1-5 carry distinctive names used by the evaluation prompts. The
-- other 95 use themed names so name resolution has realistic near-matches
-- (for example "Retirement Income Wave 012" beside "Retirement Income Review").
-- Generated campaigns with k % 10 = 5 (the "Health Cover" theme) have ended,
-- so 91 campaigns are active.
INSERT INTO campaign (
    tenant_id, campaign_id, campaign_code, name, description, status,
    start_date, end_date, audience_source, client_messaging, audience_criteria,
    email_send_runs, created_by_user_id
)
SELECT 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'::uuid,
       ('1a000000-0000-0000-0000-' || lpad(k::text, 12, '0'))::uuid,
       'DEMO-L-' || lpad(k::text, 3, '0'),
       COALESCE(anchor.name,
                (ARRAY['Retirement Income', 'Education Savings', 'Wealth Accumulation',
                       'Protection Gap', 'Legacy Planning', 'Health Cover',
                       'Dividend Income', 'Young Professionals', 'Property Planning',
                       'Market Outlook'])[1 + k % 10] || ' Wave ' || lpad(k::text, 3, '0')),
       'Synthetic demo campaign ' || k || ' for tool-call evaluation.',
       CASE WHEN anchor.name IS NULL AND k % 10 = 5 THEN 'completed' ELSE 'active' END,
       CASE WHEN anchor.name IS NULL AND k % 10 = 5 THEN DATE '2026-01-01' ELSE DATE '2026-09-01' END,
       CASE WHEN anchor.name IS NULL AND k % 10 = 5 THEN DATE '2026-06-30' ELSE DATE '2027-06-30' END,
       'contacts',
       'Synthetic educational outreach message for campaign ' || k || '.',
       (ARRAY[
           '{"ageGroups": ["55to64", "65plus"], "genders": [], "cashBands": ["250kTo1m", "above1m"]}',
           '{"ageGroups": ["under35", "35to44"], "genders": [], "cashBands": []}',
           '{"ageGroups": ["45to54", "55to64"], "genders": [], "cashBands": ["50kTo250k", "250kTo1m"]}',
           '{"ageGroups": [], "genders": [], "cashBands": ["250kTo1m", "above1m"]}'
       ])[1 + k % 4]::jsonb,
       1 + k % 3,
       'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'::uuid
FROM generate_series(1, 100) AS k
LEFT JOIN (VALUES
    (1, 'Legacy Protection Refresh'),
    (2, 'Retirement Income Review'),
    (3, 'Young Families Cover Check'),
    (4, 'Education Savings Kickstart'),
    (5, 'Year-End Portfolio Health Check')
) AS anchor(n, name) ON anchor.n = k
ON CONFLICT (tenant_id, campaign_id) DO NOTHING;

INSERT INTO contact (
    tenant_id, contact_id, contact_type, full_name, mobile, mobile_country_code, email,
    date_of_birth, opt_in_email, e_statement_opt_in, data_source, created_by_user_id
)
SELECT 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'::uuid,
       ('1c000000-0000-0000-0000-' || lpad(n::text, 12, '0'))::uuid,
       CASE WHEN n % 4 = 0 THEN 'Prospect' ELSE 'Client' END,
       'Large Demo Client ' || lpad(n::text, 5, '0'),
       (80000000 + n)::text, '+65',
       'large.demo.client.' || n || '@example.test',
       DATE '1950-01-01' + (n * 397 % 18000),
       n % 3 <> 0, n % 2 = 0, 'Manual',
       'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'::uuid
FROM generate_series(1, 10000) AS n
ON CONFLICT (tenant_id, contact_id) DO NOTHING;

-- 250 distinct contacts per campaign: j * 37 is unique modulo 10,000 because
-- gcd(37, 10000) = 1, so the 25,000 (campaign, contact) pairs never collide.
-- engagement_status mixes 0 = contacted/no reply, 1 = engaged, 2 = declined.
INSERT INTO campaign_member (
    tenant_id, campaign_id, contact_id, added_at, added_by_user_id,
    is_deleted, email_send_count, emailed_at, engagement_status
)
SELECT 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'::uuid,
       ('1a000000-0000-0000-0000-' || lpad(k::text, 12, '0'))::uuid,
       ('1c000000-0000-0000-0000-' || lpad(m.n::text, 12, '0'))::uuid,
       TIMESTAMPTZ '2026-09-01 09:00:00+08' + make_interval(days => (j + k) % 30),
       'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'::uuid,
       FALSE,
       CASE WHEN (j + k) % 7 = 0 THEN 0 ELSE 1 + (j % 3) END,
       CASE WHEN (j + k) % 7 = 0 THEN NULL
            ELSE TIMESTAMPTZ '2026-09-20 10:00:00+08' + make_interval(days => (j * 3 + k) % 45)
       END,
       (j * 5 + k) % 3
FROM generate_series(1, 100) AS k
CROSS JOIN generate_series(0, 249) AS j
CROSS JOIN LATERAL (SELECT ((k - 1) * 97 + j * 37) % 10000 + 1 AS n) AS m
ON CONFLICT DO NOTHING;

COMMIT;
