import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { createServer } from 'vite';

let server;
let resolveAudience;

before(async () => {
  server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom' });
  ({ resolveAudience } = await server.ssrLoadModule('/src/lib/targeting.ts'));
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
