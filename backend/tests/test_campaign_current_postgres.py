"""Opt-in current-schema checks in an isolated schema, never public demo tables."""
from datetime import date, datetime, timedelta, timezone
import os
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest

from app import config
from app.campaigns import catalog, draft_repository, repository
from app.campaigns.models import (
    CampaignDraftArtifact,
    CampaignDraftCreationMetadata,
    CampaignDraftRevisionArtifact,
)
from app.campaigns.preview import (
    campaign_preview_content_hash,
    campaign_preview_token_digest,
    get_campaign_preview_signer,
    revalidate_campaign_draft_preview,
)
from app.campaigns.matching import recommend_clients_for_campaign
from app.campaigns.repository import CampaignInactive, RequestScope
from app.contacts.catalog import list_contacts
from app.tools.campaign_lookup import execute_resolve_campaign

TABLES = Path(__file__).parents[1] / 'tables'
ADVISER = 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'
FIRST_HOME = 'b2222222-2222-2222-2222-222222222222'
LEGACY = 'b1111111-1111-1111-1111-111111111111'


@pytest.fixture
def current_database(monkeypatch):
    url = os.environ.get('PULSE_CURRENT_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Set PULSE_CURRENT_TEST_DATABASE_URL for isolated current-schema checks')
    schema = 'pulse_current_test_' + uuid4().hex
    settings = config.get_settings()
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        scoped_url = make_conninfo(url, options=f'-c search_path={schema},public')
        try:
            with psycopg.connect(scoped_url, autocommit=True) as connection:
                for name in ('create_mock_user_account.sql', 'create_campaign.sql', 'create_contact.sql'):
                    connection.execute((TABLES / 'create' / name).read_text())
                connection.execute(
                    (TABLES / 'create' / 'create_campaign_chat_sessions.sql').read_text()
                )
                draft_ddl = (
                    TABLES / 'create' / 'create_campaign_generation_drafts.sql'
                ).read_text()
                connection.execute(draft_ddl)
                connection.execute(draft_ddl)
                for name in ('mock_user_account.sql', 'mock_contact.sql', 'mock_campaign.sql'):
                    connection.execute((TABLES / 'mock_data' / name).read_text())
                monkeypatch.setattr(config, 'get_settings', lambda: settings.model_copy(
                    update={'database_url': scoped_url}))
                yield connection
        finally:
            admin.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


def test_discovery_and_matching_use_current_rows_and_crm_enrichment(current_database):
    scope = RequestScope(ADVISER)
    campaigns = repository.list_active_campaigns(scope, date(2026, 10, 28))
    assert len(campaigns) == 3
    assert {row.campaign_id for row in repository.list_active_campaigns(
        scope, date(2026, 10, 28), campaign_names=['FIRST HOME STARTER BUNDLE'])} == {FIRST_HOME}
    result = recommend_clients_for_campaign(FIRST_HOME, scope)
    assert result['evaluated_count'] == 12
    assert result['matched_count'] == 3 and result['incomplete_count'] == 1
    assert [client['name'] for client in result['clients']] == [
        'Demo Client F', 'Demo Client G', 'Demo Client H']
    crm_ids = {str(contact['id']) for contact in list_contacts(scope)}
    assert all(client['contact_id'] in crm_ids for client in result['clients'])
    # Current portfolio mock values are below the legacy campaign's cash floor.
    assert recommend_clients_for_campaign(LEGACY, scope)['matched_count'] == 0
    assert repository.get_campaign_by_name('first home starter bundle', scope).campaign_id == FIRST_HOME
    resolved = execute_resolve_campaign({'campaign_name': 'first home starter bundle campaign'},
                                       {'pulse_scope': {'fa_id': ADVISER, 'tenant_id': 'pulse-demo'}})
    assert resolved['status'] == 'matched' and resolved['campaign_id'] == FIRST_HOME
    assert 'table' not in resolved and 'criteria' not in resolved


def test_live_criteria_status_and_soft_delete_are_observed(current_database):
    scope = RequestScope(ADVISER)
    current_database.execute("""UPDATE campaign SET audience_criteria =
        '{"ageGroups":["under35","35-44"],"genders":["Female"],"cashBands":["under50k","50k-250k"]}'::jsonb
        WHERE campaign_id = %s""", (FIRST_HOME,))
    result = recommend_clients_for_campaign(FIRST_HOME, scope)
    assert [client['name'] for client in result['clients']] == ['Demo Client F', 'Demo Client H']
    current_database.execute('UPDATE campaign SET status = %s WHERE campaign_id = %s', ('paused', FIRST_HOME))
    with pytest.raises(CampaignInactive):
        recommend_clients_for_campaign(FIRST_HOME, scope)
    assert repository.list_active_campaigns(scope, date(2026, 10, 28), [FIRST_HOME]) == ()
    current_database.execute('UPDATE campaign SET is_deleted = TRUE WHERE campaign_id = %s', (FIRST_HOME,))
    with pytest.raises(repository.CampaignUnavailable):
        repository.get_campaign(FIRST_HOME, scope)


def test_other_adviser_assignment_and_explicit_tenant_are_excluded(current_database):
    scope = RequestScope(ADVISER)
    other = str(uuid4())
    current_database.execute('UPDATE contact SET assigned_to_user_id = %s WHERE full_name = %s',
                             (other, 'Demo Client G'))
    assert recommend_clients_for_campaign(FIRST_HOME, scope)['matched_count'] == 2
    current_database.execute('UPDATE contact SET is_deleted = TRUE WHERE full_name = %s', ('Demo Client F',))
    assert recommend_clients_for_campaign(FIRST_HOME, scope)['matched_count'] == 1
    assert repository.list_active_campaigns(RequestScope(other), date(2026, 10, 28)) == ()
    assert repository.list_active_campaigns(RequestScope(ADVISER, other), date(2026, 10, 28)) == ()
    assert repository.list_clients_for_fa(RequestScope(ADVISER, other)) == ()
    resolved = execute_resolve_campaign({'campaign_name': 'First Home Starter Bundle'},
                                       {'pulse_scope': {'fa_id': ADVISER, 'tenant_id': other}})
    assert resolved['status'] == 'not_found' and 'campaign_id' not in resolved


def test_contact_and_campaign_catalogues_isolate_advisers_in_one_tenant(current_database):
    other_adviser = str(uuid4())
    other_contact = str(uuid4())
    other_campaign = str(uuid4())
    current_database.execute(
        'INSERT INTO user_account (tenant_id, user_id) VALUES (%s, %s)',
        (ADVISER, other_adviser),
    )
    current_database.execute(
        """INSERT INTO contact
           (tenant_id, contact_id, contact_type, full_name, mobile, created_by_user_id)
           VALUES (%s, %s, 'Client', 'Other adviser synthetic client', '90000000', %s)""",
        (ADVISER, other_contact, other_adviser),
    )
    current_database.execute(
        """INSERT INTO campaign
           (tenant_id, campaign_id, campaign_code, name, start_date, end_date,
            created_by_user_id)
           VALUES (%s, %s, %s, 'Other adviser synthetic campaign',
                   '2026-10-01', '2026-12-31', %s)""",
        (ADVISER, other_campaign, f'OTHER-{uuid4().hex[:12]}', other_adviser),
    )

    owner_scope = RequestScope(ADVISER, ADVISER)
    other_scope = RequestScope(other_adviser, ADVISER)
    assert other_contact not in {str(row['id']) for row in list_contacts(owner_scope)}
    assert other_contact in {str(row['id']) for row in list_contacts(other_scope)}
    assert other_campaign not in {row['id'] for row in catalog.list_campaigns('advisor', owner_scope)}
    assert catalog.get_campaign_record('advisor', owner_scope, other_campaign) is None
    assert catalog.get_campaign_record('advisor', other_scope, other_campaign)['id'] == other_campaign


def test_preview_metadata_is_scoped_and_invalidated_by_revision(current_database):
    from test_orchestrator import campaign_draft_artifact

    session_id = 'stage-nine-session'
    current_database.execute(
        'INSERT INTO campaign_chat_sessions (fa_id, session_id) VALUES (%s, %s)',
        (ADVISER, session_id),
    )
    scope = RequestScope(ADVISER)
    artifact = CampaignDraftArtifact.model_validate(campaign_draft_artifact())
    persisted = draft_repository.create_campaign_draft(scope, session_id, artifact)
    now = datetime(2026, 10, 31, 8, 0, tzinfo=timezone.utc)
    metadata = draft_repository.store_campaign_draft_preview(
        scope,
        session_id,
        persisted.draftId,
        persisted.revision,
        content_hash='a' * 64,
        token_digest='b' * 64,
        created_at=now,
        expires_at=now + timedelta(minutes=5),
    )
    assert metadata.content_hash == 'a' * 64
    assert draft_repository.get_campaign_draft_preview_metadata(
        RequestScope('other-adviser'), session_id, persisted.draftId
    ) is None

    next_draft = persisted.draft.model_copy(update={'name': 'Revised preview name'})
    revision = CampaignDraftRevisionArtifact(
        objective=persisted.objective,
        referencesUsed=persisted.referencesUsed,
        draft=next_draft,
        previousRevision=1,
        revision=2,
        changedFields=['name'],
        validation=persisted.validation,
    )
    draft_repository.update_campaign_draft_revision(
        scope, session_id, persisted.draftId, 1, revision, status='reviewed'
    )
    assert draft_repository.get_campaign_draft_preview_metadata(
        scope, session_id, persisted.draftId
    ) is None


def _prepared_confirmation(current_database, session_id):
    from test_orchestrator import campaign_draft_artifact

    current_database.execute(
        'INSERT INTO campaign_chat_sessions (fa_id, session_id) VALUES (%s, %s)',
        (ADVISER, session_id),
    )
    scope = RequestScope(ADVISER)
    artifact = CampaignDraftArtifact.model_validate(campaign_draft_artifact())
    persisted = draft_repository.create_campaign_draft(scope, session_id, artifact)
    persisted = draft_repository.update_campaign_draft_creation_metadata(
        scope,
        session_id,
        persisted.draftId,
        persisted.revision,
        CampaignDraftCreationMetadata(
            startDate=date(2026, 11, 10),
            endDate=date(2027, 1, 31),
        ),
    )
    validation = revalidate_campaign_draft_preview(persisted, scope)
    content_hash = campaign_preview_content_hash(
        persisted.draft,
        validation,
        persisted.creation,
    )
    now = datetime.now(timezone.utc)
    token, claims = get_campaign_preview_signer().issue(
        draft_id=persisted.draftId,
        revision=persisted.revision,
        content_hash=content_hash,
        scope=scope,
        session_id=session_id,
        now=now,
    )
    draft_repository.store_campaign_draft_preview(
        scope,
        session_id,
        persisted.draftId,
        persisted.revision,
        content_hash=content_hash,
        token_digest=campaign_preview_token_digest(token),
        created_at=now,
        expires_at=datetime.fromtimestamp(claims.expires_at, tz=timezone.utc),
    )
    return scope, persisted, token, now


def test_confirmation_atomically_creates_one_official_draft_campaign(current_database):
    session_id = 'stage-ten-session'
    scope, persisted, token, now = _prepared_confirmation(
        current_database, session_id
    )

    first = draft_repository.confirm_campaign_draft(
        scope,
        session_id,
        persisted.draftId,
        persisted.revision,
        token,
        'stage-ten-idempotency-key',
        now=now + timedelta(seconds=1),
    )
    retry = draft_repository.confirm_campaign_draft(
        scope,
        session_id,
        persisted.draftId,
        persisted.revision,
        token,
        'stage-ten-idempotency-key',
        now=now + timedelta(seconds=2),
    )

    assert first.created is True
    assert retry.created is False
    assert retry.campaign_id == first.campaign_id
    campaign = current_database.execute(
        """SELECT status, origin, audience_source, created_by_user_id,
                  start_date, end_date, audience_criteria
           FROM campaign WHERE tenant_id = %s AND campaign_id = %s""",
        (ADVISER, first.campaign_id),
    ).fetchone()
    assert campaign['status'] == 'draft'
    assert campaign['origin'] == 'advisor'
    assert campaign['audience_source'] == 'contacts'
    assert str(campaign['created_by_user_id']) == ADVISER
    assert campaign['start_date'] == date(2026, 11, 10)
    assert campaign['end_date'] == date(2027, 1, 31)
    assert campaign['audience_criteria'] == {
        'ageGroups': ['55-64'],
        'genders': [],
        'cashBands': ['50k-250k', '250k-1m'],
    }
    draft = current_database.execute(
        """SELECT status, created_campaign_id, confirmed_revision,
                  confirmation_idempotency_key
           FROM campaign_generation_drafts WHERE draft_id = %s""",
        (persisted.draftId,),
    ).fetchone()
    assert draft['status'] == 'confirmed'
    assert str(draft['created_campaign_id']) == first.campaign_id
    assert draft['confirmed_revision'] == persisted.revision
    assert draft['confirmation_idempotency_key'] == 'stage-ten-idempotency-key'
    session = current_database.execute(
        'SELECT active_campaign_draft_id FROM campaign_chat_sessions WHERE session_id = %s',
        (session_id,),
    ).fetchone()
    assert session['active_campaign_draft_id'] is None
    assert current_database.execute(
        'SELECT count(*) AS count FROM campaign WHERE campaign_id = %s',
        (first.campaign_id,),
    ).fetchone()['count'] == 1


def test_confirmation_rolls_back_campaign_when_draft_confirmation_fails(current_database):
    session_id = 'stage-ten-rollback-session'
    scope, persisted, token, now = _prepared_confirmation(
        current_database, session_id
    )
    campaigns_before = current_database.execute(
        'SELECT count(*) AS count FROM campaign'
    ).fetchone()['count']
    current_database.execute(
        """
        CREATE FUNCTION reject_stage_ten_confirmation() RETURNS trigger AS $$
        BEGIN
            IF NEW.status = 'confirmed' THEN
                RAISE EXCEPTION 'forced confirmation failure';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER reject_stage_ten_confirmation
        BEFORE UPDATE ON campaign_generation_drafts
        FOR EACH ROW EXECUTE FUNCTION reject_stage_ten_confirmation();
        """
    )

    with pytest.raises(draft_repository.CampaignDraftStorageUnavailable):
        draft_repository.confirm_campaign_draft(
            scope,
            session_id,
            persisted.draftId,
            persisted.revision,
            token,
            'stage-ten-rollback-key',
            now=now + timedelta(seconds=1),
        )

    assert current_database.execute(
        'SELECT count(*) AS count FROM campaign'
    ).fetchone()['count'] == campaigns_before
    draft = current_database.execute(
        """SELECT status, created_campaign_id, confirmation_idempotency_key
           FROM campaign_generation_drafts WHERE draft_id = %s""",
        (persisted.draftId,),
    ).fetchone()
    assert draft == {
        'status': 'reviewed',
        'created_campaign_id': None,
        'confirmation_idempotency_key': None,
    }
    session = current_database.execute(
        'SELECT active_campaign_draft_id FROM campaign_chat_sessions WHERE session_id = %s',
        (session_id,),
    ).fetchone()
    assert session['active_campaign_draft_id'] == persisted.draftId
