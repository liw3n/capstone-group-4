-- Synthetic date corrections only. Update rows only while every relevant field
-- still matches the immutable baseline, preserving adviser edits and removals.
UPDATE campaign_member
SET added_at = '2026-11-03 11:00:00+08'::timestamptz
WHERE tenant_id = 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'
  AND campaign_id = 'b3333333-3333-3333-3333-333333333333'
  AND contact_id = 'd0000000-0000-0000-0000-000000000034'
  AND added_by_user_id = 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'
  AND is_deleted = FALSE
  AND email_send_count = 0
  AND emailed_at IS NULL
  AND engagement_status = 0
  AND added_at = '2026-10-19 11:00:00+08'::timestamptz;

UPDATE campaign_member
SET added_at = '2026-11-04 10:00:00+08'::timestamptz,
    emailed_at = '2026-11-05 15:00:00+08'::timestamptz
WHERE tenant_id = 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'
  AND campaign_id = 'b3333333-3333-3333-3333-333333333333'
  AND contact_id = 'd0000000-0000-0000-0000-000000000035'
  AND added_by_user_id = 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'
  AND is_deleted = FALSE
  AND email_send_count = 2
  AND emailed_at = '2026-10-27 15:00:00+08'::timestamptz
  AND engagement_status = 1
  AND added_at = '2026-10-26 10:00:00+08'::timestamptz;

UPDATE campaign_member
SET added_at = '2026-11-09 09:00:00+08'::timestamptz,
    emailed_at = '2026-11-09 10:00:00+08'::timestamptz
WHERE tenant_id = 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'
  AND campaign_id = 'b3333333-3333-3333-3333-333333333333'
  AND contact_id = 'd0000000-0000-0000-0000-000000000036'
  AND added_by_user_id = 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'
  AND is_deleted = FALSE
  AND email_send_count = 1
  AND emailed_at = '2026-10-29 13:00:00+08'::timestamptz
  AND engagement_status = 0
  AND added_at = '2026-10-28 09:00:00+08'::timestamptz;
