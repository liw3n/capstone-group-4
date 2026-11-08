-- Synthetic PULSE email preview and delivery audit; not a production GCRM table.
CREATE TABLE IF NOT EXISTS campaign_email_send (
    tenant_id UUID NOT NULL,
    send_batch_id UUID NOT NULL DEFAULT gen_random_uuid(),
    campaign_id UUID NOT NULL,
    fa_id UUID NOT NULL,
    session_id VARCHAR(64) NOT NULL,
    subject VARCHAR(200) NOT NULL CHECK (length(btrim(subject)) > 0),
    message_body TEXT NOT NULL CHECK (length(btrim(message_body)) > 0),
    signoff_name VARCHAR(100) NOT NULL CHECK (length(btrim(signoff_name)) > 0),
    body_template TEXT NOT NULL CHECK (length(btrim(body_template)) > 0),
    recipient_ids UUID[] NOT NULL CHECK (cardinality(recipient_ids) BETWEEN 1 AND 100),
    recipient_snapshot JSONB NOT NULL,
    confirmation_hash VARCHAR(64) NOT NULL CHECK (confirmation_hash ~ '^[a-f0-9]{64}$'),
    status VARCHAR(24) NOT NULL DEFAULT 'prepared'
        CHECK (status IN ('prepared', 'superseded', 'sending', 'sent', 'partial', 'failed', 'invalidated')),
    provider_results JSONB NOT NULL DEFAULT '[]'::jsonb,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, send_batch_id),
    FOREIGN KEY (tenant_id, campaign_id)
        REFERENCES campaign (tenant_id, campaign_id),
    FOREIGN KEY (tenant_id, fa_id)
        REFERENCES user_account (tenant_id, user_id),
    FOREIGN KEY (session_id)
        REFERENCES campaign_chat_sessions (session_id) ON DELETE CASCADE,
    CHECK (jsonb_typeof(recipient_snapshot) = 'array'),
    CHECK (jsonb_typeof(provider_results) = 'array')
);

CREATE INDEX IF NOT EXISTS idx_campaign_email_send_active
    ON campaign_email_send (tenant_id, fa_id, session_id, campaign_id, created_at DESC);

COMMENT ON TABLE campaign_email_send IS
    'PULSE adviser-approved email batches and provider outcomes; mock delivery by default';
