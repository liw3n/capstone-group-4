export type ContactLabel = 'Prospect' | 'Client';

/** Selectable order for label pickers, so every picker offers the same list. */
export const CONTACT_LABELS: ContactLabel[] = ['Prospect', 'Client'];

/**
 * Whether a record is in the book yet. Deliberately NOT a third ContactLabel:
 * `label` says what kind of relationship this is (Prospect vs Client), status
 * says whether it counts as a contact at all. Merging them would silently
 * change the meaning of every `label === 'Prospect'` count.
 *
 * Leads come from uploaded canvassing lists. They are hidden everywhere except
 * the campaign module until an advisor promotes them; undefined means 'contact'.
 */
export type ContactStatus = 'lead' | 'contact';

export type PipelineStage = 'opportunities' | 'activities' | 'closed';

/** Only meaningful once a case reaches the closed stage. */
export type ClosedOutcome = 'won' | 'lost';

export type TaskType = 'CRM' | 'Compliance' | 'Campaign' | 'Manual';

/** Selectable order for task-type pickers and filters. */
export const TASK_TYPES: TaskType[] = ['CRM', 'Compliance', 'Campaign', 'Manual'];

export type TaskStatus = 'todo' | 'done';

/** The Contact Info tab. Every field is optional — most records come in partial. */
export interface ContactProfile {
  secondaryPhone?: string;
  eStatement?: boolean;
  accreditedInvestor?: boolean;

  streetAddress?: string;
  city?: string;
  stateProvince?: string;
  postcode?: string;
  country?: string;
  mailingAddress?: boolean;

  occupation?: string;
  companyName?: string;
  annualIncome?: string;
  officeNumber?: string;
  officeStreetAddress?: string;
  officeCity?: string;
  officeStateProvince?: string;
  officePostalCode?: string;
  officeCountry?: string;
}

export interface MeetingSummary {
  id: string;
  date: string;
  title: string;
  description: string;
  tasks: string[];
}

/**
 * How a person entered the book of business.
 *
 * This is a historical fact, not a status: it is set once when the record is
 * created and never edited afterwards. Where someone came from keeps explaining
 * the record long after they have become a client — a transferred client you
 * have never spoken to reads very differently from one you signed yourself.
 *
 * Records created before this field existed are treated as 'own'.
 */
export type ContactSource = 'own' | 'transferred' | 'canvassed' | 'referral';

/**
 * A policy the contact already holds. Lets campaign targeting and the
 * advisor's own judgement answer "who already has a Prudential life policy"
 * against real data rather than a guess.
 */
export interface Policy {
  provider: string;
  type: string;
  /** ISO date the policy started. */
  since: string;
}

export interface Contact {
  id: string;
  name: string;
  email: string;
  /** Dialling code without the number, e.g. "+65". */
  countryCode: string;
  phone: string;
  dob?: string;
  nric?: string;
  /** Absent means a normal contact. Only uploaded leads set this. */
  status?: ContactStatus;
  /** Targeting attributes, used by campaign criteria matching. */
  gender?: Gender;
  /** Investable cash in SGD. Deliberately not the same thing as annual income. */
  cashAmount?: number;
  /** Communication consent from the canonical mock_client record. */
  optInEmail?: boolean;
  optInSms?: boolean;
  label?: ContactLabel;
  bookmarked?: boolean;
  needsAttention?: boolean;
  notes?: string;
  meetings?: MeetingSummary[];
  profile?: ContactProfile;
  policies?: Policy[];
  /** ISO date of the last logged interaction. Drives recency judgement calls. */
  lastContacted?: string;
  source?: ContactSource;
  /** Transferred books only: whose book this came from, and when. */
  transferredFrom?: string;
  transferredOn?: string;
  /**
   * Transferred clients arrive owing the new advisor nothing — they do not
   * know the name. Stays false until the advisor has actually introduced
   * themselves, which is a different event from the last interaction logged
   * by the previous advisor.
   */
  introduced?: boolean;
}

export interface PipelineItem {
  id: string;
  caseId: number;
  contactId: string;
  contactName: string;
  contactLabel?: ContactLabel;
  stage: PipelineStage;
  closedOutcome?: ClosedOutcome;
  startDate: string;
  dueDate: string;
  description?: string;
  archived?: boolean;
}

export interface Task {
  id: string;
  /** Empty string means the task is not linked to a contact. */
  contactId: string;
  contactName: string;
  title: string;
  description: string;
  type: TaskType;
  startDate: string;
  dueDate: string;
  status: TaskStatus;
  /** Set when the task was raised out of a campaign. */
  campaignId?: string;
}

/* -------------------------------------------------------------------------- */
/* Roles and sessions                                                         */
/* -------------------------------------------------------------------------- */

/**
 * Marketing authors campaigns; advisors receive them. There is no auth behind
 * this — the sign-in screen simply picks which of the two the prototype runs as.
 */
export type Role = 'marketing' | 'advisor';

export interface Session {
  name: string;
  email: string;
  role: Role;
  /** Which advisor is signed in. Absent for Marketing, which owns no book. */
  advisorId?: string;
}

/* -------------------------------------------------------------------------- */
/* Distribution directory                                                     */
/* -------------------------------------------------------------------------- */

/**
 * A branch, agency group, or partner firm — the middle level between a channel
 * and an individual advisor.
 */
export interface AdvisorTeam {
  id: string;
  name: string;
  channel: string;
}

export interface Advisor {
  id: string;
  name: string;
  email: string;
  teamId: string;
}

/* -------------------------------------------------------------------------- */
/* Campaign targeting                                                         */
/* -------------------------------------------------------------------------- */

export type AgeGroup = 'under35' | '35to44' | '45to54' | '55to64' | '65plus';

export type Gender = 'male' | 'female';

/**
 * Bands over investable cash. The contact stores an actual amount and the band
 * is derived from it, so band filters and custom-amount filters read the same
 * underlying number and can never disagree.
 */
export type CashBand = 'under50k' | '50kTo250k' | '250kTo1m' | 'above1m';

/** Inclusive bounds. Either end may be left open. */
export interface NumericRange {
  min?: number;
  max?: number;
}

/**
 * An empty array means "no filter on this dimension". A populated one matches
 * any of its values, so criteria are OR within a dimension, AND across them.
 *
 * The custom ranges follow the same rule: a contact matches the age dimension
 * if they fall in a selected band OR inside the custom range. Setting neither
 * leaves the dimension unfiltered.
 */
export interface CampaignCriteria {
  ageGroups: AgeGroup[];
  ageRange?: NumericRange;
  genders: Gender[];
  cashBands: CashBand[];
  cashRange?: NumericRange;
}

/* -------------------------------------------------------------------------- */
/* Campaigns                                                                  */
/* -------------------------------------------------------------------------- */

/**
 * Who authored the campaign. Marketing campaigns are distributed to an advisor
 * channel; advisor campaigns are private to whoever made them and go nowhere.
 */
export type CampaignOrigin = 'marketing' | 'advisor';

/**
 * Where a campaign's audience comes from. The two never mix: a campaign either
 * works the existing book or an uploaded lead list, never both.
 */
export type CampaignAudienceSource = 'contacts' | 'leads';

/**
 * Survives the leads themselves. Removing a lead deletes its contact record,
 * so without these counters the campaign would lose all evidence it happened.
 */
export interface LeadStats {
  uploaded: number;
  added: number;
  removed: number;
}

/** What the advisor did with one targeted client on one campaign. */
export type CampaignActionType = 'pipeline' | 'task' | 'dismissed';

/**
 * One mass-send from the campaign module. Tracked separately from
 * `Campaign.actions` because emailing a client and putting them in the
 * pipeline are not mutually exclusive — the same person can be both.
 */
export interface CampaignEmail {
  id: string;
  sentAt: string;
  subject: string;
  fromName: string;
  fromEmail: string;
  recipientIds: string[];
  /** The sign-off as it stood at send time, so the log cannot drift. */
  signOff: string;
}

export interface Campaign {
  id: string;
  name: string;
  /** Backend lifecycle fields; PostgreSQL is authoritative. */
  status?: 'draft' | 'active' | 'paused' | 'completed';
  startDate?: string;
  endDate?: string;
  /** Marketing's internal brief — what the campaign is and who it is for. */
  description: string;
  /** Client-facing copy the advisor adapts before sending. */
  clientMessage: string;
  /** Small data URL persisted with this synthetic prototype campaign. */
  bannerDataUrl?: string;
  origin: CampaignOrigin;
  audienceSource: CampaignAudienceSource;
  /**
   * Distribution channel. Absent on advisor-created campaigns, which are
   * private to their author and routed nowhere.
   */
  channel?: string;
  /** Teams within the channel. Empty means every team in it. */
  teamIds: string[];
  /** Named advisors within the selected teams. Empty means all of them. */
  advisorIds: string[];
  /** Set on advisor-authored campaigns so only their author sees them. */
  createdByAdvisorId?: string;
  /** Contact campaigns only. Ignored entirely when audienceSource is 'leads'. */
  criteria: CampaignCriteria;
  /** Hand-picked additions on top of the criteria match. */
  includeIds: string[];
  /** Criteria matches the advisor explicitly dropped. */
  excludeIds: string[];
  /** Lead campaigns only. Holds pending and promoted leads; removed ones are dropped. */
  leadIds: string[];
  /** Persisted campaign-specific lead records returned by the backend. */
  leadContacts?: Contact[];
  leadStats: LeadStats;
  createdBy: string;
  createdAt: string;
  /** Advisor decisions, keyed by contact id. */
  actions: Record<string, CampaignActionType>;
  /** Every mass-send made from this campaign, newest first. */
  emailLog: CampaignEmail[];
}
