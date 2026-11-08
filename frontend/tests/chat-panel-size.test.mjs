import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { createServer } from 'vite';

let server;
let size;

before(async () => {
  server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom' });
  size = await server.ssrLoadModule('/src/lib/chatPanelSize.ts');
});

after(async () => {
  await server?.close();
});

test('dragging the top-left handle up and left grows the panel', () => {
  const next = size.resizeFromTopLeft({ width: 460, height: 640 }, -200, -100, { width: 1600, height: 1000 });
  assert.deepEqual(next, { width: 660, height: 740 });
});

test('panel size is clamped to the minimum and to the viewport', () => {
  const viewport = { width: 1200, height: 800 };
  assert.deepEqual(size.clampChatPanelSize({ width: 100, height: 100 }, viewport), size.MIN_CHAT_PANEL_SIZE);
  assert.deepEqual(size.clampChatPanelSize({ width: Infinity, height: Infinity }, viewport), {
    width: 1200 - size.CHAT_PANEL_VIEWPORT_MARGIN,
    height: 800 - size.CHAT_PANEL_VIEWPORT_MARGIN,
  });
});

test('stored sizes are parsed defensively', () => {
  assert.deepEqual(size.parseStoredChatPanelSize('{"width":700,"height":500}'), { width: 700, height: 500 });
  assert.equal(size.parseStoredChatPanelSize('not json'), null);
  assert.equal(size.parseStoredChatPanelSize('{"width":"wide"}'), null);
  assert.equal(size.parseStoredChatPanelSize(null), null);
});
