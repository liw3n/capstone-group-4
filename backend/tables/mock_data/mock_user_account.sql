-- Synthetic PULSE prototype identity only; not a real user account.
INSERT INTO user_account (tenant_id, user_id)
VALUES (
    'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11',
    'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'
)
ON CONFLICT (tenant_id, user_id) DO NOTHING;
