import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { createServer } from 'vite';

let server;
let api;
const originalWindow = globalThis.window;

before(async () => {
  globalThis.window = { location: { origin: 'http://localhost:3000' } };
  server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom' });
  api = await server.ssrLoadModule('/src/services/chatApi.ts');
});

after(async () => {
  await server?.close();
  if (originalWindow === undefined) delete globalThis.window;
  else globalThis.window = originalWindow;
});

test('chat sends adviser, session and message without a CRM-selected campaign', async (t) => {
  const response = {
    user: 'synthetic-adviser', timestamp: '2026-10-28T00:00:00Z',
    ai_answer: 'Synthetic matching clients.',
    campaignDraft: null, campaignDraftOptions: null,
  };
  const controller = new AbortController();
  let captured;
  t.mock.method(globalThis, 'fetch', async (url, init) => {
    captured = { url, ...init };
    return new Response(JSON.stringify(response), { status: 200 });
  });
  const result = await api.sendChatMessage('synthetic-adviser', 'synthetic-session',
    'Which clients match First Home Starter Bundle?', controller.signal);
  assert.deepEqual(result, response);
  assert.equal(captured.url, '/api/chat/query');
  assert.equal(captured.method, 'POST');
  assert.equal(captured.signal, controller.signal);
  assert.equal(captured.headers.get('Content-Type'), 'application/json');
  assert.deepEqual(JSON.parse(captured.body), {
    fa_id: 'synthetic-adviser', session_id: 'synthetic-session',
    message_content: 'Which clients match First Home Starter Bundle?',
  });
});

test('chat cancellation still propagates as an abort', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => {
    throw new DOMException('Aborted', 'AbortError');
  });
  await assert.rejects(api.sendChatMessage('adviser', 'session', 'Question'),
    (error) => error.name === 'AbortError');
});

test('provider error messages still reach the chat panel', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response(
    JSON.stringify({ detail: 'AI provider rate limit reached' }), { status: 429 }));
  await assert.rejects(api.sendChatMessage('adviser', 'session', 'Question'),
    (error) => error instanceof api.ChatApiError && error.status === 429
      && error.message === 'AI provider rate limit reached');
});

test('saved conversations and history keep their existing scoped requests', async (t) => {
  const requests = [];
  t.mock.method(globalThis, 'fetch', async (url) => {
    requests.push(url);
    return new Response('[]', { status: 200 });
  });
  assert.deepEqual(await api.listChatSessions('synthetic-adviser'), []);
  assert.deepEqual(await api.getChatHistory('synthetic-session'), []);
  assert.deepEqual(requests, [
    '/api/chat/sessions?fa_id=synthetic-adviser',
    '/api/chat/history?session_id=synthetic-session',
  ]);
});
