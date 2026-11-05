import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

let server;
let AssistantMessage;
let campaignWorkbookBytes;
before(async () => {
  server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom' });
  ({ default: AssistantMessage } = await server.ssrLoadModule('/src/components/AssistantMessage.tsx'));
  ({ campaignWorkbookBytes } = await server.ssrLoadModule('/src/lib/campaignExport.ts'));
});
after(async () => { await server?.close(); });
const render = (content) => renderToStaticMarkup(createElement(AssistantMessage, { content }));

const recommendation = `**Recommended clients for Legacy Protection Refresh**

| Contact ID | Client name | Reasons for match |
|------------|-------------|-------------------|
| client-001 | Demo Client A | Age 58 matches.<br>Cash S$300,000 matches. |
| client-002 | Demo Client B | Age 70 matches.<br/>Cash S$1,000,000 matches. |
| client-003 | Demo Client C | Age 55 matches.<BR />Cash S$250,000 matches. |
| client-012 | Demo Client L | Age 58 matches.<br >Cash S$300,000 matches. |

### Clients requiring more information

| Contact ID | Client name | Missing field(s) |
|------------|-------------|------------------|
| client-010 | Demo Client J | date_of_birth |
| client-011 | Demo Client K | available_cash |

**6 clients excluded by campaign rules.**

These are synthetic matches for adviser review, not financial advice.`;

test('saved recommendation tables become cards without losing identities, reasons or disclaimer', () => {
  const html = render(recommendation);
  assert.equal((html.match(/class="pulse-client-cards"/g) ?? []).length, 2);
  for (const id of ['001', '002', '003', '012', '010', '011']) assert.ok(html.includes('client-' + id));
  for (const name of ['A', 'B', 'C', 'L', 'J', 'K']) assert.ok(html.includes('Demo Client ' + name));
  assert.ok(html.includes('date_of_birth'));
  assert.ok(html.includes('available_cash'));
  assert.ok(html.includes('6 clients excluded'));
  assert.ok(html.includes('not financial advice'));
  assert.ok(html.includes('<strong>Recommended clients'));
  assert.ok(html.includes('<h3>Clients requiring more information</h3>'));
  assert.ok(html.includes('data-label="Reasons for match"'));
  assert.equal((html.match(/<br\/>/g) ?? []).length, 4);
  assert.ok(!html.includes('&lt;br'));
});

test('ordinary tables retain column structure and Markdown lists render as lists', () => {
  const html = render('| Campaign | Matches |\n| --- | --- |\n| camp-1 | 4 |\n\n- Age matches\n- Cash matches');
  assert.ok(html.includes('<table>'));
  assert.ok(!html.includes('pulse-client-cards'));
  assert.ok(html.includes('<th>Campaign</th>'));
  assert.ok(html.includes('<td>4</td>'));
  assert.ok(html.includes('<ul>'));
  assert.ok(html.includes('<li>Age matches</li>'));
});

test('untrusted HTML and unsafe links cannot become executable markup', () => {
  const html = render('Safe text\n\n<script>alert(1)</script>\n\n<img src=x onerror=alert(1)>\n\n[Bad](javascript:alert%281%29) [Good](https://example.com)');
  assert.ok(!/<script|<img|onerror|href="javascript:/i.test(html));
  assert.ok(html.includes('Safe text'));
  assert.ok(html.includes('href="https://example.com"'));
  assert.ok(html.includes('rel="noopener noreferrer"'));
});

test('literal HTML in code and normal plain-text responses remain readable', () => {
  const html = render('Use `<br>` as a code example.\n\nA normal answer with **emphasis**.');
  assert.ok(html.includes('<code>&lt;br&gt;</code>'));
  assert.ok(!html.includes('<br/>'));
  assert.ok(html.includes('<strong>emphasis</strong>'));
  assert.ok(html.includes('A normal answer'));
});

test('restored campaign tables expose an Excel download beneath the exact displayed table', () => {
  const content = '**Current date: 4 November 2026 (Singapore)**\n\n'
    + '| Campaign Name | Campaign Code | Age Group | Cash Bands |\n'
    + '| --- | --- | --- | --- |\n'
    + '| A &#124; B | CMP-2026-003 | 40–55 | S$500,000–S$2,000,000 |\n\n'
    + '[Download Excel (.xlsx)](#active-campaigns-excel)';
  const html = render(content);
  assert.ok(html.includes('Current date: 4 November 2026'));
  assert.ok(html.includes('<td>A | B</td>'));
  assert.ok(html.indexOf('</table>') < html.indexOf('Download Excel (.xlsx)'));
  assert.ok(html.includes('href="#active-campaigns-excel"'));
  assert.ok(!html.includes('data-campaign-export='));
  assert.ok(render('[Download Excel (.xlsx)](#active-campaigns-excel)').includes('Excel download unavailable'));
});

test('Excel bytes preserve column order, text and custom ranges without creating formulas', async () => {
  const XLSX = await import('xlsx');
  const table = [
    ['Campaign Name', 'Campaign Code', 'Age Group', 'Cash Bands'],
    ['=1+1', 'CMP-2026-003', '40–55', 'S$500,000–S$2,000,000'],
    ['A | B', 'CMP-2026-004', 'Under 35', 'Below S$50,000'],
  ];
  const workbook = XLSX.read(await campaignWorkbookBytes(table), { type: 'array' });
  const sheet = workbook.Sheets['Active Campaigns'];
  assert.deepEqual(XLSX.utils.sheet_to_json(sheet, { header: 1 }), table);
  assert.equal(sheet.A2.t, 's');
  assert.equal(sheet.A2.f, undefined);
  const empty = XLSX.read(await campaignWorkbookBytes([table[0]]), { type: 'array' });
  assert.deepEqual(XLSX.utils.sheet_to_json(empty.Sheets['Active Campaigns'], { header: 1 }), [table[0]]);
});
