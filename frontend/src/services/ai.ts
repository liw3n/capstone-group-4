import { Contact, TaskType } from '../types';
import { addDaysISO } from '../lib/format';
import { firstName } from '../lib/email';
import { ageFromDob, cashBandOf, GENDER_LABELS } from '../lib/targeting';

/**
 * ============================================================================
 * THE AI SEAM
 * ============================================================================
 * Every "AI" call in the app goes through this file, and every one of them is
 * currently simulated. Nothing in this module talks to a network. The live
 * PULSE chat uses services/chatApi.ts and keeps its provider key in the backend.
 *
 * To make this real, replace the exported functions with fetch() calls to a
 * server-side route that holds the key. Their signatures and return shapes are
 * the contract the UI depends on; keep those stable and nothing else has to
 * change.
 *
 * What is genuinely real today:
 *   - Spreadsheet parsing. Headers and rows come from the actual uploaded file.
 *   - Column matching. Heuristic, deterministic, and good enough in practice.
 *   - Campaign audience selection — but that is not in this file at all. It is a
 *     rules engine in lib/targeting.ts, and rankCampaignAudience() cannot add
 *     or remove a client, only reorder and annotate the list it is given.
 * What is faked:
 *   - Reading the contents of meeting recordings, PDFs, and transcripts. Files
 *     are accepted and listed by name; their bytes are never inspected.
 *   - The summary and task text, which is composed from a fixed template.
 *   - Campaign ranking and copy. The score is a real weighted formula over real
 *     contact fields, but the rationale and draft message are templated.
 */

/* -------------------------------------------------------------------------- */
/* Contact import — column matching                                           */
/* -------------------------------------------------------------------------- */

export type ContactField =
  | 'name'
  | 'email'
  | 'countryCode'
  | 'phone'
  | 'dob'
  | 'nric'
  | 'label'
  | 'ignore';

export const CONTACT_FIELD_LABELS: Record<ContactField, string> = {
  name: 'Name',
  email: 'Email',
  countryCode: 'Country Code',
  phone: 'Phone Number',
  dob: 'Date of Birth',
  nric: 'NRIC/Passport',
  label: 'Label',
  ignore: 'Do not import',
};

/** Every mappable field, in picker order. Derived so the two never drift. */
export const CONTACT_FIELDS = Object.keys(CONTACT_FIELD_LABELS) as ContactField[];

export const REQUIRED_FIELDS: ContactField[] = ['name', 'email', 'phone'];

/** Header synonyms, checked in order. First hit wins. */
const FIELD_PATTERNS: [ContactField, RegExp][] = [
  ['countryCode', /^(country[\s_-]?code|dial(ling)?[\s_-]?code|idd|prefix)$/i],
  ['name', /(full[\s_-]?name|contact[\s_-]?name|client[\s_-]?name|^name$|customer)/i],
  ['email', /(e[\s_-]?mail|email[\s_-]?address)/i],
  ['phone', /(phone|mobile|contact[\s_-]?(number|no)|hp|handphone|tel)/i],
  ['dob', /(d\.?o\.?b\.?|date[\s_-]?of[\s_-]?birth|birth[\s_-]?date|birthday)/i],
  ['nric', /(nric|fin|passport|identity|ic[\s_-]?(no|number))/i],
  ['label', /(label|type|segment|status|category|tag)/i],
];

export interface ColumnMatch {
  header: string;
  field: ContactField;
  /** Whether the match came from a header hit rather than a fallback. */
  confident: boolean;
}

/**
 * Maps spreadsheet headers onto contact fields. Each field is claimed at most
 * once, so a file with both "Phone" and "Mobile" does not map both to phone.
 */
export async function suggestColumnMapping(headers: string[]): Promise<ColumnMatch[]> {
  await simulateLatency(600);

  const claimed = new Set<ContactField>();

  return headers.map((header) => {
    const clean = header.trim();

    for (const [field, pattern] of FIELD_PATTERNS) {
      if (claimed.has(field)) continue;
      if (pattern.test(clean)) {
        claimed.add(field);
        return { header, field, confident: true };
      }
    }

    return { header, field: 'ignore' as ContactField, confident: false };
  });
}

/* -------------------------------------------------------------------------- */
/* Meeting analysis                                                           */
/* -------------------------------------------------------------------------- */

export interface GeneratedTask {
  id: string;
  title: string;
  description: string;
  type: TaskType;
  startDate: string;
  dueDate: string;
  /** Unchecked tasks are discarded when the advisor saves. */
  include: boolean;
}

export interface MeetingAnalysis {
  title: string;
  summary: string;
  tasks: GeneratedTask[];
}

export interface AnalyseMeetingInput {
  contactName: string;
  date: string;
  notes: string;
  fileNames: string[];
  /** Reports 0-100 so the caller can drive a progress bar. */
  onProgress?: (percent: number) => void;
}

const TASK_BLUEPRINTS: { title: string; description: string; type: TaskType; due: number }[] = [
  {
    title: 'Submit Signed Application',
    description:
      'Finalize submission of signed digital application for Whole Life Plan B ($250k sum assured) via e-signature portal.',
    type: 'CRM',
    due: 14,
  },
  {
    title: 'Confirm KYC Documentation',
    description:
      'Verify uploaded 3 months of payslips meet income verification requirements for the submitted application.',
    type: 'CRM',
    due: 14,
  },
  {
    title: 'Review Health Declaration',
    description:
      'Confirm no follow-up needed on disclosed medical history; no major red flags identified during the declaration review.',
    type: 'Compliance',
    due: 14,
  },
  {
    title: 'Track Application Processing',
    description:
      'Monitor underwriting status of Whole Life Plan B application post-submission and escalate if it stalls beyond SLA.',
    type: 'CRM',
    due: 21,
  },
  {
    title: 'Schedule Policy Handover',
    description:
      'Book the policy handover meeting once underwriting approves, and prepare the welcome pack for the client.',
    type: 'Manual',
    due: 28,
  },
];

export async function analyseMeeting(input: AnalyseMeetingInput): Promise<MeetingAnalysis> {
  const { contactName, date, notes, onProgress } = input;

  // Walk the progress bar to 100 over roughly three seconds.
  for (let percent = 0; percent <= 100; percent += 4) {
    onProgress?.(percent);
    await simulateLatency(110);
  }

  const trimmedNotes = notes.trim();

  const summary = trimmedNotes
    ? trimmedNotes
    : `The advisor and client ${contactName} reviewed the client's employer coverage gap and presented three Critical Illness solution options to address a $300,000 shortfall. The client selected Option B (Whole Life with Early CI Focus) with a $250k sum assured, completed health declarations and KYC documentation, and signed the digital application pending final submission.`;

  return {
    title: 'Finalized Whole Life Critical Illness Protection Plan',
    summary,
    tasks: TASK_BLUEPRINTS.map((blueprint, i) => ({
      id: `gen-${i}`,
      title: blueprint.title,
      description: blueprint.description,
      type: blueprint.type,
      startDate: date,
      // Always at or after the start date. The reference design shows a task
      // whose due date precedes its start; that is a bug, not a spec.
      dueDate: addDaysISO(date, blueprint.due),
      include: true,
    })),
  };
}

function simulateLatency(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/* -------------------------------------------------------------------------- */
/* Campaign audience — ranking and copy                                       */
/* -------------------------------------------------------------------------- */

/**
 * Note what this function does NOT do: it never decides who is in the audience.
 * Selection is a rules job and lives in lib/targeting.ts, because an advisor has
 * to be able to ask why a client was targeted and get the same answer twice.
 * This only reorders an audience it was handed, and writes about it.
 */

export interface CampaignRecommendation {
  contactId: string;
  /** Exposed so the ordering is inspectable rather than a black box. */
  score: number;
  /** Why this client, phrased from attributes actually on the record. */
  rationale: string;
  /** Marketing's message, adapted for this client. */
  draftMessage: string;
}

export interface RankAudienceInput {
  campaignName: string;
  clientMessage: string;
  contacts: Contact[];
}

const CASH_WEIGHT: Record<string, number> = {
  above1m: 40,
  '250kTo1m': 30,
  '50kTo250k': 18,
  under50k: 8,
};

/**
 * Keyed on life stage rather than on gender. Gender is a targeting attribute,
 * not a reason to write to someone differently, and age is what actually
 * changes the financial argument.
 */
function openerForAge(age: number | undefined): string {
  if (age === undefined) return 'while the timing suits';
  if (age < 35) return 'while the cover is cheap to lock in';
  if (age < 45) return 'with the family depending on it';
  if (age < 55) return 'while you are still building';
  if (age < 65) return 'before you draw down';
  return 'so the estate passes on cleanly';
}

/**
 * Deterministic on purpose. The same book of clients ranks the same way on
 * every reload, which is what makes the list trustworthy to demo against.
 */
function scoreContact(contact: Contact): { score: number; reasons: string[] } {
  const reasons: string[] = [];
  let score = 0;

  const band = cashBandOf(contact);
  if (band) {
    score += CASH_WEIGHT[band];
    if (band === 'above1m' || band === '250kTo1m') {
      reasons.push('holds enough liquidity to act this quarter');
    }
  }

  if (contact.label === 'Client') {
    score += 15;
    reasons.push('already a client, so no cold introduction needed');
  } else if (contact.label === 'Prospect') {
    score += 8;
  }

  if (contact.needsAttention) {
    score += 12;
    reasons.push('flagged as needing attention');
  }

  if (contact.bookmarked) {
    score += 10;
    reasons.push('bookmarked in your book');
  }

  const meetings = contact.meetings?.length ?? 0;
  if (meetings > 0) {
    score += 6;
    reasons.push(`${meetings} meeting${meetings === 1 ? '' : 's'} already on the timeline`);
  } else {
    reasons.push('no meeting recorded yet');
  }

  return { score, reasons };
}

export async function rankCampaignAudience(
  input: RankAudienceInput,
): Promise<CampaignRecommendation[]> {
  const { clientMessage, contacts } = input;

  // No simulated latency here, deliberately. Scoring is a pure function over
  // data already in memory, and a chained-setTimeout progress walk stalls
  // outright in a backgrounded tab — the advisor would come back to a list
  // stuck on "Prioritising..." forever. The function stays async so a real
  // server call can drop straight in behind the same signature.
  const ranked = contacts.map((contact) => {
    const { score, reasons } = scoreContact(contact);

    const age = ageFromDob(contact.dob);
    const opener = openerForAge(age);

    // Ties break on name so the order never wobbles between renders.
    return {
      contactId: contact.id,
      score,
      rationale: `${age ? `${age}` : 'Age unknown'}${
        contact.gender ? `, ${GENDER_LABELS[contact.gender]}` : ''
      } — ${reasons.slice(0, 2).join('; ')}.`,
      draftMessage: `Hi ${firstName(contact)}, ${lowerFirst(clientMessage.trim())}${
        clientMessage.trim().endsWith('.') ? '' : '.'
      } Worth a look ${opener} — shall I put 20 minutes in the diary?`,
    };
  });

  return ranked.sort((a, b) => b.score - a.score || a.contactId.localeCompare(b.contactId));
}

function lowerFirst(text: string): string {
  if (!text) return text;
  // Leave acronyms alone: "CI cover..." should not become "cI cover...".
  if (text.slice(0, 2) === text.slice(0, 2).toUpperCase() && text.length > 1) return text;
  return text[0].toLowerCase() + text.slice(1);
}
