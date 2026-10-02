import { Contact } from '../types';
import { ColumnMatch, ContactField } from '../services/ai';
import { createCellReader, ParsedSheet } from './spreadsheet';

/**
 * ============================================================================
 * LEAD IMPORT
 * ============================================================================
 * Canvassing and roadshow lists are messy by nature — half-legible names, a
 * phone number or an email but rarely both, and plenty of people with no real
 * intention of ever replying. So the bar here is deliberately lower than the
 * Contacts wizard's: a name, plus *some* way to reach them.
 *
 * Nothing imported here becomes a real contact. Every row lands as
 * `status: 'lead'` and stays invisible outside the campaign module until an
 * advisor promotes it.
 */

export interface LeadImport {
  leads: Omit<Contact, 'id'>[];
  /** Rows dropped for having no name, or no email and no phone. */
  skipped: number;
  total: number;
}

/**
 * Name is required, and at least one of email or phone. A lead with neither is
 * not a lead — there is no way to act on it.
 */
export function buildLeadsFromSheet(sheet: ParsedSheet, matches: ColumnMatch[]): LeadImport {
  const cell = createCellReader<ContactField>(matches);

  const leads: Omit<Contact, 'id'>[] = [];
  let skipped = 0;

  for (const row of sheet.rows) {
    const name = cell(row, 'name');
    const email = cell(row, 'email');
    const phone = cell(row, 'phone').replace(/[\s-]/g, '');

    if (!name || (!email && !phone)) {
      skipped++;
      continue;
    }

    const code = cell(row, 'countryCode');

    leads.push({
      name,
      // Kept even when it fails validation: a typo'd address is still the only
      // thing the advisor has, and the email flow excludes unusable ones anyway.
      email,
      countryCode: code ? (code.startsWith('+') ? code : `+${code}`) : '+65',
      phone,
      status: 'lead',
      // No label yet. They are not a prospect until someone decides they are.
    });
  }

  return { leads, skipped, total: sheet.rows.length };
}
