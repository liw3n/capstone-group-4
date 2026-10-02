import { TODAY_ISO, toISODate } from '../data/seed';

const TODAY = new Date(`${TODAY_ISO}T00:00:00`);

/** Placeholder for empty cells. Import data arrives with gaps everywhere. */
export const EMPTY = '–';

/**
 * Values such as "\N" leak in from CSV/database exports. Treat them as blank
 * rather than rendering the artifact to the advisor.
 */
export function display(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return EMPTY;
  const s = String(value).trim();
  if (!s || s === '\\N' || s === 'null' || s === 'undefined') return EMPTY;
  return s;
}

export function yesNo(value: boolean | undefined): string {
  if (value === undefined) return EMPTY;
  return value ? 'Yes' : 'No';
}

export function daysUntil(dueDate: string): number {
  const due = new Date(`${dueDate}T00:00:00`);
  return Math.round((due.getTime() - TODAY.getTime()) / 86_400_000);
}

/** "710 days overdue" / "Due today" / "in 12 days" */
export function dueLabel(dueDate: string): string {
  const days = daysUntil(dueDate);
  if (days < 0) return `${Math.abs(days)} day${Math.abs(days) === 1 ? '' : 's'} overdue`;
  if (days === 0) return 'Due today';
  if (days === 1) return 'in 1 day';
  return `in ${days} days`;
}

export function isOverdue(dueDate: string): boolean {
  return daysUntil(dueDate) < 0;
}

/** "Aug 26, 2026" */
export function formatDate(value: string | undefined): string {
  if (!value) return EMPTY;
  const d = new Date(`${value}T00:00:00`);
  if (Number.isNaN(d.getTime())) return display(value);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

/** "19 Jun 2026" — used on the engagement timeline */
export function formatTimelineDate(value: string): string {
  const d = new Date(`${value}T00:00:00`);
  if (Number.isNaN(d.getTime())) return display(value);
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

export function todayISO(): string {
  return TODAY_ISO;
}

export function addDaysISO(base: string, days: number): string {
  const d = new Date(`${base}T00:00:00`);
  d.setDate(d.getDate() + days);
  return toISODate(d);
}

export function initials(name: string): string {
  return name
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((n) => n[0])
    .join('')
    .toUpperCase();
}

export function newId(): string {
  return Math.random().toString(36).slice(2, 11);
}

/** "+65 92988104", collapsing to the code alone when no number is on file. */
export function formatPhone(contact: { countryCode?: string; phone?: string }): string {
  const code = (contact.countryCode ?? '').trim();
  const number = (contact.phone ?? '').trim();
  if (!number) return EMPTY;
  return code ? `${code} ${number}` : number;
}
