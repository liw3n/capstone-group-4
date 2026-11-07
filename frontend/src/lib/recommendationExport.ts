import { utils, write } from 'xlsx';
import type { RecommendationList } from '../services/chatApi';

export function recommendationWorkbookBytes(result: RecommendationList): ArrayBuffer {
  const workbook = utils.book_new();
  const reasonCount = result.clients.reduce((count, client) => Math.max(count, client.reasons.length), 0);
  const reasonHeaders = Array.from({ length: Math.max(1, reasonCount) }, (_, index) => `Eligibility reason ${index + 1}`);
  const reasonWidths = reasonHeaders.map((header) => ({ wch: header.length + 2 }));
  for (const client of result.clients) {
    client.reasons.forEach((reason, index) => {
      // Size each reason separately so Excel does not hide it behind the next cell.
      reasonWidths[index].wch = Math.min(255, Math.max(reasonWidths[index].wch, reason.length + 2));
    });
  }
  // String cells stay text even when a synthetic name begins with =, + or @.
  utils.book_append_sheet(workbook, utils.aoa_to_sheet([
    ['Campaign', result.campaign_name], ['As of (Singapore)', result.as_of_date],
    ['Evaluated', result.evaluated_count], ['Matched', result.matched_count],
    ['Incomplete', result.incomplete_count], ['Excluded', result.excluded_count],
    ['List ID', result.list_id], ['Download expires', result.expires_at],
    ['Notice', result.disclaimer],
    ['Outreach', 'Review this synthetic snapshot; recheck eligibility and consent before outreach.'],
  ]), 'Summary');
  utils.book_append_sheet(workbook, utils.aoa_to_sheet([
    ['Contact ID', 'Client Name', ...reasonHeaders],
    ...result.clients.map((client) => [client.contact_id, client.name, ...client.reasons]),
  ]), 'Matched clients');
  utils.book_append_sheet(workbook, utils.aoa_to_sheet([
    ['Contact ID', 'Client Name', 'Missing Fields'],
    ...result.incomplete_clients.map((client) => [client.contact_id, client.name, client.missing_fields.join(', ')]),
  ]), 'Incomplete profiles');
  workbook.Sheets.Summary['!cols'] = [{ wch: 24 }, { wch: 100 }];
  workbook.Sheets['Matched clients']['!cols'] = [{ wch: 38 }, { wch: 28 }, ...reasonWidths];
  workbook.Sheets['Incomplete profiles']['!cols'] = [{ wch: 38 }, { wch: 28 }, { wch: 40 }];
  return write(workbook, { bookType: 'xlsx', type: 'array' });
}

export function downloadRecommendationList(result: RecommendationList): void {
  const url = URL.createObjectURL(new Blob([recommendationWorkbookBytes(result)], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  }));
  const link = document.createElement('a');
  link.href = url;
  link.download = `recommended-clients-${result.as_of_date}.xlsx`;
  try {
    document.body.appendChild(link);
    link.click();
  } finally {
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}
