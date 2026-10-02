export interface ParsedSheet {
  headers: string[];
  rows: string[][];
}

export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

export const ACCEPTED_EXTENSIONS = ['.xlsx', '.xls', '.csv'];

function hasAcceptedExtension(fileName: string): boolean {
  return ACCEPTED_EXTENSIONS.some((ext) => fileName.toLowerCase().endsWith(ext));
}

/**
 * Reads an Excel or CSV file into headers plus rows. SheetJS handles both, so
 * one path covers every accepted format.
 */
export async function parseSpreadsheet(file: File): Promise<ParsedSheet> {
  if (file.size > MAX_UPLOAD_BYTES) {
    throw new Error('That file is larger than the 10 MB limit.');
  }
  if (!hasAcceptedExtension(file.name)) {
    throw new Error('Upload an Excel (.xlsx, .xls) or CSV (.csv) file.');
  }

  // Loaded on demand: SheetJS is large and only the upload wizard needs it.
  const XLSX = await import('xlsx');

  const buffer = await file.arrayBuffer();
  const workbook = XLSX.read(buffer, { type: 'array' });

  const sheetName = workbook.SheetNames[0];
  if (!sheetName) throw new Error('That file has no worksheets.');

  const matrix = XLSX.utils.sheet_to_json<unknown[]>(workbook.Sheets[sheetName], {
    header: 1,
    blankrows: false,
    defval: '',
    raw: false,
  });

  if (matrix.length === 0) throw new Error('That file appears to be empty.');

  const [headerRow, ...dataRows] = matrix;
  const headers = headerRow.map((h) => String(h ?? '').trim());

  if (headers.every((h) => !h)) throw new Error('No column headers were found in the first row.');

  const rows = dataRows
    .map((row) => headers.map((_, i) => String(row[i] ?? '').trim()))
    .filter((row) => row.some((cell) => cell !== ''));

  if (rows.length === 0) throw new Error('That file has headers but no data rows.');

  return { headers, rows };
}

/**
 * Reads a cell by the field its column was mapped to, rather than by position.
 * A field that was never mapped — and a row that stops short of it — reads as
 * an empty string, which both import paths treat as absent.
 *
 * First mapping wins, so a sheet with "Phone" and "Mobile" both pointed at the
 * same field still yields one column.
 */
export function createCellReader<F extends string>(
  matches: { field: F }[],
): (row: string[], field: F) => string {
  const columnFor = new Map<F, number>();
  matches.forEach((match, index) => {
    if (!columnFor.has(match.field)) columnFor.set(match.field, index);
  });

  return (row, field) => {
    const index = columnFor.get(field);
    return index === undefined ? '' : (row[index] ?? '').trim();
  };
}

/** The downloadable starter file offered on step 1 of the contacts wizard. */
export function buildContactTemplateCsv(): string {
  return [
    'Name,Email,Country Code,Phone Number,Date of Birth,NRIC/Passport,Label',
    'Tan Wei Ming,wei.ming@example.com,+65,91234567,1985-04-12,S8512345A,Prospect',
    'Priya Sharma,priya.sharma@example.com,+65,98765432,1990-11-03,S9098765B,Client',
  ].join('\n');
}

/**
 * The lead-list equivalent. Deliberately thinner than the contacts template: a
 * lead needs a name plus an email *or* a mobile, and the sample rows show each
 * of those halves missing in turn.
 */
export function buildLeadTemplateCsv(): string {
  return [
    'Name,Email,Country Code,Phone Number',
    'Tan Wei Ming,wei.ming@example.com,+65,91234567',
    'Roadshow walk-in,,+65,98765432',
    'Priya S.,priya.s@example.com,,',
  ].join('\n');
}

/** Hands the browser a CSV to save. There is no backend; the file is built here. */
export function downloadCsv(fileName: string, csv: string): void {
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName;
  link.click();
  URL.revokeObjectURL(url);
}
