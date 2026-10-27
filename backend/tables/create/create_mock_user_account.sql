-- Minimal synthetic identity keys for prototype foreign-key relationships.
-- This is not a production user-account schema.
CREATE TABLE IF NOT EXISTS user_account (
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL,
    PRIMARY KEY (tenant_id, user_id)
);

COMMENT ON TABLE user_account IS
    'Minimal synthetic identity keys for PULSE prototype foreign keys; not a production user schema.';
