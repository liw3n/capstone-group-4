-- PULSE prototype review state; not a production GCRM campaign table.
CREATE TABLE IF NOT EXISTS campaign_generation_drafts (
    draft_id VARCHAR(36) PRIMARY KEY
        CHECK (draft_id ~ '^[a-f0-9-]{36}$'),
    tenant_id VARCHAR(64) NOT NULL CHECK (length(btrim(tenant_id)) > 0),
    fa_id VARCHAR(64) NOT NULL CHECK (length(btrim(fa_id)) > 0),
    session_id VARCHAR(64) NOT NULL
        REFERENCES campaign_chat_sessions (session_id) ON DELETE CASCADE,
    objective TEXT NOT NULL
        CHECK (length(btrim(objective)) BETWEEN 10 AND 2000),
    references_used JSONB NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(references_used) = 'array'),
    draft JSONB NOT NULL CHECK (jsonb_typeof(draft) = 'object'),
    validation JSONB NOT NULL CHECK (jsonb_typeof(validation) = 'object'),
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
    status VARCHAR(16) NOT NULL DEFAULT 'generated'
        CHECK (status IN ('generated', 'reviewed', 'confirmed', 'rejected', 'expired')),
    changed_fields TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]
        CHECK (
            changed_fields <@ ARRAY[
                'name', 'description', 'clientMessage', 'ageGroups', 'genders',
                'cashBands', 'targetDemographicSummary'
            ]::TEXT[]
            AND array_position(changed_fields, NULL) IS NULL
        ),
    model_version VARCHAR(128),
    prompt_version VARCHAR(64) NOT NULL DEFAULT 'stage-7-v1',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, draft_id)
);

CREATE INDEX IF NOT EXISTS idx_campaign_generation_draft_scope_session
    ON campaign_generation_drafts
        (tenant_id, fa_id, session_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_campaign_generation_draft_scope_status
    ON campaign_generation_drafts (tenant_id, fa_id, status, updated_at DESC);

COMMENT ON TABLE campaign_generation_drafts IS
    'PULSE prototype review-only generated campaign drafts; not a supplied GCRM table.';
