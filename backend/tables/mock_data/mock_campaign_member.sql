-- Synthetic data only. Re-running preserves edits to existing demo rows.
-- Fixed dates make first-contact and repeat-contact examples reproducible.
BEGIN;

INSERT INTO campaign_member
    (
        tenant_id, 
        campaign_id, 
        contact_id, 
        added_at, 
        added_by_user_id, 
        is_deleted, 
        email_send_count, 
        engagement_status
    )
VALUES
    -- Campaign 1 Members
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'b1111111-1111-1111-1111-111111111111', 'd0000000-0000-0000-0000-000000000001', '2026-08-01 09:00:00+08', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', false, 2, 1),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'b1111111-1111-1111-1111-111111111111', 'd0000000-0000-0000-0000-000000000002', '2026-08-02 10:00:00+08', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', false, 1, 0),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'b1111111-1111-1111-1111-111111111111', 'd0000000-0000-0000-0000-000000000003', '2026-08-03 11:00:00+08', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', false, 1, 0),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'b1111111-1111-1111-1111-111111111111', 'd0000000-0000-0000-0000-000000000004', '2026-08-04 12:00:00+08', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', false, 1, 1),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'b1111111-1111-1111-1111-111111111111', 'd0000000-0000-0000-0000-000000000005', '2026-08-05 13:00:00+08', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', false, 2, 1),
    
    -- Campaign 2 Members
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'b2222222-2222-2222-2222-222222222222', 'd0000000-0000-0000-0000-000000000006', '2026-10-05 09:00:00+08', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', false, 1, 0),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'b2222222-2222-2222-2222-222222222222', 'd0000000-0000-0000-0000-000000000007', '2026-10-08 10:00:00+08', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', false, 1, 0),
    ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'b2222222-2222-2222-2222-222222222222', 'd0000000-0000-0000-0000-000000000008', '2026-10-12 11:00:00+08', 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', false, 1, 0)
ON CONFLICT (tenant_id, campaign_id, contact_id) WHERE is_deleted = false DO NOTHING;

COMMIT;