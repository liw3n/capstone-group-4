import {
  Campaign,
  Contact,
  ContactLabel,
  Gender,
  PipelineItem,
  Policy,
  Task,
  TaskType,
} from '../types';

/**
 * The prototype is anchored to a fixed "today" so that relative copy such as
 * "345 days overdue" stays stable instead of drifting every time it is opened.
 */
export const TODAY_ISO = '2026-08-26';
const TODAY = new Date(`${TODAY_ISO}T00:00:00`);

/**
 * Format as YYYY-MM-DD in local time. Using toISOString() here would shift the
 * date back a day for anyone east of UTC, since the Date is local midnight.
 */
export function toISODate(d: Date): string {
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${month}-${day}`;
}

function shiftDays(days: number): string {
  const d = new Date(TODAY);
  d.setDate(d.getDate() + days);
  return toISODate(d);
}

/** Deterministic PRNG so the generated book of business is identical on every load. */
function mulberry32(seed: number) {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const rand = mulberry32(20260826);

function pick<T>(arr: T[]): T {
  return arr[Math.floor(rand() * arr.length)];
}

const FIRST_NAMES = [
  'Wei Ling', 'Rajesh', 'Priya', 'Daniel', 'Amanda', 'Hakim', 'Nurul', 'Jun Wei',
  'Michelle', 'Arun', 'Farah', 'Benjamin', 'Clarissa', 'Zhi Hao', 'Aisha', 'Marcus',
  'Grace', 'Ridwan', 'Melissa', 'Boon Keat', 'Yi Xuan', 'Ibrahim', 'Rachel', 'Kai Xin',
  'Suriya', 'Jonathan', 'Serene', 'Haziq', 'Deepa', 'Andrew', 'Shu Fen', 'Faizal',
  'Natalie', 'Vikram', 'Joanne', 'Terence', 'Nadia', 'Chee Meng', 'Lakshmi', 'Gerald',
];

const LAST_NAMES = [
  'Rahman', 'Chong', 'Yusuf', 'O’Connor', 'Chen', 'Tan', 'Lim', 'Kumar', 'Wong', 'Ng',
  'Ibrahim', 'Goh', 'Sharma', 'Lee', 'Teo', 'Nair', 'Koh', 'Hassan', 'Pillai', 'Low',
  'Ong', 'Devi', 'Yeo', 'Aziz', 'Toh',
];

const EMAIL_DOMAINS = [
  'placeholder.local', 'yahoo.com.sg', 'personalmail.com', 'domain-example.org', 'gmail.com',
];

const LABELS: (ContactLabel | undefined)[] = [
  'Prospect', 'Prospect', 'Prospect', 'Client', 'Client', 'Client', undefined,
];

const OCCUPATIONS = [
  'Senior Software Engineer', 'Regional Sales Director', 'General Practitioner',
  'Civil Engineer', 'Marketing Manager', 'Operations Lead', 'Financial Controller',
  'University Lecturer', 'Architect', 'Business Owner',
];

const COMPANIES = [
  'Global Tech Solutions', 'Marina Bay Holdings', 'Sentosa Logistics', 'Orchard Health Group',
  'Raffles Consulting', 'Keppel Industrial', 'Jurong Manufacturing', 'Tanjong Media',
];

const INCOMES = ['$85,000', '$120,000', '$185,000', '$240,000', '$310,000', '$450,000'];

const STREETS = [
  '12 Marina Boulevard', '88 Orchard Road', '5 Tanjong Pagar Road', '210 Bukit Timah Road',
  '47 Serangoon Gardens Way', '9 Raffles Place', '133 New Bridge Road',
];

/** Policy holdings exist so a contact record can answer "what do they already hold". */
const PROVIDERS = [
  'Prudential', 'Prudential', 'Prudential', 'AIA', 'Great Eastern', 'Manulife', 'NTUC Income',
];

const POLICY_TYPES = ['Life', 'Life', 'Critical Illness', 'Endowment', 'Hospitalisation'];

/** Advisors who left; their books were reassigned. */
const PREVIOUS_ADVISORS = ['Marcus Tan', 'Evelyn Koh', 'Darren Sim'];

/** Contacts 1-6 mirror the production contact list exactly. */
const ANCHOR_CONTACTS: Contact[] = [
  {
    id: '1',
    name: 'Steven',
    email: 'stevn@phillip.com.sgs',
    countryCode: '+65',
    phone: '92988104',
    label: 'Prospect',
    bookmarked: true,
    meetings: [
      {
        id: 'm-steven-1',
        date: '2026-06-19',
        title: 'Conducted Initial Discovery And Identified Critical Illness Gap',
        description:
          'The financial advisor met with the client to establish their current financial health and identify protection gaps. A significant gap in Critical Illness coverage was identified, as the client only has basic hospitalisation insurance without lump-sum payout protection for non-medical costs during recovery. The advisor proposed evaluating a tiered CI plan covering Early, Intermediate, and Advanced stages with sum assured equivalent to 3-5 times annual income.',
        tasks: ['CI Quote Generation', 'Policy Audit Review', 'Budget Finalization'],
      },
    ],
    profile: { eStatement: false, accreditedInvestor: false, mailingAddress: true },
  },
  {
    id: '2',
    name: 'Joseph Rahman',
    email: 'joseph.rahman@placeholder.local',
    countryCode: '+65',
    phone: '80498629',
    bookmarked: true,
  },
  {
    id: '3',
    name: 'Sarah Chong',
    email: 'sarahchong.@yahoo.com.sg',
    countryCode: '+65',
    phone: '',
    label: 'Prospect',
  },
  {
    id: '4',
    name: 'Siti Adilah Yusuf',
    email: 'siti.adilah@personalmail.com',
    countryCode: '+65',
    phone: '',
    label: 'Prospect',
  },
  {
    id: '5',
    name: 'Kayden O’Connor',
    email: 'kayden.oconnor@placeholder.local',
    countryCode: '+65',
    phone: '83332211',
    label: 'Client',
    bookmarked: true,
  },
  {
    id: '6',
    name: 'Mathew Chen',
    email: 'mathew.chen@domain-example.org',
    countryCode: '+65',
    phone: '',
    label: 'Prospect',
  },
];

/** Referenced by the seeded task list, so they must exist in the registry. */
const TASK_CONTACT_NAMES = [
  'Jason Rahman',
  'Siti Amina Yusuf',
  'Siti Chong',
  'Kevin O’Connor',
  'Minghao Chen',
];

function emailFor(name: string, domain: string): string {
  const local = name
    .toLowerCase()
    .replace(/’/g, '')
    .replace(/\s+/g, '.');
  return `${local}@${domain}`;
}

/**
 * Campaign targeting attributes, applied as a pass over the finished book.
 *
 * This deliberately draws from its OWN generator rather than the shared `rand`
 * above. Adding draws to that sequence would shift every value after them and
 * reshuffle all 75 contacts, breaking the anchored numbers the QA runbook
 * checks against ("710 days overdue", 25 bookmarked, and so on).
 */
const targetingRand = mulberry32(20260901);

function pickWith<T>(arr: T[]): T {
  return arr[Math.floor(targetingRand() * arr.length)];
}

/**
 * Gender is taken from the first name rather than drawn at random, because a
 * contact called Amanda listed as Male reads as a bug in the seed even though
 * the targeting would work fine. Ambiguous Chinese given names use the
 * conventional reading; this is demo data, not a claim about anyone.
 */
const FEMALE_FIRST_NAMES = new Set([
  'Wei Ling', 'Priya', 'Amanda', 'Nurul', 'Michelle', 'Farah', 'Clarissa', 'Aisha',
  'Grace', 'Melissa', 'Yi Xuan', 'Rachel', 'Kai Xin', 'Serene', 'Deepa', 'Shu Fen',
  'Natalie', 'Joanne', 'Nadia', 'Lakshmi', 'Sarah', 'Siti', 'Siti Adilah', 'Siti Amina',
]);

function genderFor(name: string): Gender {
  const first = name.split(' ')[0];
  const twoWord = name.split(' ').slice(0, 2).join(' ');
  if (FEMALE_FIRST_NAMES.has(twoWord) || FEMALE_FIRST_NAMES.has(first)) return 'female';
  return 'male';
}

/**
 * Cash amounts, in SGD, weighted by income where it is on file. Income is a
 * hint, not a derivation — a high earner with no liquidity is exactly the case
 * the criteria need to be able to tell apart. Amounts are stored rather than
 * bands so a custom-amount filter has a real number to compare against.
 */
const CASH_BY_INCOME: Record<string, [number, number][]> = {
  '$85,000': [[8_000, 45_000], [12_000, 60_000], [20_000, 90_000]],
  '$120,000': [[15_000, 48_000], [40_000, 150_000], [60_000, 200_000]],
  '$185,000': [[70_000, 240_000], [90_000, 245_000], [180_000, 400_000]],
  '$240,000': [[120_000, 249_000], [200_000, 600_000], [300_000, 800_000]],
  '$310,000': [[260_000, 700_000], [400_000, 950_000], [700_000, 1_600_000]],
  '$450,000': [[300_000, 900_000], [800_000, 2_200_000], [1_200_000, 3_500_000]],
};

const CASH_UNKNOWN_INCOME: [number, number][] = [
  [5_000, 45_000],
  [50_000, 150_000],
  [90_000, 245_000],
  [260_000, 600_000],
  [500_000, 980_000],
  [1_100_000, 2_800_000],
];

/** Rounded to the nearest thousand so the figures read like real balances. */
function cashWithin([low, high]: [number, number]): number {
  const raw = low + targetingRand() * (high - low);
  return Math.round(raw / 1000) * 1000;
}

/**
 * Records left deliberately incomplete, by index, so the "incomplete profiles"
 * path in campaign targeting has something real to show. Fixed rather than
 * random to keep the counts quotable. Anchor contacts (0-5) stay complete —
 * they carry the demo.
 */
const NO_CASH_AMOUNT = new Set([12, 27, 41, 58, 66]);
const NO_GENDER = new Set([19, 34, 52]);

function enrichTargeting(contacts: Contact[]): void {
  contacts.forEach((contact, index) => {
    // Six anchor contacts carry no DOB; targeting needs one for everybody.
    if (!contact.dob) {
      const year = 1962 + Math.floor(targetingRand() * 29);
      const month = String(1 + Math.floor(targetingRand() * 12)).padStart(2, '0');
      const day = String(1 + Math.floor(targetingRand() * 28)).padStart(2, '0');
      contact.dob = `${year}-${month}-${day}`;
    }

    const income = contact.profile?.annualIncome;
    const spread = (income && CASH_BY_INCOME[income]) || CASH_UNKNOWN_INCOME;
    const amount = cashWithin(pickWith(spread));

    if (!NO_GENDER.has(index)) contact.gender = genderFor(contact.name);
    if (!NO_CASH_AMOUNT.has(index)) contact.cashAmount = amount;
  });
}

/**
 * Provenance and policy holdings, layered on as a further pass with its own
 * PRNG stream — same reason enrichTargeting has one: nothing here may draw
 * from `rand` or `targetingRand`, or every downstream value in either
 * sequence shifts and the anchored numbers stop matching.
 */
const provenanceRand = mulberry32(20260915);

function pickProvenance<T>(arr: T[]): T {
  return arr[Math.floor(provenanceRand() * arr.length)];
}

/** Most of the book holds something; a third holds nothing at all. */
function buildPolicies(): Policy[] {
  const roll = provenanceRand();
  const count = roll > 0.66 ? 0 : roll > 0.55 ? 2 : 1;

  return Array.from({ length: count }, () => ({
    provider: pickProvenance(PROVIDERS),
    type: pickProvenance(POLICY_TYPES),
    since: shiftDays(-Math.floor(365 + provenanceRand() * 2900)),
  }));
}

/**
 * Roughly a fifth of the book was inherited from an advisor who left. Those
 * arrive as clients with policies already in force but no relationship with
 * the current advisor, and most have not been introduced yet.
 */
function buildProvenance(): Partial<Contact> {
  const roll = provenanceRand();

  if (roll > 0.8) {
    return {
      source: 'transferred',
      transferredFrom: pickProvenance(PREVIOUS_ADVISORS),
      transferredOn: shiftDays(-Math.floor(30 + provenanceRand() * 300)),
      introduced: provenanceRand() > 0.7,
    };
  }

  if (roll > 0.72) return { source: 'referral' };
  if (roll > 0.62) return { source: 'canvassed' };
  return { source: 'own' };
}

/**
 * Two anchors carry hand-picked provenance rather than random: Steven (index 0)
 * already holds the Prudential life policy his meeting notes reference, and
 * Kayden O'Connor (index 4) guarantees the "transferred, not yet introduced"
 * banner has something real to show rather than depending on the dice.
 */
function enrichProvenance(contacts: Contact[]): void {
  contacts.forEach((contact, index) => {
    if (index === 0) {
      contact.policies = [{ provider: 'Prudential', type: 'Life', since: '2019-05-02' }];
      contact.lastContacted = '2026-06-19';
      contact.source = 'own';
      return;
    }

    if (index === 4) {
      contact.policies = [
        { provider: 'Prudential', type: 'Life', since: shiftDays(-2500) },
        { provider: 'AIA', type: 'Hospitalisation', since: shiftDays(-1800) },
      ];
      // Inherited, dormant, and never introduced — two policies in force, and
      // he has no idea who the advisor is.
      contact.lastContacted = shiftDays(-800);
      contact.source = 'transferred';
      contact.transferredFrom = 'Marcus Tan';
      contact.transferredOn = shiftDays(-180);
      contact.introduced = false;
      return;
    }

    contact.policies = buildPolicies();
    // Spread across the last three years so recency judgement calls have
    // something real to look at.
    contact.lastContacted = shiftDays(-Math.floor(provenanceRand() * 1000));
    Object.assign(contact, buildProvenance());
  });
}

function buildContacts(): Contact[] {
  const contacts: Contact[] = [...ANCHOR_CONTACTS];

  TASK_CONTACT_NAMES.forEach((name, i) => {
    contacts.push({
      id: String(contacts.length + 1),
      name,
      email: emailFor(name, EMAIL_DOMAINS[i % EMAIL_DOMAINS.length]),
      countryCode: '+65',
      phone: `9${Math.floor(1000000 + rand() * 8999999)}`,
      label: pick(LABELS),
    });
  });

  let guard = 0;
  while (contacts.length < 75 && guard < 1000) {
    guard++;
    const name = `${pick(FIRST_NAMES)} ${pick(LAST_NAMES)}`;
    if (contacts.some((c) => c.name === name)) continue;

    const hasProfile = rand() > 0.45;

    contacts.push({
      id: String(contacts.length + 1),
      name,
      email: emailFor(name, pick(EMAIL_DOMAINS)),
      countryCode: '+65',
      phone: rand() > 0.25 ? String(Math.floor(80000000 + rand() * 19999999)) : '',
      dob: `19${Math.floor(60 + rand() * 35)}-${String(
        Math.floor(1 + rand() * 12),
      ).padStart(2, '0')}-${String(Math.floor(1 + rand() * 28)).padStart(2, '0')}`,
      nric: `S${Math.floor(1000000 + rand() * 8999999)}${'ABCDEFGHJZ'[Math.floor(rand() * 10)]}`,
      label: pick(LABELS),
      bookmarked: rand() > 0.68,
      needsAttention: rand() > 0.88,
      profile: hasProfile
        ? {
            occupation: pick(OCCUPATIONS),
            companyName: pick(COMPANIES),
            annualIncome: pick(INCOMES),
            streetAddress: pick(STREETS),
            city: 'Singapore',
            country: 'Singapore',
            postcode: String(Math.floor(100000 + rand() * 799999)),
            eStatement: rand() > 0.5,
            accreditedInvestor: rand() > 0.8,
            mailingAddress: true,
          }
        : undefined,
    });
  }

  // Pin the bookmark count to 25 so the summary card reads against real data.
  let bookmarked = contacts.filter((c) => c.bookmarked).length;
  for (const c of contacts) {
    if (bookmarked === 25) break;
    if (bookmarked < 25 && !c.bookmarked) {
      c.bookmarked = true;
      bookmarked++;
    } else if (bookmarked > 25 && c.bookmarked) {
      c.bookmarked = false;
      bookmarked--;
    }
  }

  enrichTargeting(contacts);
  enrichProvenance(contacts);

  return contacts;
}

export const SEED_CONTACTS: Contact[] = buildContacts();

function byName(name: string): Contact | undefined {
  return SEED_CONTACTS.find((c) => c.name === name);
}

interface AnchorTask {
  title: string;
  description: string;
  contact?: string;
  overdue: number;
}

/** The first ten rows reproduce the production task list. */
const ANCHOR_TASKS: AnchorTask[] = [
  {
    title: 'Client Agreement Form Collection',
    description: 'Follow up with Jason Rahman to submit signed client agreement form.',
    contact: 'Jason Rahman',
    overdue: 710,
  },
  {
    title: 'Client Agreement Submission',
    description: 'Follow up with Siti Amina to ensure she submits the signed client agreement form.',
    contact: 'Siti Amina Yusuf',
    overdue: 345,
  },
  {
    title: 'Retirement Planning Analysis',
    description: 'Model a 10-year retirement plan for Siti Chong assuming 6-7% average annual returns.',
    contact: 'Siti Chong',
    overdue: 345,
  },
  {
    title: 'Collect Signed Client Agreement',
    description: 'Ensure Siti Chong submits the signed client agreement form by 15th September.',
    contact: 'Siti Chong',
    overdue: 345,
  },
  {
    title: 'Client Agreement Submission',
    description: 'Ensure Kevin submits the signed client agreement form before the deadline.',
    contact: 'Kevin O’Connor',
    overdue: 345,
  },
  {
    title: 'Client Agreement Form Submission',
    description: 'Ensure Siti Amina Yusuf submits signed client agreement form.',
    contact: 'Siti Amina Yusuf',
    overdue: 345,
  },
  {
    title: 'Compliance Deadline - Client Suitability Forms',
    description: 'Complete all outstanding client suitability forms by compliance deadline.',
    contact: 'Minghao Chen',
    overdue: 345,
  },
  { title: 'Send Meeting Confirmation', description: '', overdue: 112 },
  { title: 'Prepare Term Life Insurance Quotation', description: '', overdue: 112 },
  { title: 'Prepare Early Critical Illness Insurance Options', description: '', overdue: 112 },
];

interface TaskTemplate {
  title: string;
  description: (name: string) => string;
  type: TaskType;
}

const TASK_TEMPLATES: TaskTemplate[] = [
  {
    title: 'Client Agreement Submission',
    description: (n) => `Follow up with ${n} to submit the signed client agreement form.`,
    type: 'CRM',
  },
  {
    title: 'Annual Portfolio Review',
    description: (n) => `Prepare the annual portfolio review pack for ${n}.`,
    type: 'CRM',
  },
  {
    title: 'Retirement Planning Analysis',
    description: (n) => `Model a 10-year retirement plan for ${n} assuming 6-7% average annual returns.`,
    type: 'CRM',
  },
  {
    title: 'Client Suitability Form',
    description: (n) => `Complete the outstanding suitability assessment for ${n}.`,
    type: 'Compliance',
  },
  {
    title: 'KYC Refresh',
    description: (n) => `Refresh know-your-client documentation for ${n} ahead of the review cycle.`,
    type: 'Compliance',
  },
  {
    title: 'Prepare Term Life Insurance Quotation',
    description: (n) => `Draft a term life quotation for ${n} based on the latest needs analysis.`,
    type: 'CRM',
  },
  {
    title: 'Prepare Early Critical Illness Options',
    description: (n) => `Compile early-stage CI plan options for ${n}.`,
    type: 'CRM',
  },
  {
    title: 'Send Meeting Confirmation',
    description: (n) => `Send the meeting confirmation and agenda to ${n}.`,
    type: 'Manual',
  },
  {
    title: 'Policy Audit Review',
    description: (n) => `Audit existing in-force policies held by ${n}.`,
    type: 'Compliance',
  },
  {
    title: 'Follow Up On Fund Switch',
    description: (n) => `Confirm the requested fund switch instruction with ${n}.`,
    type: 'CRM',
  },
  {
    title: 'Schedule Quarterly Check-In',
    description: (n) => `Book the quarterly relationship check-in with ${n}.`,
    type: 'Manual',
  },
  {
    title: 'Campaign Follow-Up Call',
    description: (n) => `Call ${n} following the wealth seminar invitation.`,
    type: 'Campaign',
  },
];

function buildTasks(): Task[] {
  const tasks: Task[] = [];

  ANCHOR_TASKS.forEach((t, i) => {
    const contact = t.contact ? byName(t.contact) : undefined;
    tasks.push({
      id: `t${i + 1}`,
      contactId: contact ? contact.id : '',
      contactName: contact ? contact.name : '',
      title: t.title,
      description: t.description,
      type: 'CRM',
      startDate: shiftDays(-t.overdue - 14),
      dueDate: shiftDays(-t.overdue),
      status: 'todo',
    });
  });

  // Fill to 180 open tasks, weighted towards overdue to match production.
  while (tasks.length < 180) {
    const template = pick(TASK_TEMPLATES);
    const contact = pick(SEED_CONTACTS);
    const linked = rand() > 0.12;
    const offset = rand() > 0.25 ? -Math.floor(1 + rand() * 400) : Math.floor(1 + rand() * 45);

    tasks.push({
      id: `t${tasks.length + 1}`,
      contactId: linked ? contact.id : '',
      contactName: linked ? contact.name : '',
      title: template.title,
      description: linked && rand() > 0.2 ? template.description(contact.name) : '',
      type: template.type,
      startDate: shiftDays(offset - 14),
      dueDate: shiftDays(offset),
      status: 'todo',
    });
  }

  ['Client Agreement Form Collection', 'Annual Portfolio Review', 'KYC Refresh'].forEach(
    (title, i) => {
      const contact = SEED_CONTACTS[i + 1];
      tasks.push({
        id: `t${tasks.length + 1}`,
        contactId: contact.id,
        contactName: contact.name,
        title,
        description: `Completed for ${contact.name}.`,
        type: i === 2 ? 'Compliance' : 'CRM',
        startDate: shiftDays(-Math.floor(80 + rand() * 40)),
        dueDate: shiftDays(-Math.floor(10 + rand() * 60)),
        status: 'done',
      });
    },
  );

  return tasks;
}

export const SEED_TASKS: Task[] = buildTasks();

export const SEED_PIPELINE: PipelineItem[] = [
  {
    id: 'pipe-4',
    caseId: 4,
    contactId: '1',
    contactName: 'Steven',
    contactLabel: 'Prospect',
    stage: 'opportunities',
    startDate: shiftDays(0),
    dueDate: shiftDays(30),
    description: '',
  },
  {
    id: 'pipe-5',
    caseId: 5,
    contactId: '2',
    contactName: 'Joseph Rahman',
    contactLabel: 'Prospect',
    stage: 'activities',
    startDate: shiftDays(0),
    dueDate: shiftDays(30),
    description: '',
  },
];

/**
 * Campaigns already sitting in the advisor's inbox on first load, so the module
 * is not empty before Marketing has authored anything this session.
 */
export const SEED_CAMPAIGNS: Campaign[] = [
  {
    id: 'camp-1',
    name: 'Legacy Protection Refresh',
    description:
      'Q4 push on estate and legacy planning for our established client base. Priority is on clients approaching or past retirement who hold meaningful liquid assets but have not reviewed their protection cover in the last three years. Lead with the wealth transfer angle, not the premium.',
    clientMessage:
      'Your protection plan was built for a different stage of life. We are offering complimentary legacy planning reviews this quarter — a 45-minute session covering how your current cover would pass on, what it would be worth after tax, and where the gaps sit. No obligation, and we can do it over a call.',
    origin: 'marketing',
    audienceSource: 'contacts',
    channel: 'BANCA-SG',
    teamIds: [],
    advisorIds: [],
    criteria: {
      ageGroups: ['55to64', '65plus'],
      genders: [],
      cashBands: ['250kTo1m', 'above1m'],
    },
    createdBy: 'Marketing',
    createdAt: shiftDays(-9),
    includeIds: [],
    excludeIds: [],
    leadIds: [],
    leadStats: { uploaded: 0, added: 0, removed: 0 },
    actions: {},
    emailLog: [],
  },
  {
    id: 'camp-2',
    name: 'First Home Starter Bundle',
    description:
      'Acquisition campaign aimed at younger clients and prospects entering the property market. Bundles mortgage protection with a starter critical illness rider at a reduced first-year premium. Marketing owns the digital spend; advisors handle follow-up on qualified leads only.',
    clientMessage:
      'Buying your first home is the point most people are most exposed — a mortgage, and nothing standing behind it. Our starter bundle covers the loan and adds early-stage critical illness protection, at a reduced premium for the first year. Happy to walk you through the numbers.',
    origin: 'marketing',
    audienceSource: 'contacts',
    channel: 'BANCA-SG',
    teamIds: ['marina-bay-branch'],
    advisorIds: [],
    criteria: {
      ageGroups: ['under35', '35to44'],
      genders: [],
      cashBands: ['under50k', '50kTo250k'],
    },
    createdBy: 'Marketing',
    createdAt: shiftDays(-3),
    includeIds: [],
    excludeIds: [],
    leadIds: [],
    leadStats: { uploaded: 0, added: 0, removed: 0 },
    actions: {},
    emailLog: [],
  },
];
