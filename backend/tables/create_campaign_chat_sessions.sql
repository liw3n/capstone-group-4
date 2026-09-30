CREATE TABLE IF NOT EXISTS campaign_chat_sessions (
    fa_id VARCHAR(64) NOT NULL,
    session_id VARCHAR(64) NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    session_title VARCHAR(255) DEFAULT NULL,
    PRIMARY KEY (session_id)
);

CREATE INDEX IF NOT EXISTS idx_fa_id ON campaign_chat_sessions (fa_id);