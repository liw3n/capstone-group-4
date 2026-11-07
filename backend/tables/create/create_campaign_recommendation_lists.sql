-- Project-owned synthetic result snapshots; not part of the supplied CRM schema.
CREATE TABLE IF NOT EXISTS campaign_recommendation_lists (
    list_id uuid PRIMARY KEY,
    tenant_id text NOT NULL,
    fa_id text NOT NULL,
    session_id text,
    campaign_id text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object')
);
CREATE INDEX IF NOT EXISTS ix_recommendation_list_scope_expiry
    ON campaign_recommendation_lists (tenant_id, fa_id, expires_at);
