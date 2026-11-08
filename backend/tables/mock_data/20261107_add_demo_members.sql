-- Synthetic additions only. Skip absent/deleted parents and any prior membership,
-- including soft-deleted membership, so an adviser's removal is not undone.
INSERT INTO campaign_member (
    tenant_id, campaign_id, contact_id, added_at, added_by_user_id,
    is_deleted, email_send_count, emailed_at, engagement_status
)
SELECT c.tenant_id, c.campaign_id, p.contact_id, v.added_at, u.user_id,
       FALSE, 1, v.emailed_at, 0
FROM (VALUES
    ('d0000000-0000-0000-0000-000000000030'::uuid,
     '2026-10-30 09:00:00+08'::timestamptz, '2026-10-30 14:00:00+08'::timestamptz),
    ('d0000000-0000-0000-0000-000000000033'::uuid,
     '2026-10-31 10:00:00+08'::timestamptz, '2026-11-01 11:00:00+08'::timestamptz)
) AS v(contact_id, added_at, emailed_at)
JOIN contact p ON p.contact_id = v.contact_id
    AND p.tenant_id = 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11' AND NOT p.is_deleted
JOIN campaign c ON c.tenant_id = p.tenant_id
    AND c.campaign_id = 'b2222222-2222-2222-2222-222222222222' AND NOT c.is_deleted
JOIN user_account u ON u.tenant_id = p.tenant_id
    AND u.user_id = 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'
WHERE NOT EXISTS (
    SELECT 1 FROM campaign_member m WHERE m.tenant_id = c.tenant_id
      AND m.campaign_id = c.campaign_id AND m.contact_id = p.contact_id
)
ON CONFLICT DO NOTHING;
