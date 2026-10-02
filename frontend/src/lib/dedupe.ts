import { Contact } from '../types';

/**
 * Duplicate detection for incoming names.
 *
 * Identifiers are checked strongest first. NRIC leads because it is the only
 * one of the three that actually identifies a person: emails get shared and
 * recycled within a household, and phone numbers get reassigned. A name is not
 * an identifier at all — two different Tan Wei Mings is an ordinary Tuesday —
 * so it is deliberately not matched on.
 *
 * Transferred books and roadshow lists are where duplicates come from: the same
 * person turns up at two roadshows, or a client transferred to you was already
 * on your book as a referral.
 */

export type MatchedOn = 'nric' | 'email' | 'phone';

export interface DuplicateHit {
  contact: Contact;
  matchedOn: MatchedOn;
}

export interface Identifiable {
  nric?: string;
  email?: string;
  phone?: string;
}

function normaliseNric(value: string | undefined): string {
  return (value ?? '').trim().toUpperCase();
}

function normaliseEmail(value: string | undefined): string {
  return (value ?? '').trim().toLowerCase();
}

/**
 * Strips everything but digits so "+65 9123 4567", "91234567" and "9123-4567"
 * compare equal. Anything under 7 digits is treated as unusable rather than
 * matched loosely.
 */
function normalisePhone(value: string | undefined): string {
  const digits = (value ?? '').replace(/\D/g, '');
  return digits.length >= 7 ? digits.slice(-8) : '';
}

export function findDuplicate(contacts: Contact[], candidate: Identifiable): DuplicateHit | null {
  const nric = normaliseNric(candidate.nric);
  const email = normaliseEmail(candidate.email);
  const phone = normalisePhone(candidate.phone);

  if (nric) {
    const hit = contacts.find((c) => normaliseNric(c.nric) === nric);
    if (hit) return { contact: hit, matchedOn: 'nric' };
  }

  if (email) {
    const hit = contacts.find((c) => normaliseEmail(c.email) === email);
    if (hit) return { contact: hit, matchedOn: 'email' };
  }

  if (phone) {
    const hit = contacts.find((c) => normalisePhone(c.phone) === phone);
    if (hit) return { contact: hit, matchedOn: 'phone' };
  }

  return null;
}

/**
 * Dedupes a batch against the book AND against itself, so a spreadsheet
 * containing the same person twice only yields one row.
 */
export function partitionIncoming<T extends Identifiable>(
  contacts: Contact[],
  incoming: T[],
): { fresh: T[]; duplicates: { row: T; hit: DuplicateHit }[] } {
  const fresh: T[] = [];
  const duplicates: { row: T; hit: DuplicateHit }[] = [];

  // Grows as the batch is walked, so later rows collide with earlier ones.
  const seen: Contact[] = [...contacts];

  for (const row of incoming) {
    const hit = findDuplicate(seen, row);
    if (hit) {
      duplicates.push({ row, hit });
      continue;
    }

    fresh.push(row);
    seen.push({
      id: '',
      name: '',
      email: row.email ?? '',
      countryCode: '',
      phone: row.phone ?? '',
      nric: row.nric,
    });
  }

  return { fresh, duplicates };
}
