import {
  AgeGroup,
  Campaign,
  CampaignGender,
  CampaignCriteria,
  CashBand,
  Contact,
  Gender,
  NumericRange,
} from '../types';
import { TODAY_ISO } from '../data/seed';

/**
 * ============================================================================
 * CAMPAIGN TARGETING — the deterministic half
 * ============================================================================
 * Which clients a campaign reaches is decided here, by rules, not by the model
 * in services/ai.ts. Selection has to be reproducible and explainable: an
 * advisor asking "why was this client on the list" gets the same answer every
 * time, and the same criteria always produce the same audience.
 *
 * The AI layer sits on top of this output and only ever reorders it and writes
 * about it. It never adds or removes a client.
 */

export const AGE_GROUPS: AgeGroup[] = ['under35', '35to44', '45to54', '55to64', '65plus'];

export const AGE_GROUP_LABELS: Record<AgeGroup, string> = {
  under35: 'Under 35',
  '35to44': '35 - 44',
  '45to54': '45 - 54',
  '55to64': '55 - 64',
  '65plus': '65 and above',
};

export const GENDERS: CampaignGender[] = ['Male', 'Female'];

export const GENDER_LABELS: Record<Gender | CampaignGender, string> = {
  male: 'Male',
  female: 'Female',
  Male: 'Male',
  Female: 'Female',
};

export const CASH_BANDS: CashBand[] = ['under50k', '50kTo250k', '250kTo1m', 'above1m'];

export const CASH_BAND_LABELS: Record<CashBand, string> = {
  under50k: 'Under S$50k',
  '50kTo250k': 'S$50k - S$250k',
  '250kTo1m': 'S$250k - S$1M',
  above1m: 'Above S$1M',
};

/** Lower bound of each band, in SGD. The band is derived, never stored. */
const CASH_BAND_FLOOR: [CashBand, number][] = [
  ['above1m', 1_000_000],
  ['250kTo1m', 250_000],
  ['50kTo250k', 50_000],
  ['under50k', 0],
];

function targetingKey(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9]/g, '');
}

const AGE_GROUP_ALIASES: Record<string, AgeGroup> = {
  under35: 'under35',
  '35to44': '35to44',
  '3544': '35to44',
  '45to54': '45to54',
  '4554': '45to54',
  '55to64': '55to64',
  '5564': '55to64',
  '65plus': '65plus',
  '65andabove': '65plus',
};

const CASH_BAND_ALIASES: Record<string, CashBand> = {
  under50k: 'under50k',
  '50kto250k': '50kTo250k',
  '50k250k': '50kTo250k',
  '250kto1m': '250kTo1m',
  '250k1m': '250kTo1m',
  above1m: 'above1m',
};

function normalizeAgeGroup(value: string): AgeGroup | undefined {
  return AGE_GROUP_ALIASES[targetingKey(value)];
}

function normalizeCashBand(value: string): CashBand | undefined {
  return CASH_BAND_ALIASES[targetingKey(value)];
}

export function cashBandOf(contact: Contact): CashBand | undefined {
  if (contact.cashAmount === undefined || contact.cashAmount === null) return undefined;
  const hit = CASH_BAND_FLOOR.find(([, floor]) => contact.cashAmount! >= floor);
  return hit ? hit[0] : 'under50k';
}

/** "S$420,000" */
export function formatCash(amount: number | null | undefined): string | undefined {
  if (amount === undefined || amount === null) return undefined;
  return `S$${amount.toLocaleString('en-SG')}`;
}

/** An open-ended range still filters; a range with neither end set does not. */
export function hasRange(range: NumericRange | undefined): boolean {
  return Boolean(range && (range.min !== undefined || range.max !== undefined));
}

function ageRangeOf(criteria: CampaignCriteria): NumericRange | undefined {
  if (criteria.ageCustomMin !== undefined || criteria.ageCustomMax !== undefined) {
    return { min: criteria.ageCustomMin, max: criteria.ageCustomMax };
  }
  return criteria.ageRange;
}

function cashRangeOf(criteria: CampaignCriteria): NumericRange | undefined {
  if (criteria.cashCustomMin !== undefined || criteria.cashCustomMax !== undefined) {
    return { min: criteria.cashCustomMin, max: criteria.cashCustomMax };
  }
  return criteria.cashRange;
}

function inRange(value: number, range: NumericRange | undefined): boolean {
  if (!hasRange(range)) return false;
  if (range!.min !== undefined && value < range!.min) return false;
  if (range!.max !== undefined && value > range!.max) return false;
  return true;
}

/** Age against the prototype's fixed "today", not the wall clock. */
export function ageFromDob(dob: string | null | undefined): number | undefined {
  if (!dob) return undefined;
  const born = new Date(`${dob}T00:00:00`);
  if (Number.isNaN(born.getTime())) return undefined;

  const today = new Date(`${TODAY_ISO}T00:00:00`);
  let age = today.getFullYear() - born.getFullYear();
  const monthDelta = today.getMonth() - born.getMonth();
  if (monthDelta < 0 || (monthDelta === 0 && today.getDate() < born.getDate())) age--;

  return age >= 0 && age < 130 ? age : undefined;
}

export function ageGroupOf(contact: Contact): AgeGroup | undefined {
  const age = ageFromDob(contact.dob);
  if (age === undefined) return undefined;
  if (age < 35) return 'under35';
  if (age < 45) return '35to44';
  if (age < 55) return '45to54';
  if (age < 65) return '55to64';
  return '65plus';
}

export const EMPTY_CRITERIA: CampaignCriteria = {
  ageGroups: [],
  genders: [],
  cashBands: [],
};

export function criteriaCount(criteria: CampaignCriteria): number {
  return (
    criteria.ageGroups.length +
    criteria.genders.length +
    criteria.cashBands.length +
    (criteria.ageGroups.length === 0 && hasRange(ageRangeOf(criteria)) ? 1 : 0) +
    (hasRange(cashRangeOf(criteria)) ? 1 : 0)
  );
}

/** Whether an age band or a custom range filters the age dimension. */
function filtersAge(criteria: CampaignCriteria): boolean {
  return criteria.ageGroups.length > 0 || hasRange(ageRangeOf(criteria));
}

function filtersCash(criteria: CampaignCriteria): boolean {
  return criteria.cashBands.length > 0 || hasRange(cashRangeOf(criteria));
}

export interface MatchResult {
  /** Meets every active criterion. */
  matched: Contact[];
  /**
   * Would have been tested against a criterion whose field is missing from the
   * record. Held out of the audience rather than silently dropped — an advisor
   * can complete the profile and bring them in.
   */
  incomplete: Contact[];
}

/**
 * Splits a book of contacts against a campaign's criteria.
 *
 * A criterion with no values selected does not filter. A contact missing the
 * field a *selected* criterion tests is never guessed at: it lands in
 * `incomplete` so the gap is visible instead of being read as a rejection.
 */
export function matchContacts(criteria: CampaignCriteria, contacts: Contact[]): MatchResult {
  const matched: Contact[] = [];
  const incomplete: Contact[] = [];
  const selectedAgeGroups = criteria.ageGroups
    .map(normalizeAgeGroup)
    .filter((group): group is AgeGroup => group !== undefined);
  const ageRange = ageRangeOf(criteria);
  const cashRange = cashRangeOf(criteria);
  const usesAgeRange = selectedAgeGroups.length === 0 && hasRange(ageRange);
  const filtersAgeDimension = selectedAgeGroups.length > 0 || usesAgeRange;

  for (const contact of contacts) {
    const age = ageFromDob(contact.dob);
    const group = ageGroupOf(contact);
    const band = cashBandOf(contact);

    const missing =
      (filtersAgeDimension && age === undefined) ||
      (criteria.genders.length > 0 &&
        (contact.gender === undefined || contact.gender === null)) ||
      (filtersCash(criteria) &&
        (contact.cashAmount === undefined || contact.cashAmount === null));

    if (missing) {
      incomplete.push(contact);
      continue;
    }

    // Explicit age bands take precedence over a stale or legacy custom range.
    const ageOk =
      !filtersAgeDimension ||
      (selectedAgeGroups.length > 0
        ? group !== undefined && selectedAgeGroups.includes(group)
        : inRange(age!, ageRange));

    const cashOk =
      !filtersCash(criteria) ||
      (band !== undefined &&
        criteria.cashBands.some((value) => normalizeCashBand(value) === band)) ||
      inRange(contact.cashAmount!, cashRange);

    const genderOk =
      criteria.genders.length === 0 ||
      criteria.genders.some(
        (gender) => gender.trim().toLowerCase() === contact.gender?.trim().toLowerCase(),
      );

    if (ageOk && genderOk && cashOk) matched.push(contact);
  }

  return { matched, incomplete };
}

/** "Age 45 - 54 · Business Owner · S$250k - S$1M" — the row-level audit line. */
export function describeContactTargeting(contact: Contact): string {
  const group = ageGroupOf(contact);
  return [
    group ? `Age ${AGE_GROUP_LABELS[group]}` : null,
    contact.gender ? GENDER_LABELS[contact.gender] : null,
    formatCash(contact.cashAmount) ?? null,
  ]
    .filter(Boolean)
    .join(' · ');
}

/**
 * The audience for a campaign, whichever kind it is.
 *
 * Contact campaigns are a live criteria query with hand-picked overrides on
 * top: matches, plus anyone explicitly included, minus anyone explicitly
 * excluded. Change a contact's cash band and the criteria half re-evaluates,
 * but the overrides always win.
 *
 * Lead campaigns ignore criteria completely — the uploaded list is the
 * audience, in upload order, and nothing is ever "incomplete" because there is
 * no criterion to be missing a field for.
 */
export type AudienceSpec = Pick<
  Campaign,
  'audienceSource' | 'criteria' | 'includeIds' | 'excludeIds' | 'leadIds'
>;

export function resolveAudience(campaign: AudienceSpec, contacts: Contact[]): MatchResult {
  const byId = new Map(contacts.map((c) => [c.id, c]));

  if (campaign.audienceSource === 'leads') {
    return {
      matched: campaign.leadIds
        .map((id) => byId.get(id))
        .filter((c): c is Contact => Boolean(c)),
      incomplete: [],
    };
  }

  const excluded = new Set(campaign.excludeIds);

  // Leads are never criteria-matched. They belong to their own campaign and
  // must not surface in a contact campaign's audience or its incomplete list,
  // so the filter lives here rather than in each caller.
  const { matched, incomplete } = matchContacts(
    campaign.criteria,
    contacts.filter((c) => c.status !== 'lead'),
  );

  const audience = matched.filter((c) => !excluded.has(c.id));
  const present = new Set(audience.map((c) => c.id));

  // Hand-picked additions need not match the criteria — that is the point.
  for (const id of campaign.includeIds) {
    const contact = byId.get(id);
    if (contact && !present.has(id) && !excluded.has(id)) {
      audience.push(contact);
      present.add(id);
    }
  }

  return {
    matched: audience,
    // Someone added by hand is answered for; they are not an open data gap.
    incomplete: incomplete.filter((c) => !present.has(c.id) && !excluded.has(c.id)),
  };
}

/** Which criteria a contact is missing, for the incomplete-profiles list. */
export function missingFieldsFor(contact: Contact, criteria: CampaignCriteria): string[] {
  const gaps: string[] = [];
  if (filtersAge(criteria) && ageFromDob(contact.dob) === undefined) gaps.push('Date of birth');
  if (criteria.genders.length > 0 && !contact.gender) gaps.push('Demographic');
  if (
    filtersCash(criteria) &&
    (contact.cashAmount === undefined || contact.cashAmount === null)
  ) {
    gaps.push('Cash availability');
  }
  return gaps;
}
