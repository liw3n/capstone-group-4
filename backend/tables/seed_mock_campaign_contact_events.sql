-- Synthetic data only. Re-running preserves edits to existing demo rows.
-- Fixed dates make first-contact and repeat-contact examples reproducible.
BEGIN;

INSERT INTO mock_campaign_contact_event
    (tenant_id, contact_event_id, campaign_id, fa_id, contact_id, contacted_at)
VALUES
    ('pulse-demo', 'contact-event-001', 'camp-1', 'adv-steven-raynaldi', 'client-001', '2026-08-01 09:00:00+08'),
    ('pulse-demo', 'contact-event-002', 'camp-1', 'adv-steven-raynaldi', 'client-002', '2026-08-02 10:00:00+08'),
    ('pulse-demo', 'contact-event-003', 'camp-1', 'adv-steven-raynaldi', 'client-003', '2026-08-03 11:00:00+08'),
    ('pulse-demo', 'contact-event-004', 'camp-1', 'adv-steven-raynaldi', 'client-004', '2026-08-04 12:00:00+08'),
    ('pulse-demo', 'contact-event-005', 'camp-1', 'adv-steven-raynaldi', 'client-005', '2026-08-05 13:00:00+08'),
    ('pulse-demo', 'contact-event-006', 'camp-1', 'adv-steven-raynaldi', 'client-005', '2026-08-05 14:00:00+08'),
    ('pulse-demo', 'contact-event-007', 'camp-1', 'adv-steven-raynaldi', 'client-012', '2026-10-12 09:00:00+08'),
    ('pulse-demo', 'contact-event-008', 'camp-2', 'adv-steven-raynaldi', 'client-006', '2026-10-05 09:00:00+08'),
    ('pulse-demo', 'contact-event-009', 'camp-2', 'adv-steven-raynaldi', 'client-007', '2026-10-08 10:00:00+08'),
    ('pulse-demo', 'contact-event-010', 'camp-2', 'adv-steven-raynaldi', 'client-008', '2026-10-12 11:00:00+08'),
    ('pulse-demo', 'contact-event-011', 'camp-2', 'adv-steven-raynaldi', 'client-009', '2026-10-12 12:00:00+08'),
    ('pulse-demo', 'contact-event-012', 'camp-2', 'adv-steven-raynaldi', 'client-009', '2026-10-12 13:00:00+08')
ON CONFLICT DO NOTHING;

COMMIT;
