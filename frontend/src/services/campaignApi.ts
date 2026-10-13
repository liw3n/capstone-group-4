import { Campaign, Contact, Session } from '../types';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');

export type EngagementStatus = 0 | 1 | 2;

export interface StatusUpdateResponse {
  campaign_id: string;
  contact_id: string;
  fa_id: string;
  status: EngagementStatus;
}

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

export function updateCampaignEngagementStatus(
  campaignId: string,
  contactId: string,
  status: EngagementStatus,
  session: Session,
): Promise<StatusUpdateResponse> {
  if (!session.advisorId) {
    throw new Error('An adviser session is required to update campaign status.');
  }

  const url = new URL(
    `${API_BASE_URL}/api/campaign/update-engagement-status`,
    window.location.origin,
  );
  url.searchParams.set('fa_id', session.advisorId);
  const requestUrl = API_BASE_URL ? url.toString() : `${url.pathname}${url.search}`;

  return request<StatusUpdateResponse>(requestUrl, {
    method: 'POST',
    body: JSON.stringify({
      campaign_id: campaignId,
      contact_id: contactId,
      status,
    }),
  });
}

export async function getCampaignEngagementStatus(
  campaignId: string,
  contactId: string,
  session: Session,
): Promise<EngagementStatus | null> {
  if (!session.advisorId) {
    throw new Error('An adviser session is required to load campaign status.');
  }

  const url = new URL(
    `${API_BASE_URL}/api/campaigns/engagement-status`,
    window.location.origin,
  );
  url.searchParams.set('campaign_id', campaignId);
  url.searchParams.set('contact_id', contactId);
  url.searchParams.set('fa_id', session.advisorId);
  const requestUrl = API_BASE_URL ? url.toString() : `${url.pathname}${url.search}`;
  const response = await fetch(requestUrl, { headers: { Accept: 'application/json' } });

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    const detail = typeof payload?.detail === 'string' ? payload.detail : null;
    throw new Error(detail ?? `Campaign request failed (${response.status}).`);
  }

  const result = (await response.json()) as StatusUpdateResponse | null;
  return result?.status ?? null;
}
