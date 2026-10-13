INSERT INTO mock_campaign_advisor (tenant_id, campaign_id, fa_id)
VALUES
    ('pulse-demo', 'camp-1', 'adv-steven-raynaldi'),
    ('pulse-demo', 'camp-2', 'adv-steven-raynaldi')
ON CONFLICT DO NOTHING;