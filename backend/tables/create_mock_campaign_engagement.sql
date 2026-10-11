CREATE TABLE IF NOT EXISTS mock_campaign_engagement (
    campaign_id VARCHAR(64) NOT NULL,
    client_id VARCHAR(64) NOT NULL, 
    last_engagement_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    engagement_status INT NOT NULL CHECK (engagement_status IN (0, 1, 2)),
    PRIMARY KEY (campaign_id, client_id)
);

INSERT INTO mock_campaign_engagement (campaign_id, client_id, last_engagement_date, engagement_status)
VALUES
    ('camp-1', 'client-001', '2026-08-01 10:00:00', 1),
    ('camp-1', 'client-002', '2026-08-02 11:00:00', 0),
    ('camp-1', 'client-003', '2026-08-03 12:00:00', 2),
    ('camp-1', 'client-004', '2026-08-04 13:00:00', 1),
    ('camp-1', 'client-005', '2026-08-05 14:00:00', 0),
    ('camp-2', 'client-006', '2026-08-06 15:00:00', 2),
    ('camp-2', 'client-007', '2026-08-07 16:00:00', 1),
    ('camp-2', 'client-008', '2026-08-08 17:00:00', 0),
    ('camp-2', 'client-009', '2026-08-09 18:00:00', 2),
    ('camp-2', 'client-010', '2026-08-10 19:00:00', 1)
ON CONFLICT DO NOTHING;