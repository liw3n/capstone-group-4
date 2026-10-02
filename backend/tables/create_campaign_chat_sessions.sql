CREATE TABLE IF NOT EXISTS campaign_chat_sessions (
    fa_id VARCHAR(64) NOT NULL,
    session_id VARCHAR(64) NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    session_title VARCHAR(255) DEFAULT NULL,
    PRIMARY KEY (session_id)
);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'campaign_chat_sessions'
          AND column_name = 'timestamp'
          AND data_type = 'timestamp without time zone'
    ) THEN
        ALTER TABLE campaign_chat_sessions
            ALTER COLUMN timestamp TYPE TIMESTAMPTZ
            USING timestamp AT TIME ZONE 'UTC';
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_fa_id ON campaign_chat_sessions (fa_id);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_fa_time
    ON campaign_chat_sessions (fa_id, timestamp DESC);

CREATE TABLE IF NOT EXISTS campaign_chat_messages (
    message_id BIGSERIAL PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL REFERENCES campaign_chat_sessions (session_id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    role VARCHAR(16) NOT NULL CHECK (role IN ('user', 'assistant')),
    user_id VARCHAR(64) DEFAULT NULL,
    message_content TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session_time
    ON campaign_chat_messages (session_id, timestamp, message_id);
