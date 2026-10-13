
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