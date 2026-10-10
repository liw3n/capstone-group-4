import { FormEvent, useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { Bot, MessageCircle, Plus, Send, X } from 'lucide-react';
import AssistantMessage from './AssistantMessage';
import {
  ChatMessage,
  ChatSession,
  createChatSession,
  getChatHistory,
  listChatSessions,
  sendChatMessage,
} from '../services/chatApi';

interface ChatPanelProps {
  advisorId: string;
  campaignId?: string;
  campaignName?: string;
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

export default function ChatPanel({ advisorId, campaignId, campaignName }: ChatPanelProps) {
  const [open, setOpen] = useState(false);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
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

  useEffect(() => {
    loadedForAdvisor.current = null;
    skipHistoryForSession.current = null;
    createRequest.current?.abort();
    sendRequest.current?.abort();
    setSessions([]);
    setActiveSessionId(null);
    setMessages([]);
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
    setError((current) => (current?.source === 'history' ? null : current));
    const controller = new AbortController();
    getChatHistory(activeSessionId, controller.signal)
      .then((history) => {
        if (!cancelled) setMessages(history);
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
  }, [activeSessionId, historyLoadAttempt, open]);

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
        campaignId,
      );
      if (controller.signal.aborted) return;
      setMessages((current) => [
        ...current,
        {
          timestamp: response.timestamp,
          user: false,
          message_content: response.ai_answer,
        },
      ]);
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
            className="fixed inset-x-3 bottom-3 z-50 flex h-[min(640px,calc(100vh-24px))] flex-col overflow-hidden rounded-xl border border-line bg-white shadow-2xl sm:inset-x-auto sm:bottom-5 sm:right-5 sm:w-[460px]"
          >
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
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close PULSE assistant"
                className="rounded p-1.5 text-white/70 hover:bg-white/10 hover:text-white"
              >
                <X size={17} />
              </button>
            </header>

            <div className="border-b border-line-soft bg-link-soft px-3 py-2 text-[12px] text-body">
              <p className="font-medium">
                {campaignName ? 'Selected campaign: ' + campaignName : 'Select a campaign to request client recommendations.'}
              </p>
              {campaignId && (
                <>
                  <p className="mt-1 text-[11px] text-muted">
                    Demo recommendations use a separate synthetic client list.
                  </p>
                  <button
                    type="button"
                    onClick={() => setDraft('Which clients are recommended for this campaign? Explain why each matches.')}
                    disabled={sending || creatingSession}
                    className="mt-1 text-link hover:underline disabled:opacity-50"
                  >
                    Ask for recommended clients
                  </button>
                </>
              )}
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
                          <AssistantMessage content={message.message_content} />
                        ) : (
                          <p className="whitespace-pre-wrap break-words">{message.message_content}</p>
                        )}
                      </div>
                    </div>
                  );
                })}
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
