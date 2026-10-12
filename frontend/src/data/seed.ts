/**
 * Fixed prototype date shared by deterministic campaign targeting and date
 * formatting. CRM contact records are not seeded here; they come from
 * PostgreSQL `mock_client` through `/api/contacts`.
 */
export const TODAY_ISO = '2026-08-26';

/** Format a local Date as YYYY-MM-DD without a UTC day shift. */
export function toISODate(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}
