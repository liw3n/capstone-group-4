import { Contact, Session } from '../types';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');

function contactUrl(path: string, session: Session): string {
  if (!session.advisorId) throw new Error('An adviser session is required for contacts.');
  const url = new URL(`${API_BASE_URL}${path}`, window.location.origin);
  url.searchParams.set('fa_id', session.advisorId);
  return API_BASE_URL ? url.toString() : `${url.pathname}${url.search}`;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set('Accept', 'application/json');
  if (init?.body) headers.set('Content-Type', 'application/json');
  const response = await fetch(url, { ...init, headers });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    const detail = typeof payload?.detail === 'string' ? payload.detail : null;
    throw new Error(detail ?? `Contact request failed (${response.status}).`);
  }
  return response.json() as Promise<T>;
}

export function listContacts(session: Session, signal?: AbortSignal): Promise<Contact[]> {
  return request<Contact[]>(contactUrl('/api/contacts', session), { signal });
}

export function createContact(contact: Contact, session: Session): Promise<Contact> {
  return request<Contact>(contactUrl('/api/contacts', session), {
    method: 'POST',
    body: JSON.stringify(contact),
  });
}

export function replaceContact(contact: Contact, session: Session): Promise<Contact> {
  return request<Contact>(
    contactUrl(`/api/contacts/${encodeURIComponent(contact.id)}`, session),
    { method: 'PUT', body: JSON.stringify(contact) },
  );
}
