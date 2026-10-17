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

-- Structured alternatives are stored separately from chat prose so a later
-- instruction such as "use the fifth option" can be resolved safely.
CREATE TABLE IF NOT EXISTS campaign_generation_draft_options (
    option_set_id VARCHAR(36) PRIMARY KEY
        CHECK (option_set_id ~ '^[a-f0-9-]{36}$'),
    tenant_id VARCHAR(64) NOT NULL CHECK (length(btrim(tenant_id)) > 0),
    fa_id VARCHAR(64) NOT NULL CHECK (length(btrim(fa_id)) > 0),
    session_id VARCHAR(64) NOT NULL
        REFERENCES campaign_chat_sessions (session_id) ON DELETE CASCADE,
    draft_id VARCHAR(36) NOT NULL
        REFERENCES campaign_generation_drafts (draft_id) ON DELETE CASCADE,
    base_revision INTEGER NOT NULL CHECK (base_revision >= 1),
    field_name VARCHAR(32) NOT NULL
        CHECK (field_name IN (
            'name', 'description', 'clientMessage', 'targetDemographicSummary'
        )),
    options JSONB NOT NULL
        CHECK (jsonb_typeof(options) = 'array' AND jsonb_array_length(options) BETWEEN 2 AND 10),
    status VARCHAR(16) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'selected', 'stale', 'expired')),
    selected_index INTEGER CHECK (selected_index BETWEEN 1 AND 10),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ NOT NULL,
    UNIQUE (tenant_id, option_set_id)
);

CREATE INDEX IF NOT EXISTS idx_campaign_draft_options_pending
    ON campaign_generation_draft_options
        (tenant_id, fa_id, session_id, draft_id, status, created_at DESC);

COMMENT ON TABLE campaign_generation_draft_options IS
    'PULSE prototype revision-bound structured options; never campaign records.';

ALTER TABLE campaign_chat_sessions
    ADD COLUMN IF NOT EXISTS active_campaign_draft_id VARCHAR(36);

UPDATE campaign_chat_sessions AS sessions
SET active_campaign_draft_id = latest.draft_id
FROM (
    SELECT DISTINCT ON (session_id) session_id, draft_id
    FROM campaign_generation_drafts
    WHERE status IN ('generated', 'reviewed')
    ORDER BY session_id, updated_at DESC, created_at DESC
) AS latest
WHERE sessions.session_id = latest.session_id
  AND sessions.active_campaign_draft_id IS NULL;
