-- Synthetic PULSE prototype data only; not company GCRM records.
BEGIN;

INSERT INTO campaign (
    tenant_id,
    campaign_id,
    campaign_code,
    name,
    description,
    start_date,
    end_date,
    audience_source,
    client_messaging,
    audience_criteria,
    lead_count_uploaded,
    lead_count_promoted,
    lead_count_removed,
    email_send_runs,
    created_by_user_id
)
VALUES
    (
        'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
        'b1111111-1111-1111-1111-111111111111',
        'CMP-2026-001',
        'Legacy Protection Refresh',
        'Q4 push on estate and legacy planning for our established client base. Priority is on clients approaching or past retirement.',
        '2026-08-01',
        '2026-12-31',
        'contacts',
        'Your protection plan was built for a different stage of life. We are offering complimentary legacy planning reviews this quarter.',
        '{"ageGroups": ["55-64", "65plus"], "genders": [], "cashBands": ["250k-1m", "above1m"]}'::jsonb,
        150,
        120,
        30,
        2,
        'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'
    ),
    (
        'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
        'b2222222-2222-2222-2222-222222222222',
        'CMP-2026-002',
        'First Home Starter Bundle',
        'Acquisition campaign aimed at younger clients and prospects entering the property market.',
        '2026-08-01',
        '2026-12-31',
        'contacts',
        'Buying your first home is the point most people are most exposed — a mortgage, and nothing standing behind it.',
        '{"ageGroups": ["under35", "35-44"], "genders": ["Male", "Female"], "cashBands": ["under50k", "50k-250k"]}'::jsonb,
        300,
        250,
        50,
        4,
        'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'
    ),
    (
        'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
        'b3333333-3333-3333-3333-333333333333',
        'CMP-2026-003',
        'Custom High-Net-Worth Advisory Outreach',
        'Targeted outreach by advisors focusing on custom age and cash brackets for wealth management.',
        '2026-09-01',
        '2026-11-30',
        'contacts',
        'We would like to invite you for an exclusive portfolio consultation session.',
        '{"ageCustomMin": 40, "ageCustomMax": 55, "genders": ["Male", "Female"], "cashCustomMin": 500000, "cashCustomMax": 2000000}'::jsonb,
        75,
        60,
        15,
        1,
        'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'
    )
ON CONFLICT (tenant_id, campaign_id) DO NOTHING;

COMMIT;
