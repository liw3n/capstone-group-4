import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

let server;
let CampaignDraftReview;
let campaignDraftChanges;

const artifact = {
  type: 'campaign_draft',
  data_source: 'ai_generated',
  draftId: '11111111-1111-4111-8111-111111111111',
  objective: 'Invite clients nearing retirement to review their financial plans.',
  referencesUsed: [{ referenceId: 'campaign-pattern-retirement-001', version: 1 }],
  draft: {
    name: 'Retirement Readiness Review',
    description: 'An educational review for clients nearing retirement.',
    clientMessage: 'Review your plans with an adviser. This is not financial advice.',
    criteria: {
      ageGroups: ['55to64', '65plus'],
      genders: [],
      cashBands: ['250kTo1m', 'above1m'],
    },
    targetDemographicSummary: 'Clients aged 55 and above across all genders.',
    rationale: {
      ageGroups: 'The objective concerns clients nearing retirement.',
      genders: 'The objective has no gender restriction.',
      cashBands: 'These bands support an asset review hypothesis.',
    },
    assumptions: ['Retirement timing must be confirmed.'],
    disclaimer: 'Educational information only; individual suitability requires adviser review.',
  },
  revision: 2,
  status: 'reviewed',
  changedFields: ['name'],
  validation: {
    schema_valid: true,
    policy_valid: true,
    warnings: ['Confirm the retirement timing with the client.'],
  },
  requires_adviser_review: true,
  created: false,
};

before(async () => {
  server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom' });
  const module = await server.ssrLoadModule('/src/components/CampaignDraftReview.tsx');
  CampaignDraftReview = module.default;
  campaignDraftChanges = module.campaignDraftChanges;
});

after(async () => { await server?.close(); });

test('generated review uses the campaign screen without exposing campaign creation', () => {
  const html = renderToStaticMarkup(createElement(CampaignDraftReview, {
    advisorId: 'adv-demo',
    sessionId: 'session-1',
    initialDraft: artifact,
    onCancel() {},
    onDraftUpdated() {},
  }));

  assert.ok(html.includes('Review generated campaign'));
  assert.ok(html.includes('Retirement Readiness Review'));
  assert.ok(html.includes('Targeting criteria'));
  assert.ok(html.includes('Retirement timing must be confirmed'));
  assert.ok(html.includes('campaign-pattern-retirement-001'));
  assert.ok(html.includes('Save draft'));
  assert.ok(html.includes('Preview draft'));
  assert.ok(html.includes('fixed age and cash bands only'));
  assert.ok(!html.includes('Minimum age'));
  assert.ok(!html.includes('Create campaign'));
  assert.ok(!html.includes('Estimated audience'));
});

test('manual review sends only fields changed from the authoritative revision', () => {
  const form = {
    name: 'Retirement Confidence Review',
    description: artifact.draft.description,
    clientMessage: artifact.draft.clientMessage,
    criteria: {
      ageGroups: artifact.draft.criteria.ageGroups,
      genders: ['female'],
      cashBands: artifact.draft.criteria.cashBands,
    },
    targetDemographicSummary: artifact.draft.targetDemographicSummary,
  };

  assert.deepEqual(campaignDraftChanges(artifact, form), {
    name: 'Retirement Confidence Review',
    genders: ['female'],
  });
});
