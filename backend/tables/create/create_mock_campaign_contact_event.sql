-- Synthetic PULSE prototype only; not a production GCRM interaction migration.
-- One row records one campaign outreach event for one adviser's client.
-- Campaign names remain in mock_campaign and are joined through campaign_id.
BEGIN;

-- Allows the event to reference the same tenant, contact and adviser together.
CREATE UNIQUE INDEX IF NOT EXISTS idx_mock_client_contact_advisor_key
    ON mock_client (tenant_id, contact_id, fa_id);

CREATE TABLE IF NOT EXISTS mock_campaign_contact_event (
    tenant_id VARCHAR(64) NOT NULL,
    contact_event_id VARCHAR(64) NOT NULL CHECK (length(btrim(contact_event_id)) > 0),
    campaign_id VARCHAR(69) NOT NULL,
    fa_id VARCHAR(64) NOT NULL,
    contact_id VARCHAR(64) NOT NULL,
    contacted_at TIMESTAMPTZ NOT NULL,
    engagement_status INT NOT NULL DEFAULT 0 CHECK (engagement_status IN (0, 1, 2)),
    send_batch_id VARCHAR(64),
    channel VARCHAR(16) NOT NULL DEFAULT 'manual'
        CHECK (channel IN ('manual', 'email')),
    delivery_mode VARCHAR(16) NOT NULL DEFAULT 'manual'
        CHECK (delivery_mode IN ('manual', 'mock', 'gwm')),
    PRIMARY KEY (tenant_id, contact_event_id),
    FOREIGN KEY (tenant_id, campaign_id, fa_id)
        REFERENCES mock_campaign_advisor (tenant_id, campaign_id, fa_id),
    FOREIGN KEY (tenant_id, contact_id, fa_id)
        REFERENCES mock_client (tenant_id, contact_id, fa_id),
    UNIQUE (tenant_id, send_batch_id, contact_id)
);

CREATE INDEX IF NOT EXISTS idx_mock_campaign_contact_event_scope
    ON mock_campaign_contact_event
        (tenant_id, fa_id, campaign_id, contact_id, contacted_at);

COMMENT ON TABLE mock_campaign_contact_event IS
    'Synthetic adviser-scoped campaign outreach history; not the company GCRM interaction table';
COMMIT;
