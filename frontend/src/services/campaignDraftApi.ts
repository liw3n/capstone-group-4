import {
  CampaignAgeGroup,
  CampaignCashBand,
  CampaignDraftArtifact,
  CampaignDraftField,
  CampaignGender,
} from './chatApi';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');

export type CampaignDraftChanges = Partial<{
  name: string;
  description: string;
  clientMessage: string;
  ageGroups: CampaignAgeGroup[];
  genders: CampaignGender[];
  cashBands: CampaignCashBand[];
  targetDemographicSummary: string;
}>;

export class CampaignDraftApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'CampaignDraftApiError';
    this.status = status;
  }
}

function apiUrl(path: string, query?: Record<string, string>): string {
  const url = new URL(`${API_BASE_URL}${path}`, window.location.origin);
  for (const [key, value] of Object.entries(query ?? {})) {
    url.searchParams.set(key, value);
  }
  return API_BASE_URL ? url.toString() : `${url.pathname}${url.search}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set('Accept', 'application/json');
  if (init?.body) headers.set('Content-Type', 'application/json');
  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    const detail = typeof payload?.detail === 'string'
      ? payload.detail
      : `Campaign draft request failed (${response.status}).`;
    throw new CampaignDraftApiError(detail, response.status);
  }
  return response.json() as Promise<T>;
}

export function getCampaignDraft(
  advisorId: string,
  sessionId: string,
  draftId: string,
  signal?: AbortSignal,
): Promise<CampaignDraftArtifact> {
  return request<CampaignDraftArtifact>(
    apiUrl(`/api/campaign-drafts/${encodeURIComponent(draftId)}`, {
      fa_id: advisorId,
      session_id: sessionId,
    }),
    { signal },
  );
}

export function updateCampaignDraft(
  advisorId: string,
  sessionId: string,
  current: CampaignDraftArtifact,
  changes: CampaignDraftChanges,
  signal?: AbortSignal,
): Promise<CampaignDraftArtifact> {
  return request<CampaignDraftArtifact>(
    apiUrl(`/api/campaign-drafts/${encodeURIComponent(current.draftId)}`),
    {
      method: 'PATCH',
      signal,
      body: JSON.stringify({
        fa_id: advisorId,
        session_id: sessionId,
        expectedRevision: current.revision,
        changes,
      }),
    },
  );
}

export function regenerateCampaignDraft(
  advisorId: string,
  sessionId: string,
  current: CampaignDraftArtifact,
  fields: CampaignDraftField[],
  instruction: string,
  signal?: AbortSignal,
): Promise<CampaignDraftArtifact> {
  return request<CampaignDraftArtifact>(
    apiUrl(`/api/campaign-drafts/${encodeURIComponent(current.draftId)}/regenerate`),
    {
      method: 'POST',
      signal,
      body: JSON.stringify({
        fa_id: advisorId,
        session_id: sessionId,
        expectedRevision: current.revision,
        fields,
        instruction,
      }),
    },
  );
}
