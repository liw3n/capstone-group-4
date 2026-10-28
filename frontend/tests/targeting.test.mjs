import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { createServer } from 'vite';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

let server;
let resolveAudience;
let CriteriaSummary;
let CriteriaPicker;

before(async () => {
  server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom' });
  ({ resolveAudience } = await server.ssrLoadModule('/src/lib/targeting.ts'));
  ({ CriteriaSummary, CriteriaPicker } = await server.ssrLoadModule('/src/components/CampaignCriteria.tsx'));
});

for (const { name, criteria, labels } of [
  {
    name: 'Legacy Protection Refresh',
    criteria: { ageGroups: ['55-64', '65plus'], genders: [], cashBands: ['250k-1m', 'above1m'] },
    labels: ['55 - 64', '65 and above', 'S$250k - S$1M', 'Above S$1M'],
  },
  {
    name: 'First Home Starter Bundle',
    criteria: { ageGroups: ['under35', '35-44'], genders: ['Male', 'Female'], cashBands: ['under50k', '50k-250k'] },
    labels: ['Under 35', '35 - 44', 'Male', 'Female', 'Under S$50k', 'S$50k - S$250k'],
  },
]) {
  test(`${name} displays every stored age and cash band without changing criteria`, () => {
    const before = structuredClone(criteria);
    const html = renderToStaticMarkup(createElement(CriteriaSummary, { criteria }));
    for (const label of labels) assert.ok(html.includes(label), `Missing label: ${label}`);
    assert.ok(!/<span\b[^>]*>\s*<\/span>/.test(html), 'Criteria must not render blank badges');
    assert.deepEqual(criteria, before);
  });

  test(`${name} editor selects the stored age and cash bands`, () => {
    const html = renderToStaticMarkup(createElement(CriteriaPicker, { criteria, onChange() {} }));
    const selected = [...html.matchAll(/<button\b[^>]*aria-pressed="true"[^>]*>(.*?)<\/button>/gs)]
      .map((match) => match[1]);
    assert.deepEqual(selected, labels);
  });
}

test('canonical frontend criteria retain their existing labels and custom ranges', () => {
  const html = renderToStaticMarkup(createElement(CriteriaSummary, {
    criteria: {
      ageGroups: ['35to44'], genders: [], cashBands: ['50kTo250k'],
      cashRange: { min: 500000, max: 1000000 },
    },
  }));
  for (const label of ['35 - 44', 'S$50k - S$250k', 'S$500,000 - S$1,000,000']) {
    assert.ok(html.includes(label), `Missing label: ${label}`);
  }
});

after(async () => {
  await server?.close();
});

const campaign = {
  audienceSource: 'contacts',
  criteria: {
    ageGroups: ['55-64'],
    genders: ['Male'],
    cashBands: ['250k-1m'],
  },
  includeIds: [],
  excludeIds: [],
  leadIds: [],
};

test('resolves campaign audience using legacy stored age and cash-band values', () => {
  const contacts = [
    {
      id: 'matching',
      name: 'Matching Contact',
      email: 'matching@example.test',
      countryCode: '+65',
      phone: '',
      dob: '1968-08-26',
      gender: 'Male',
      cashAmount: 500_000,
    },
    {
      id: 'wrong-gender',
      name: 'Wrong Gender',
      email: 'wrong.gender@example.test',
      countryCode: '+65',
      phone: '',
      dob: '1968-08-26',
      gender: 'Female',
      cashAmount: 500_000,
    },
    {
      id: 'wrong-age',
      name: 'Wrong Age',
      email: 'wrong.age@example.test',
      countryCode: '+65',
      phone: '',
      dob: '1996-03-26',
      gender: 'Male',
      cashAmount: 500_000,
    },
  ];

  const result = resolveAudience(campaign, contacts);

  assert.deepEqual(result.matched.map((contact) => contact.id), ['matching']);
  assert.deepEqual(result.incomplete, []);
});

test('matches title-case contact genders against lowercase campaign genders', () => {
  const result = resolveAudience(
    {
      ...campaign,
      criteria: {
        ageGroups: [],
        genders: ['Male'],
        cashBands: [],
      },
    },
    [
      {
        id: 'male',
        name: 'Male Contact',
        email: 'male@example.test',
        countryCode: '+65',
        phone: '',
        gender: 'male',
      },
      {
        id: 'female',
        name: 'Female Contact',
        email: 'female@example.test',
        countryCode: '+65',
        phone: '',
        gender: 'Female',
      },
    ],
  );

  assert.deepEqual(result.matched.map((contact) => contact.id), ['male']);
});

test('selected age groups exclude contacts admitted only by a stale custom range', () => {
  const result = resolveAudience(
    {
      ...campaign,
      criteria: {
        ageGroups: ['under35'],
        ageRange: { min: 35, max: 44 },
        genders: [],
        cashBands: [],
      },
    },
    [
      {
        id: 'under-35',
        name: 'Under 35',
        email: 'under35@example.test',
        countryCode: '+65',
        phone: '',
        dob: '1991-08-27',
      },
      {
        id: 'age-35',
        name: 'Age 35',
        email: 'age35@example.test',
        countryCode: '+65',
        phone: '',
        dob: '1991-08-26',
      },
    ],
  );

  assert.deepEqual(result.matched.map((contact) => contact.id), ['under-35']);
  assert.deepEqual(result.incomplete, []);
});
