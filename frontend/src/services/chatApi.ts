export interface ChatSession {
  session_id: string;
  timestamp: string;
  session_title: string;
}

export interface ChatMessage {
  timestamp: string;
  user: boolean | string;
  message_content: string;
}

interface NewChatSession {
  session_id: string;
  timestamp: string;
}

export interface QueryResponse {
  user: boolean | string;
  timestamp: string;
  ai_answer: string;
  campaignDraft?: CampaignDraftArtifact | null;
}

export type CampaignAgeGroup = 'under35' | '35to44' | '45to54' | '55to64' | '65plus';
export type CampaignGender = 'male' | 'female';
export type CampaignCashBand = 'under50k' | '50kTo250k' | '250kTo1m' | 'above1m';

export interface CampaignDraftArtifact {
  type: 'campaign_draft';
  data_source: 'ai_generated';
  draftId: string;
  objective: string;
  referencesUsed: Array<{ referenceId: string; version: number }>;
  draft: {
    name: string;
    description: string;
    clientMessage: string;
    criteria: {
      ageGroups: CampaignAgeGroup[];
      genders: CampaignGender[];
      cashBands: CampaignCashBand[];
    };
    targetDemographicSummary: string;
    rationale: Record<'ageGroups' | 'genders' | 'cashBands', string>;
    assumptions: string[];
    disclaimer: string;
  };
  revision: number;
  status: 'generated' | 'reviewed' | 'confirmed' | 'rejected' | 'expired';
  changedFields: Array<
    | 'name'
    | 'description'
    | 'clientMessage'
    | 'ageGroups'
    | 'genders'
    | 'cashBands'
    | 'targetDemographicSummary'
  >;
  validation: {
    schema_valid: true;
    policy_valid: true;
    warnings: string[];
  };
  requires_adviser_review: true;
  created: false;
}

export class ChatApiError extends Error {
  readonly status: number | null;

  constructor(message: string, status: number | null = null, options?: ErrorOptions) {
    super(message, options);
    this.name = 'ChatApiError';
    this.status = status;
  }
}

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');

function apiUrl(path: string, query?: Record<string, string>): string {
  const url = new URL(`${API_BASE_URL}${path}`, window.location.origin);
  for (const [key, value] of Object.entries(query ?? {})) {
    url.searchParams.set(key, value);
  }
  return API_BASE_URL ? url.toString() : `${url.pathname}${url.search}`;
}

function errorMessage(payload: unknown, status: number): string {
  if (typeof payload === 'object' && payload !== null && 'detail' in payload) {
    const detail = (payload as { detail: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      const messages = detail.flatMap((item) => {
        if (typeof item !== 'object' || item === null || !('msg' in item)) return [];
        const message = (item as { msg: unknown }).msg;
        return typeof message === 'string' ? [message] : [];
      });
      if (messages.length > 0) return messages.join('. ');
    }
  }

  if (status === 429) return 'PULSE is receiving too many requests. Please try again shortly.';
  if (status === 502) return 'PULSE could not get a response from the AI provider.';
  if (status === 503) return 'PULSE is not fully configured or its data service is unavailable.';
  if (status === 504) return 'The AI provider took too long to respond. Please try again.';
  return `PULSE request failed (${status}).`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set('Accept', 'application/json');
  if (init?.body) headers.set('Content-Type', 'application/json');

  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers,
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause;
    throw new ChatApiError(
      'Unable to reach the PULSE service. Check that the backend is running and try again.',
      null,
      { cause },
    );
  }

  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null);
    throw new ChatApiError(errorMessage(payload, response.status), response.status);
  }

  return response.json() as Promise<T>;
}

export function listChatSessions(faId: string, signal?: AbortSignal): Promise<ChatSession[]> {
  return request<ChatSession[]>(apiUrl('/api/chat/sessions', { fa_id: faId }), { signal });
}

export async function createChatSession(
  faId: string,
  signal?: AbortSignal,
): Promise<ChatSession> {
  const session = await request<NewChatSession>(
    apiUrl('/api/chat/new', { fa_id: faId }),
    { method: 'POST', signal },
  );
  return { ...session, session_title: 'New chat' };
}

export function getChatHistory(
  sessionId: string,
  signal?: AbortSignal,
): Promise<ChatMessage[]> {
  return request<ChatMessage[]>(apiUrl('/api/chat/history', { session_id: sessionId }), {
    signal,
  });
}

export function sendChatMessage(
  faId: string,
  sessionId: string,
  messageContent: string,
  signal?: AbortSignal,
  campaignId?: string,
): Promise<QueryResponse> {
  return request<QueryResponse>(apiUrl('/api/chat/query'), {
    method: 'POST',
    signal,
    body: JSON.stringify({
      fa_id: faId,
      session_id: sessionId,
      message_content: messageContent,
      campaign_id: campaignId,
    }),
  });
}
