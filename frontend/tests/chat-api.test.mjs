import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { createServer } from 'vite';

let server;
let api;
const originalWindow = globalThis.window;

test('full client download uses a separate adviser-scoped request with no chat/provider call', async (t) => {
  const listId = '66666666-6666-4666-8666-666666666666';
  const requests = [];
  const controller = new AbortController();
  const snapshot = { clients: Array.from({ length: 150 }, (_, i) => ({ contact_id: String(i) })) };
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    requests.push({ url, options });
    return new Response(JSON.stringify(snapshot), { status: 200 });
  });
  assert.deepEqual(await api.getRecommendationList(listId, 'adviser-a', controller.signal), snapshot);
  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, `/api/chat/recommendation-lists/${listId}?fa_id=adviser-a`);
  assert.equal(requests[0].options.signal, controller.signal);
  assert.equal(requests[0].options.body, undefined);
});

test('expired client download reports the backend recovery message', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response(
    JSON.stringify({ detail: 'This list has expired. Request recommendations again.' }), { status: 410 }));
  await assert.rejects(api.getRecommendationList('list', 'adviser-a'),
    (error) => error.status === 410 && error.message.includes('expired'));
});

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

test('active campaign discovery sends the frontend directory adviser ID without overriding tenant or campaign context', async (t) => {
  const { DEMO_ADVISOR } = await server.ssrLoadModule('/src/lib/directory.ts');
  let payload;
  t.mock.method(globalThis, 'fetch', async (_url, init) => {
    payload = JSON.parse(init.body);
    return new Response(JSON.stringify({ user: DEMO_ADVISOR.id, ai_answer: 'Campaign table',
      timestamp: '2026-11-04T00:00:00Z' }), { status: 200 });
  });
  await api.sendChatMessage(DEMO_ADVISOR.id, 'session', 'what are the active campaigns');
  assert.equal(payload.fa_id, DEMO_ADVISOR.id);
  assert.equal('tenant_id' in payload, false);
  assert.equal('campaign_id' in payload, false);
});
