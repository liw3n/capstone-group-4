CREATE TABLE IF NOT EXISTS campaign_member (
    tenant_id uuid NOT NULL,
    campaign_member_id uuid NOT NULL DEFAULT gen_random_uuid(),

    campaign_id uuid NOT NULL,
    contact_id uuid NOT NULL,

    member_role varchar(50) NULL,

    added_at timestamptz NOT NULL DEFAULT now(),
    added_by_user_id uuid NOT NULL,

    is_deleted boolean NOT NULL DEFAULT false,
    deleted_at timestamptz NULL,
    deleted_by_user_id uuid NULL,

    added_to_pipeline_at timestamptz NULL,
    task_created_at timestamptz NULL,

    emailed_at timestamptz NULL,
    email_send_count integer NOT NULL DEFAULT 0,
    engagement_status INT NOT NULL DEFAULT 0 CHECK (engagement_status IN (0, 1, 2)),

    CONSTRAINT pk_campaign_member PRIMARY KEY (tenant_id, campaign_member_id),
    CONSTRAINT fk_campaign_member_campaign FOREIGN KEY (tenant_id, campaign_id)
    REFERENCES campaign(tenant_id, campaign_id),
    CONSTRAINT fk_campaign_member_contact FOREIGN KEY (tenant_id, contact_id)
    REFERENCES contact(tenant_id, contact_id),
    CONSTRAINT fk_campaign_member_added_by FOREIGN KEY (tenant_id, added_by_user_id)
    REFERENCES user_account(tenant_id, user_id)
);

CREATE UNIQUE INDEX ux_campaign_member_tenant_campaign_contact
    ON campaign_member(tenant_id, campaign_id, contact_id) WHERE is_deleted = false;
