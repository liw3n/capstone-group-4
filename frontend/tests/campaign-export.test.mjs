import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { createServer } from 'vite';

let server;
let downloadCampaignTable;
let recommendationWorkbookBytes;
let downloadRecommendationList;
before(async () => {
  server = await createServer({ configFile: false,
    server: { middlewareMode: true, hmr: false }, appType: 'custom',
    optimizeDeps: { noDiscovery: true, entries: [], include: [] },
  });
  ({ downloadCampaignTable } = await server.ssrLoadModule('/src/lib/campaignExport.ts'));
  ({ recommendationWorkbookBytes, downloadRecommendationList } = await server.ssrLoadModule('/src/lib/recommendationExport.ts'));
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

function recommendationSnapshot() {
  return {
    list_id: '66666666-6666-4666-8666-666666666666', campaign_name: 'Broad demo campaign',
    as_of_date: '2026-11-07', evaluated_count: 175, matched_count: 150,
    incomplete_count: 25, excluded_count: 0, expires_at: '2026-11-08T00:00:00Z',
    disclaimer: 'Synthetic data; not financial advice.',
    clients: Array.from({ length: 150 }, (_, i) => ({
      contact_id: `client-${i}`, name: i === 0 ? '=1+1' : `Client ${i}`,
      reasons: ['Meets the age criterion', 'Meets the cash criterion'],
    })),
    incomplete_clients: Array.from({ length: 25 }, (_, i) => ({
      contact_id: `gap-${i}`, name: `Incomplete ${i}`, missing_fields: ['date_of_birth'],
    })),
  };
}

test('client workbook includes all results beyond both the preview and old 100-row limit', async () => {
  const XLSX = await import('xlsx');
  const workbook = XLSX.read(recommendationWorkbookBytes(recommendationSnapshot()), { type: 'array' });
  const matches = XLSX.utils.sheet_to_json(workbook.Sheets['Matched clients'], { header: 1 });
  const gaps = XLSX.utils.sheet_to_json(workbook.Sheets['Incomplete profiles'], { header: 1 });
  assert.equal(matches.length, 151);
  assert.equal(gaps.length, 26);
  assert.equal(matches.at(-1)[0], 'client-149');
  assert.equal(gaps.at(-1)[0], 'gap-24');
  assert.equal(workbook.Sheets['Matched clients'].B2.v, '=1+1');
  assert.equal(workbook.Sheets['Matched clients'].B2.f, undefined);
  assert.equal(workbook.Sheets['Matched clients'].B2.t, 's');
  assert.ok(XLSX.utils.sheet_to_json(workbook.Sheets.Summary, { header: 1 })
    .some(([label, value]) => label === 'Matched' && value === 150));
});

test('client export downloads XLSX without any model request and cleans up browser resources', async (t) => {
  const context = browser(t);
  downloadRecommendationList(recommendationSnapshot());
  assert.equal(context.link.download, 'recommended-clients-2026-11-07.xlsx');
  assert.equal(context.blob().type, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
  assert.deepEqual(context.calls, ['append', 'click', 'remove']);
  context.cleanup();
  assert.equal(context.calls.at(-1), 'revoke');
});

test('client export separates every eligibility reason and sizes the columns to their text', async () => {
  const XLSX = await import('xlsx');
  const snapshot = recommendationSnapshot();
  snapshot.clients = [
    { contact_id: 'client-1', name: 'Client One', reasons: [
      'Age 58 matches the campaign age group (55 - 64)',
      'Gender Male matches the campaign criterion',
      'Available cash of S$60,000 matches the cash criterion (S$50,000 to below S$250,000)',
    ] },
    { contact_id: 'client-2', name: 'Client Two', reasons: ['No targeting restrictions'] },
    { contact_id: 'client-3', name: 'Client Three', reasons: ['=1+1', 'Custom condition', 'Another condition', 'Additional condition'] },
    { contact_id: 'client-4', name: 'Client Four', reasons: [] },
  ];
  const workbook = XLSX.read(recommendationWorkbookBytes(snapshot), { type: 'array', cellStyles: true });
  const sheet = workbook.Sheets['Matched clients'];
  const rows = XLSX.utils.sheet_to_json(sheet, { header: 1 });
  assert.deepEqual(rows[0], ['Contact ID', 'Client Name', 'Eligibility reason 1',
    'Eligibility reason 2', 'Eligibility reason 3', 'Eligibility reason 4']);
  snapshot.clients.forEach((client, index) => {
    assert.deepEqual(rows[index + 1], [client.contact_id, client.name, ...client.reasons]);
  });
  assert.ok(sheet['!cols'][4].wch >= snapshot.clients[0].reasons[2].length);
  assert.equal(sheet.C4.t, 's');
  assert.equal(sheet.C4.f, undefined);
});

test('client export still has a readable header when there are no matching clients', async () => {
  const XLSX = await import('xlsx');
  const snapshot = recommendationSnapshot();
  snapshot.clients = [];
  snapshot.matched_count = 0;
  const workbook = XLSX.read(recommendationWorkbookBytes(snapshot), { type: 'array' });
  assert.deepEqual(XLSX.utils.sheet_to_json(workbook.Sheets['Matched clients'], { header: 1 }),
    [['Contact ID', 'Client Name', 'Eligibility reason 1']]);
});
