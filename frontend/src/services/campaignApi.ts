import { Campaign, Contact, Session } from '../types';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');

function apiUrl(path: string, session: Session): string {
  const url = new URL(`${API_BASE_URL}${path}`, window.location.origin);
  url.searchParams.set('role', session.role);
  if (session.advisorId) url.searchParams.set('fa_id', session.advisorId);
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
    throw new Error(detail ?? `Campaign request failed (${response.status}).`);
  }
  return response.json() as Promise<T>;
}

export function listCampaigns(session: Session, signal?: AbortSignal): Promise<Campaign[]> {
  return request<Campaign[]>(apiUrl('/api/campaigns', session), { signal });
}

export function createCampaign(
  campaign: Campaign,
  leadContacts: Contact[],
  session: Session,
): Promise<Campaign> {
  return request<Campaign>(apiUrl('/api/campaigns', session), {
    method: 'POST',
    body: JSON.stringify({ ...campaign, leadContacts }),
  });
}

export function updateCampaignState(campaign: Campaign, session: Session): Promise<Campaign> {
  return request<Campaign>(apiUrl(`/api/campaigns/${encodeURIComponent(campaign.id)}/state`, session), {
    method: 'PATCH',
    body: JSON.stringify({
      includeIds: campaign.includeIds,
      excludeIds: campaign.excludeIds,
      leadIds: campaign.leadIds,
      leadStats: campaign.leadStats,
      actions: campaign.actions,
      emailLog: campaign.emailLog,
      leadContacts: campaign.leadContacts ?? [],
    }),
  });
}
