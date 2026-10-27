CREATE TABLE IF NOT EXISTS campaign (
    tenant_id uuid NOT NULL,
    campaign_id uuid NOT NULL DEFAULT gen_random_uuid(),
    campaign_code varchar(50) NOT NULL,
    name varchar(200) NOT NULL,
    description text NULL,

    campaign_type varchar(20) NULL,
    status varchar(20) NULL,
    sent_date date NULL,
    start_date date NULL,
    end_date date NULL,

    origin varchar(20) NOT NULL DEFAULT 'advisor',
    audience_source varchar(20) NOT NULL DEFAULT 'contacts',
    client_messaging text NULL,
    audience_criteria jsonb NULL,

    lead_count_uploaded integer NOT NULL DEFAULT 0,
    lead_count_promoted integer NOT NULL DEFAULT 0,
    lead_count_removed integer NOT NULL DEFAULT 0,

    email_send_runs integer NOT NULL DEFAULT 0,

    banner_image_data bytea NULL,
    banner_image_mime_type varchar(50) NULL,

    created_by_user_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),

    is_deleted boolean NOT NULL DEFAULT false,
    deleted_at timestamptz NULL,
    deleted_by_user_id uuid NULL,

    PRIMARY KEY (tenant_id, campaign_id),
    FOREIGN KEY (tenant_id, created_by_user_id) REFERENCES user_account(tenant_id, user_id),

    CHECK (origin in ('marketing','advisor')),
    CHECK (audience_source in ('contacts','leads'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_campaign_tenant_code 
    ON campaign(tenant_id, campaign_code) WHERE is_deleted = false;

CREATE INDEX IF NOT EXISTS ix_campaign_tenant_created_by
    ON campaign(tenant_id, created_by_user_id) WHERE is_deleted = false;
