CREATE TABLE IF NOT EXISTS campaign_generation_clarifications (
    clarification_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    fa_id VARCHAR(64) NOT NULL,
    session_id VARCHAR(64) NOT NULL
        REFERENCES campaign_chat_sessions (session_id) ON DELETE CASCADE,
    objective TEXT NOT NULL CHECK (length(btrim(objective)) > 0),
    answers JSONB NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(answers) = 'array'),
    pending_question_ids TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]
        CHECK (
            cardinality(pending_question_ids) <= 3
            AND pending_question_ids <@
                ARRAY['focus', 'audience', 'age', 'cash']::TEXT[]
        ),
    round_count SMALLINT NOT NULL DEFAULT 0
        CHECK (round_count BETWEEN 0 AND 3),
    status VARCHAR(16) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'completed', 'cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_campaign_clarification_active_session
    ON campaign_generation_clarifications (tenant_id, fa_id, session_id)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_campaign_clarification_scope_time
    ON campaign_generation_clarifications
        (tenant_id, fa_id, session_id, created_at DESC);

COMMENT ON TABLE campaign_generation_clarifications IS
    'PULSE prototype pre-generation workflow state; not a supplied GCRM table.';
