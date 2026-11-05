import { utils, write } from 'xlsx';

/** Export the displayed snapshot without another database query. */
export function campaignWorkbookBytes(table: string[][]): ArrayBuffer {
  // Load the writer with the page: a download must not depend on fetching a
  // separate chunk after a deployment, or lose the browser's click activation.
  const sheet = utils.aoa_to_sheet(table);
  sheet['!cols'] = table[0].map((_, column) => ({
    wch: Math.min(65, Math.max(14, ...table.map((row) => (row[column] ?? '').length))),
  }));
  const workbook = utils.book_new();
  utils.book_append_sheet(workbook, sheet, 'Active Campaigns');
  return write(workbook, { bookType: 'xlsx', type: 'array' });
}

export async function downloadCampaignTable(table: string[][]): Promise<void> {
  const bytes = campaignWorkbookBytes(table);
  const url = URL.createObjectURL(new Blob([bytes], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  }));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'active-campaigns.xlsx';
  try {
    document.body.appendChild(link);
    link.click();
  } finally {
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}
