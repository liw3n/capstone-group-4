import { CampaignEmail, Contact, Session } from '../types';

/**
 * ============================================================================
 * CAMPAIGN EMAIL COMPOSITION
 * ============================================================================
 * Nothing here sends anything. There is no mail transport, no backend, and no
 * network call in this app — the send flow records what *would* have gone out
 * and the UI says so plainly.
 *
 * The point of this file is that the confirmation preview and the recorded
 * send are built by the same function. If they were composed separately, the
 * advisor could approve one thing and have another logged.
 */

/** Loose on purpose — import data is messy and blanks matter more than edge cases. */
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** The one email rule in the app — form validation and campaign eligibility share it. */
export function isValidEmail(value: string): boolean {
  return EMAIL_RE.test(value.trim());
}

export function hasUsableEmail(contact: Contact): boolean {
  return isValidEmail(contact.email ?? '');
}

export const SIGN_OFF_TOKENS = ['{{advisor_name}}', '{{advisor_email}}', '{{client_name}}'];

/** Tokens rather than baked-in values, so one template survives a role switch. */
export const DEFAULT_SIGN_OFF = [
  'Kind regards,',
  '',
  '{{advisor_name}}',
  'Financial Advisor · MyWealth',
  '{{advisor_email}}',
].join('\n');

export interface ComposeInput {
  contact: Contact;
  clientMessage: string;
  signOff: string;
  session: Session;
}

export function firstName(contact: Contact): string {
  return contact.name.split(' ')[0];
}

/**
 * Everyone a campaign has already been emailed to, across every send. Four
 * screens ask this question and they must all agree on the answer, so the
 * flattening lives here rather than being rewritten at each call site.
 */
export function emailedContactIds(emailLog: CampaignEmail[]): Set<string> {
  return new Set(emailLog.flatMap((entry) => entry.recipientIds));
}

function fillTokens(template: string, contact: Contact, session: Session): string {
  return template
    .replaceAll('{{advisor_name}}', session.name)
    .replaceAll('{{advisor_email}}', session.email)
    .replaceAll('{{client_name}}', contact.name);
}

/**
 * Greeting + marketing's client messaging, verbatim + the advisor's sign-off.
 * The body is deliberately marketing's copy rather than the AI-personalised
 * draft: one campaign message goes to everyone, and the per-client drafts on
 * the table are for one-to-one follow-up.
 */
export function composeEmailBody({
  contact,
  clientMessage,
  signOff,
  session,
}: ComposeInput): string {
  return [
    `Dear ${firstName(contact)},`,
    '',
    clientMessage.trim(),
    '',
    fillTokens(signOff, contact, session).trim(),
  ].join('\n');
}
