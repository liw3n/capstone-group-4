import { useRef, useState } from 'react';
import { Download, FileText, Loader2, TriangleAlert, Upload, X } from 'lucide-react';
import { Contact } from '../types';
import Button from '../ui/Button';
import {
  ColumnMatch,
  CONTACT_FIELD_LABELS,
  ContactField,
  suggestColumnMapping,
} from '../services/ai';
import {
  ACCEPTED_EXTENSIONS,
  buildLeadTemplateCsv,
  downloadCsv,
  ParsedSheet,
  parseSpreadsheet,
} from '../lib/spreadsheet';
import { buildLeadsFromSheet, LeadImport } from '../lib/leads';
import { display, EMPTY } from '../lib/format';

interface LeadUploadPanelProps {
  onChange: (leads: Omit<Contact, 'id'>[]) => void;
}

/** Only the fields a lead list can meaningfully carry. */
const LEAD_FIELDS: ContactField[] = ['name', 'email', 'countryCode', 'phone', 'ignore'];

export default function LeadUploadPanel({ onChange }: LeadUploadPanelProps) {
  const [file, setFile] = useState<File | null>(null);
  const [sheet, setSheet] = useState<ParsedSheet | null>(null);
  const [matches, setMatches] = useState<ColumnMatch[]>([]);
  const [result, setResult] = useState<LeadImport | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const recompute = (nextSheet: ParsedSheet, nextMatches: ColumnMatch[]) => {
    const built = buildLeadsFromSheet(nextSheet, nextMatches);
    setResult(built);
    onChange(built.leads);
  };

  const accept = async (candidate: File) => {
    setError('');
    setBusy(true);
    try {
      const parsed = await parseSpreadsheet(candidate);
      const suggested = await suggestColumnMapping(parsed.headers);
      setFile(candidate);
      setSheet(parsed);
      setMatches(suggested);
      recompute(parsed, suggested);
    } catch (e) {
      reset();
      setError(e instanceof Error ? e.message : 'That file could not be read.');
    } finally {
      setBusy(false);
    }
  };

  const reset = () => {
    setFile(null);
    setSheet(null);
    setMatches([]);
    setResult(null);
    onChange([]);
    if (fileInput.current) fileInput.current.value = '';
  };

  const changeMatch = (index: number, field: ContactField) => {
    if (!sheet) return;
    const next = matches.map((m, i) => (i === index ? { ...m, field } : m));
    setMatches(next);
    recompute(sheet, next);
  };

  const downloadTemplate = () => downloadCsv('lead-list-template.csv', buildLeadTemplateCsv());

  if (!sheet) {
    return (
      <div className="flex flex-col gap-3">
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setIsDragging(true);
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setIsDragging(false);
            const dropped = e.dataTransfer.files?.[0];
            if (dropped) accept(dropped);
          }}
          className={`flex flex-col items-center justify-center gap-2 rounded-md border border-dashed py-10 transition-colors ${
            isDragging ? 'border-accent bg-accent-soft/50' : 'border-line'
          }`}
        >
          {busy ? (
            <Loader2 size={20} className="animate-spin text-accent" />
          ) : (
            <Upload size={20} className="text-muted" />
          )}
          <p className="text-[13px] text-body">
            Drop your roadshow or canvassing list here
          </p>
          <p className="text-[11px] text-faint">
            Excel or CSV. Each row needs a name, plus an email or a mobile number.
          </p>
          <Button variant="secondary" onClick={() => fileInput.current?.click()} disabled={busy}>
            Choose file
          </Button>
        </div>

        <button
          type="button"
          onClick={downloadTemplate}
          className="flex w-fit items-center gap-1.5 text-[12px] text-link hover:underline"
        >
          <Download size={12} />
          Download a template
        </button>

        {error && <p className="text-[12px] text-danger">{error}</p>}

        <input
          ref={fileInput}
          type="file"
          accept={ACCEPTED_EXTENSIONS.join(',')}
          className="hidden"
          onChange={(e) => {
            const chosen = e.target.files?.[0];
            if (chosen) accept(chosen);
          }}
        />
      </div>
    );
  }

  const preview = result?.leads.slice(0, 5) ?? [];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3 rounded-md border border-line px-3 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <FileText size={15} className="shrink-0 text-accent" />
          <span className="truncate text-[13px] text-body">{file?.name}</span>
        </div>
        <button
          onClick={reset}
          className="flex shrink-0 items-center gap-1 text-[12px] text-danger hover:underline"
        >
          <X size={13} />
          Remove
        </button>
      </div>

      <div className="flex flex-col gap-2">
        <span className="field-label">Match the columns</span>
        <div className="flex flex-col gap-1.5">
          {matches.map((match, index) => (
            <div key={match.header + index} className="grid grid-cols-[1fr_1fr] items-center gap-3">
              <span className="truncate text-[13px] text-body">{display(match.header)}</span>
              <select
                value={match.field}
                onChange={(e) => changeMatch(index, e.target.value as ContactField)}
                aria-label={`Map column ${match.header}`}
                className="w-full rounded-md border border-line px-2 py-1.5 text-[12px] outline-none transition-colors focus:border-accent"
              >
                {LEAD_FIELDS.map((field) => (
                  <option key={field} value={field}>
                    {CONTACT_FIELD_LABELS[field]}
                  </option>
                ))}
              </select>
            </div>
          ))}
        </div>
      </div>

      {result && (
        <>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md bg-line-soft px-3 py-2.5 text-[12px]">
            <span className="text-body">
              <span className="font-semibold text-ink">{result.leads.length}</span> of {result.total}{' '}
              rows usable
            </span>
            {result.skipped > 0 && (
              <span className="flex items-center gap-1 text-amber">
                <TriangleAlert size={12} />
                {result.skipped} skipped — no name, or no email and no mobile
              </span>
            )}
          </div>

          {preview.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <span className="field-label">Preview</span>
              <div className="overflow-hidden rounded-md border border-line">
                {preview.map((lead, i) => (
                  <div
                    key={lead.name + i}
                    className="flex items-center gap-3 border-b border-line-soft px-3 py-2 last:border-0"
                  >
                    <span className="min-w-0 flex-1 truncate text-[13px] text-body">
                      {lead.name}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-[12px] text-faint">
                      {display(lead.email)}
                    </span>
                    <span className="shrink-0 text-[12px] text-faint">
                      {lead.phone ? `${lead.countryCode} ${lead.phone}` : EMPTY}
                    </span>
                  </div>
                ))}
              </div>
              {result.leads.length > preview.length && (
                <span className="text-[11px] text-faint">
                  and {result.leads.length - preview.length} more
                </span>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
