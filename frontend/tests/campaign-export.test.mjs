import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { createServer } from 'vite';

let server;
let downloadCampaignTable;
before(async () => {
  server = await createServer({ configFile: false,
    server: { middlewareMode: true, hmr: false }, appType: 'custom',
    optimizeDeps: { noDiscovery: true, entries: [], include: [] },
  });
  ({ downloadCampaignTable } = await server.ssrLoadModule('/src/lib/campaignExport.ts'));
});
after(async () => { await server?.close(); });

function browser(t, failClick = false) {
  const calls = [];
  let downloadedBlob;
  let cleanup;
  const link = {
    href: '', download: '',
    click() {
      calls.push('click');
      if (failClick) throw new Error('Browser blocked the download');
    },
    remove() { calls.push('remove'); },
  };
  const oldDocument = Object.getOwnPropertyDescriptor(globalThis, 'document');
  const oldWindow = Object.getOwnPropertyDescriptor(globalThis, 'window');
  Object.defineProperty(globalThis, 'document', { configurable: true, value: {
    createElement(tag) { assert.equal(tag, 'a'); return link; },
    body: { appendChild(node) { assert.equal(node, link); calls.push('append'); } },
  } });
  Object.defineProperty(globalThis, 'window', { configurable: true, value: {
    setTimeout(callback, delay) { assert.equal(delay, 1000); cleanup = callback; },
  } });
  t.after(() => {
    if (oldDocument) Object.defineProperty(globalThis, 'document', oldDocument);
    else delete globalThis.document;
    if (oldWindow) Object.defineProperty(globalThis, 'window', oldWindow);
    else delete globalThis.window;
  });
  t.mock.method(URL, 'createObjectURL', (blob) => {
    downloadedBlob = blob;
    return 'blob:synthetic-workbook';
  });
  t.mock.method(URL, 'revokeObjectURL', (url) => {
    assert.equal(url, 'blob:synthetic-workbook'); calls.push('revoke');
  });
  t.mock.method(globalThis, 'fetch', () => assert.fail('Download must not fetch another asset or API'));
  return { calls, link, blob: () => downloadedBlob, cleanup: () => cleanup() };
}

test('download starts during the click, saves actual Excel bytes and releases browser resources', async (t) => {
  const context = browser(t);
  const table = [['Campaign Name', 'Cash Bands'], ['=1+1', 'S$50,000 to below S$250,000']];
  const done = downloadCampaignTable(table);

  assert.deepEqual(context.calls, ['append', 'click', 'remove']);
  await done;
  assert.equal(context.link.download, 'active-campaigns.xlsx');
  assert.equal(context.link.href, 'blob:synthetic-workbook');
  assert.equal(context.blob().type, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
  const XLSX = await import('xlsx');
  const workbook = XLSX.read(await context.blob().arrayBuffer(), { type: 'array' });
  assert.deepEqual(XLSX.utils.sheet_to_json(workbook.Sheets['Active Campaigns'], { header: 1 }), table);
  assert.equal(workbook.Sheets['Active Campaigns'].A2.f, undefined);
  context.cleanup();
  assert.equal(context.calls.at(-1), 'revoke');
});

test('a browser download failure still removes the temporary link and revokes its URL', async (t) => {
  const context = browser(t, true);
  await assert.rejects(downloadCampaignTable([['Campaign'], ['Synthetic']]), /Browser blocked/);
  assert.deepEqual(context.calls, ['append', 'click', 'remove']);
  context.cleanup();
  assert.equal(context.calls.at(-1), 'revoke');
});
