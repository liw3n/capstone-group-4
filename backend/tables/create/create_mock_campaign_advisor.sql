CREATE TABLE IF NOT EXISTS mock_campaign_advisor (
    tenant_id VARCHAR(64) NOT NULL,
    campaign_id VARCHAR(69) NOT NULL,
    fa_id VARCHAR(64) NOT NULL CHECK (length(btrim(fa_id)) > 0),
    PRIMARY KEY (tenant_id, campaign_id, fa_id),
    FOREIGN KEY (tenant_id, campaign_id)
        REFERENCES mock_campaign (tenant_id, campaign_id)
);

CREATE INDEX IF NOT EXISTS idx_mock_campaign_advisor_scope
    ON mock_campaign_advisor (tenant_id, fa_id, campaign_id);

COMMENT ON TABLE mock_campaign_advisor IS 'Synthetic tenant-scoped campaign access assignments';