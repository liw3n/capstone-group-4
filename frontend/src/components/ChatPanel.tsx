import {
  CSSProperties,
  FormEvent,
  PointerEvent as ReactPointerEvent,
  useEffect,
  useRef,
  useState,
} from 'react';
import { AnimatePresence, motion } from 'motion/react';
import {
  Bot,
  FileText,
  Maximize2,
  MessageCircle,
  Minimize2,
  Plus,
  Send,
  X,
} from 'lucide-react';
import AssistantMessage from './AssistantMessage';
import {
  CHAT_PANEL_SIZE_STORAGE_KEY,
  ChatPanelSize,
  DEFAULT_CHAT_PANEL_SIZE,
  clampChatPanelSize,
  parseStoredChatPanelSize,
  resizeFromTopLeft,
} from '../lib/chatPanelSize';
import {
  ChatMessage,
  ChatSession,
  CampaignDraftArtifact,
  createChatSession,
  getChatHistory,
  listChatSessions,
  sendChatMessage,
} from '../services/chatApi';
import { getCampaignDraft } from '../services/campaignDraftApi';

interface ChatPanelProps {
  advisorId: string;
  onReviewCampaignDraft?: (draft: CampaignDraftArtifact, sessionId: string) => void;
}

type ErrorSource = 'sessions' | 'history' | 'create' | 'send';

interface PanelError {
  message: string;
  source: ErrorSource;
}

function isAbortError(reason: unknown): boolean {
  return reason instanceof DOMException && reason.name === 'AbortError';
}

function errorMessage(reason: unknown, fallback: string): string {
  return reason instanceof Error ? reason.message : fallback;
}

function formatSessionTimestamp(timestamp: string): string {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(date);
}

function readViewport(): ChatPanelSize {
  if (typeof window === 'undefined') return DEFAULT_CHAT_PANEL_SIZE;
  return { width: window.innerWidth, height: window.innerHeight };
}

function readStoredPanelSize(): ChatPanelSize {
  if (typeof window === 'undefined') return DEFAULT_CHAT_PANEL_SIZE;
  try {
    return (
      parseStoredChatPanelSize(window.localStorage.getItem(CHAT_PANEL_SIZE_STORAGE_KEY)) ??
      DEFAULT_CHAT_PANEL_SIZE
    );
  } catch {
    return DEFAULT_CHAT_PANEL_SIZE;
  }
}

function storePanelSize(size: ChatPanelSize) {
  try {
    window.localStorage.setItem(CHAT_PANEL_SIZE_STORAGE_KEY, JSON.stringify(size));
  } catch {
    // Size persistence is a convenience; ignore blocked storage.
  }
}

function titleFromMessage(message: string): string {
  return `${message.split(/\s+/).slice(0, 5).join(' ')}...`;
}

export default function ChatPanel({
  advisorId,
  onReviewCampaignDraft,
}: ChatPanelProps) {
  const [open, setOpen] = useState(false);
  const [panelSize, setPanelSize] = useState<ChatPanelSize>(readStoredPanelSize);
  const [maximized, setMaximized] = useState(false);
  const [viewport, setViewport] = useState<ChatPanelSize>(readViewport);
  const resizeStart = useRef<{ x: number; y: number; size: ChatPanelSize } | null>(null);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [latestCampaignDraft, setLatestCampaignDraft] =
    useState<CampaignDraftArtifact | null>(null);
  const [draft, setDraft] = useState('');
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [creatingSession, setCreatingSession] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<PanelError | null>(null);
  const [sessionLoadAttempt, setSessionLoadAttempt] = useState(0);
  const [historyLoadAttempt, setHistoryLoadAttempt] = useState(0);
  const loadedForAdvisor = useRef<string | null>(null);
  const skipHistoryForSession = useRef<string | null>(null);
  const messagesEnd = useRef<HTMLDivElement | null>(null);
  const createRequest = useRef<AbortController | null>(null);
  const sendRequest = useRef<AbortController | null>(null);
  const activeCampaignDraftId = sessions.find(
    (session) => session.session_id === activeSessionId,
  )?.active_campaign_draft_id;

  useEffect(() => {
    if (!open) return;
    const handleResize = () => setViewport(readViewport());
    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [open]);

  const effectivePanelSize = maximized
    ? clampChatPanelSize({ width: Infinity, height: Infinity }, viewport)
    : clampChatPanelSize(panelSize, viewport);
  const panelStyle = {
    '--chat-panel-width': `${effectivePanelSize.width}px`,
    '--chat-panel-height': `${effectivePanelSize.height}px`,
  } as CSSProperties;

  const startResize = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    resizeStart.current = { x: event.clientX, y: event.clientY, size: effectivePanelSize };
    setMaximized(false);
  };

  const continueResize = (event: ReactPointerEvent<HTMLDivElement>) => {
    const start = resizeStart.current;
    if (!start) return;
    setPanelSize(
      resizeFromTopLeft(
        start.size,
        event.clientX - start.x,
        event.clientY - start.y,
        readViewport(),
      ),
    );
  };

  const endResize = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!resizeStart.current) return;
    resizeStart.current = null;
    event.currentTarget.releasePointerCapture(event.pointerId);
    setPanelSize((size) => {
      storePanelSize(size);
      return size;
    });
  };

  const resetPanelSize = () => {
    setMaximized(false);
    setPanelSize(DEFAULT_CHAT_PANEL_SIZE);
    storePanelSize(DEFAULT_CHAT_PANEL_SIZE);
  };

  useEffect(() => {
    loadedForAdvisor.current = null;
    skipHistoryForSession.current = null;
    createRequest.current?.abort();
    sendRequest.current?.abort();
    setSessions([]);
    setActiveSessionId(null);
    setMessages([]);
    setLatestCampaignDraft(null);
    setDraft('');
    setError(null);
    setLoadingSessions(false);
    setLoadingHistory(false);
    setCreatingSession(false);
    setSending(false);
  }, [advisorId]);

  useEffect(() => {
    return () => {
      createRequest.current?.abort();
      sendRequest.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (!open || loadedForAdvisor.current === advisorId) return;

    let cancelled = false;
    setLoadingSessions(true);
    setError((current) => (current?.source === 'sessions' ? null : current));
    const controller = new AbortController();
    listChatSessions(advisorId, controller.signal)
      .then((nextSessions) => {
        if (cancelled) return;
        setSessions(nextSessions);
        setActiveSessionId(nextSessions[0]?.session_id ?? null);
        loadedForAdvisor.current = advisorId;
      })
      .catch((reason: unknown) => {
        if (!cancelled && !isAbortError(reason)) {
          setError({ message: errorMessage(reason, 'Unable to load chats'), source: 'sessions' });
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingSessions(false);
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [advisorId, open, sessionLoadAttempt]);

  useEffect(() => {
    if (!open || !activeSessionId) {
      setMessages([]);
      setLatestCampaignDraft(null);
      setLoadingHistory(false);
      return;
    }

    if (skipHistoryForSession.current === activeSessionId) {
      skipHistoryForSession.current = null;
      setLoadingHistory(false);
      return;
    }

    let cancelled = false;
    setLoadingHistory(true);
    setLatestCampaignDraft(null);
    setError((current) => (current?.source === 'history' ? null : current));
    const controller = new AbortController();
    Promise.all([
      getChatHistory(activeSessionId, controller.signal),
      activeCampaignDraftId
        ? getCampaignDraft(
          advisorId,
          activeSessionId,
          activeCampaignDraftId,
          controller.signal,
        )
        : Promise.resolve(null),
    ])
      .then(([history, campaignDraft]) => {
        if (!cancelled) {
          setMessages(history);
          setLatestCampaignDraft(campaignDraft);
        }
      })
      .catch((reason: unknown) => {
        if (!cancelled && !isAbortError(reason)) {
          setError({
            message: errorMessage(reason, 'Unable to load history'),
            source: 'history',
          });
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingHistory(false);
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [activeCampaignDraftId, activeSessionId, advisorId, historyLoadAttempt, open]);

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, sending]);

  const startNewChat = async (): Promise<ChatSession | null> => {
    if (creatingSession) return null;
    const requestAdvisorId = advisorId;
    const controller = new AbortController();
    createRequest.current?.abort();
    createRequest.current = controller;
    setCreatingSession(true);
    setError(null);
    try {
      const session = await createChatSession(requestAdvisorId, controller.signal);
      if (controller.signal.aborted) return null;
      setSessions((current) => [session, ...current]);
      skipHistoryForSession.current = session.session_id;
      setActiveSessionId(session.session_id);
      setMessages([]);
      setLatestCampaignDraft(null);
      return session;
    } catch (reason) {
      if (!isAbortError(reason)) {
        setError({
          message: errorMessage(reason, 'Unable to create a chat'),
          source: 'create',
        });
      }
      return null;
    } finally {
      if (createRequest.current === controller) {
        createRequest.current = null;
        setCreatingSession(false);
      }
    }
  };

  const submitMessage = async (event: FormEvent) => {
    event.preventDefault();
    const content = draft.trim();
    if (!content || sending) return;

    let sessionId = activeSessionId;
    if (!sessionId) {
      const session = await startNewChat();
      if (!session) return;
      sessionId = session.session_id;
    }

    const optimisticMessage: ChatMessage = {
      timestamp: new Date().toISOString(),
      user: advisorId,
      message_content: content,
    };
    setMessages((current) => [...current, optimisticMessage]);
    setDraft('');
    setSending(true);
    setError(null);
    const controller = new AbortController();
    sendRequest.current?.abort();
    sendRequest.current = controller;

    try {
      const response = await sendChatMessage(
        advisorId,
        sessionId,
        content,
        controller.signal,
      );
      if (controller.signal.aborted) return;
      setSessions((current) =>
        current.map((session) =>
          session.session_id === sessionId && session.session_title === 'New chat'
            ? { ...session, session_title: titleFromMessage(content) }
            : session,
        ),
      );
      setMessages((current) => [
        ...current,
        {
          timestamp: response.timestamp,
          user: false,
          message_content: response.ai_answer,
        },
      ]);
      if (response.campaignDraft) {
        setLatestCampaignDraft(response.campaignDraft);
        setSessions((current) => current.map((session) =>
          session.session_id === sessionId
            ? { ...session, active_campaign_draft_id: response.campaignDraft?.draftId }
            : session,
        ));
      }
    } catch (reason) {
      if (!isAbortError(reason)) {
        setMessages((current) => current.filter((message) => message !== optimisticMessage));
        setDraft((current) => current || content);
        setError({
          message: errorMessage(reason, 'Unable to send your message'),
          source: 'send',
        });
      }
    } finally {
      if (sendRequest.current === controller) {
        sendRequest.current = null;
        setSending(false);
      }
    }
  };

  const retryLoad = () => {
    if (error?.source === 'sessions') {
      loadedForAdvisor.current = null;
      setSessionLoadAttempt((attempt) => attempt + 1);
    } else if (error?.source === 'history') {
      setHistoryLoadAttempt((attempt) => attempt + 1);
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Open PULSE assistant"
        className="fixed bottom-5 right-5 z-40 flex h-12 w-12 items-center justify-center rounded-full bg-accent text-white shadow-lg transition-transform hover:scale-105 hover:bg-accent-hover focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2"
      >
        <MessageCircle size={21} />
      </button>

      <AnimatePresence>
        {open && (
          <motion.section
            role="dialog"
            aria-label="PULSE assistant"
            initial={{ opacity: 0, y: 12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.98 }}
            transition={{ duration: 0.16 }}
            style={panelStyle}
            className="fixed inset-x-3 bottom-3 z-50 flex h-[min(640px,calc(100vh-24px))] flex-col overflow-hidden rounded-xl border border-line bg-white shadow-2xl sm:inset-x-auto sm:bottom-5 sm:right-5 sm:h-[var(--chat-panel-height)] sm:w-[var(--chat-panel-width)]"
          >
            <div
              role="separator"
              aria-label="Resize PULSE assistant"
              title="Drag to resize · double-click to reset"
              onPointerDown={startResize}
              onPointerMove={continueResize}
              onPointerUp={endResize}
              onPointerCancel={endResize}
              onDoubleClick={resetPanelSize}
              className="absolute left-0 top-0 z-10 hidden h-4 w-4 cursor-nwse-resize touch-none sm:block"
            >
              <span className="absolute left-1 top-1 h-2 w-2 rounded-tl-sm border-l-2 border-t-2 border-white/60" />
            </div>
            <header className="flex items-center justify-between border-b border-line bg-ink px-4 py-3 text-white">
              <div className="flex items-center gap-2.5">
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-white/15">
                  <Bot size={17} />
                </span>
                <div>
                  <h2 className="text-[13px] font-semibold">PULSE assistant</h2>
                  <p className="text-[11px] text-white/65">Campaign and adviser support</p>
                </div>
              </div>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => setMaximized((value) => !value)}
                  aria-label={maximized ? 'Restore PULSE assistant size' : 'Expand PULSE assistant'}
                  title={maximized ? 'Restore size' : 'Expand'}
                  className="hidden rounded p-1.5 text-white/70 hover:bg-white/10 hover:text-white sm:block"
                >
                  {maximized ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
                </button>
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  aria-label="Close PULSE assistant"
                  className="rounded p-1.5 text-white/70 hover:bg-white/10 hover:text-white"
                >
                  <X size={17} />
                </button>
              </div>
            </header>

            <div className="border-b border-line-soft bg-link-soft px-3 py-2 text-[12px] text-body">
              <p className="font-medium">
                Name a campaign in chat to request client recommendations.
              </p>
            </div>

            <div className="flex items-center gap-2 border-b border-line-soft px-3 py-2">
              <select
                aria-label="Chat session"
                value={activeSessionId ?? ''}
                onChange={(event) => {
                  setError(null);
                  setActiveSessionId(event.target.value || null);
                }}
                disabled={
                  loadingSessions || creatingSession || sending || sessions.length === 0
                }
                className="min-w-0 flex-1 rounded-md border border-line bg-white px-2.5 py-1.5 text-[12px] text-body outline-none focus:border-accent"
              >
                {sessions.length === 0 && <option value="">No previous chats</option>}
                {sessions.map((session) => (
                  <option key={session.session_id} value={session.session_id}>
                    {session.session_title} · {formatSessionTimestamp(session.timestamp)}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => void startNewChat()}
                disabled={loadingSessions || creatingSession || sending}
                aria-label="Start a new chat"
                title="New chat"
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-line text-muted hover:bg-gray-50 hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Plus size={16} />
              </button>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto bg-gray-50/60 px-4 py-4" aria-live="polite">
              {(loadingSessions || loadingHistory) && (
                <p className="py-8 text-center text-[12px] text-faint">Loading conversation…</p>
              )}

              {!loadingSessions && !loadingHistory && messages.length === 0 && (
                <div className="mx-auto mt-12 max-w-[260px] text-center">
                  <span className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-accent-soft text-accent">
                    <Bot size={19} />
                  </span>
                  <h3 className="mt-3 text-[13px] font-semibold text-ink">How can I help?</h3>
                  <p className="mt-1 text-[12px] leading-relaxed text-muted">
                    Ask about campaign reach, outstanding actions, or adviser workflows.
                  </p>
                </div>
              )}

              <div className="space-y-3">
                {messages.map((message, index) => {
                  const fromAssistant = message.user === false;
                  return (
                    <div
                      key={`${message.timestamp}-${index}`}
                      className={`flex ${fromAssistant ? 'justify-start' : 'justify-end'}`}
                    >
                      <div
                        className={`min-w-0 rounded-xl text-[13px] leading-relaxed shadow-sm ${
                          fromAssistant
                            ? 'w-full rounded-tl-sm border border-line-soft bg-white px-4 py-3 text-body'
                            : 'max-w-[85%] rounded-tr-sm bg-ink px-3 py-2 text-white'
                        }`}
                      >
                        {fromAssistant ? (
                          <AssistantMessage content={message.message_content} advisorId={advisorId} />
                        ) : (
                          <p className="whitespace-pre-wrap break-words">{message.message_content}</p>
                        )}
                      </div>
                    </div>
                  );
                })}
                {latestCampaignDraft && activeSessionId && (
                  <div className="rounded-xl border border-accent/25 bg-accent-soft p-3 shadow-sm">
                    <div className="flex items-start gap-2.5">
                      <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white text-accent">
                        <FileText size={16} />
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="text-[12px] font-semibold text-ink">Campaign draft ready for review</p>
                        <p className="mt-0.5 truncate text-[12px] text-body">
                          {latestCampaignDraft.draft.name}
                        </p>
                        <p className="mt-1 text-[10px] text-muted">
                          Revision {latestCampaignDraft.revision} · Adviser review required
                        </p>
                        <button
                          type="button"
                          onClick={() => {
                            onReviewCampaignDraft?.(latestCampaignDraft, activeSessionId);
                            setOpen(false);
                          }}
                          className="mt-2 rounded-md bg-accent px-3 py-1.5 text-[11px] font-semibold text-white hover:bg-accent-hover"
                        >
                          Review draft
                        </button>
                      </div>
                    </div>
                  </div>
                )}
                {sending && (
                  <div className="flex justify-start">
                    <div className="rounded-xl rounded-tl-sm border border-line-soft bg-white px-3 py-2 text-[12px] text-muted shadow-sm">
                      Thinking…
                    </div>
                  </div>
                )}
                <div ref={messagesEnd} />
              </div>
            </div>

            {error && (
              <div
                role="alert"
                className="flex items-center gap-2 border-t border-danger/15 bg-danger-soft px-4 py-2 text-[11px] text-danger"
              >
                <span className="min-w-0 flex-1">{error.message}</span>
                {(error.source === 'sessions' || error.source === 'history') && (
                  <button
                    type="button"
                    onClick={retryLoad}
                    className="shrink-0 font-semibold underline underline-offset-2"
                  >
                    Retry
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setError(null)}
                  aria-label="Dismiss error"
                  className="shrink-0 font-semibold underline underline-offset-2"
                >
                  Dismiss
                </button>
              </div>
            )}

            <div className="border-t border-line bg-white">
              <form onSubmit={submitMessage} className="flex items-end gap-2 px-3 pb-1.5 pt-3">
                <textarea
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && !event.shiftKey) {
                      event.preventDefault();
                      event.currentTarget.form?.requestSubmit();
                    }
                  }}
                  rows={1}
                  maxLength={4000}
                  placeholder="Ask PULSE…"
                  aria-label="Message"
                  disabled={sending}
                  className="max-h-28 min-h-9 flex-1 resize-y rounded-md border border-line px-3 py-2 text-[12px] outline-none focus:border-accent disabled:bg-gray-50"
                />
                <button
                  type="submit"
                  disabled={!draft.trim() || sending}
                  aria-label="Send message"
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-accent text-white hover:bg-accent-hover disabled:cursor-not-allowed disabled:bg-gray-200 disabled:text-gray-400"
                >
                  <Send size={15} />
                </button>
              </form>
              <p className="px-3 pb-2 text-center text-[10px] leading-relaxed text-faint">
                AI-generated responses may be inaccurate. Verify before acting; PULSE never
                sends client communications automatically.
              </p>
            </div>
          </motion.section>
        )}
      </AnimatePresence>
    </>
  );
}
