import { RefObject, useRef, useState } from 'react';
import { motion } from 'motion/react';
import { CircleCheck, Download, FileText, Loader2, Upload, Users, X } from 'lucide-react';
import { Contact, ContactSource } from '../types';
import Button from '../ui/Button';
import { partitionIncoming } from '../lib/dedupe';
import { EMPTY, todayISO } from '../lib/format';
import {
  ColumnMatch,
  CONTACT_FIELD_LABELS,
  CONTACT_FIELDS,
  ContactField,
  REQUIRED_FIELDS,
  suggestColumnMapping,
} from '../services/ai';
import {
  buildContactTemplateCsv,
  createCellReader,
  downloadCsv,
  MAX_UPLOAD_BYTES,
  ParsedSheet,
  parseSpreadsheet,
} from '../lib/spreadsheet';

interface UploadContactsWizardProps {
  /** The book, so incoming rows can be checked against it for duplicates. */
  contacts: Contact[];
  onClose: () => void;
  onImport: (contacts: Omit<Contact, 'id'>[]) => void;
  /** Canvassed lists belong on a campaign, not in the contact book. */
  onGoToCampaigns: () => void;
}

type Step = 'origin' | 'upload' | 'match' | 'complete';

const STEPS: { id: Step; label: string }[] = [
  { id: 'origin', label: 'Origin' },
  { id: 'upload', label: 'Upload' },
  { id: 'match', label: 'Match' },
  { id: 'complete', label: 'Complete' },
];

/** Only the two origins that actually belong in the contact book are offered here. */
const ORIGINS: { id: ContactSource; title: string; blurb: string }[] = [
  {
    id: 'own',
    title: 'My own contacts',
    blurb: 'People you already deal with — a backup, or a list from another system.',
  },
  {
    id: 'transferred',
    title: 'Transferred from another advisor',
    blurb:
      'An advisor left and their clients moved to you. These go straight into your book: they hold live policies and you have servicing obligations from day one.',
  },
  {
    id: 'canvassed',
    title: 'Roadshow or canvassing',
    blurb: 'Names collected in the field. Mostly unqualified, and many will not be real.',
  },
];

export default function UploadContactsWizard({
  contacts,
  onClose,
  onImport,
  onGoToCampaigns,
}: UploadContactsWizardProps) {
  const [step, setStep] = useState<Step>('origin');
  const [origin, setOrigin] = useState<ContactSource | null>(null);
  const [transferredFrom, setTransferredFrom] = useState('');
  const [transferredOn, setTransferredOn] = useState(todayISO());
  const [file, setFile] = useState<File | null>(null);
  const [sheet, setSheet] = useState<ParsedSheet | null>(null);
  const [matches, setMatches] = useState<ColumnMatch[]>([]);
  const [error, setError] = useState('');
  const [isParsing, setIsParsing] = useState(false);
  const [isMatching, setIsMatching] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [imported, setImported] = useState<{ added: number; skipped: number; duplicates: number }>(
    { added: 0, skipped: 0, duplicates: 0 },
  );

  const fileInputRef = useRef<HTMLInputElement>(null);

  const acceptFile = async (candidate: File) => {
    setError('');
    setIsParsing(true);
    try {
      const parsed = await parseSpreadsheet(candidate);
      setFile(candidate);
      setSheet(parsed);
    } catch (e) {
      setFile(null);
      setSheet(null);
      setError(e instanceof Error ? e.message : 'That file could not be read.');
    } finally {
      setIsParsing(false);
    }
  };

  const goToMatch = async () => {
    if (!sheet) return;
    setIsMatching(true);
    setStep('match');
    const suggested = await suggestColumnMapping(sheet.headers);
    setMatches(suggested);
    setIsMatching(false);
  };

  const missingRequired = REQUIRED_FIELDS.filter(
    (field) => !matches.some((m) => m.field === field),
  );

  const runImport = () => {
    if (!sheet) return;

    const cell = createCellReader<ContactField>(matches);

    const parsed: Omit<Contact, 'id'>[] = [];
    let skipped = 0;

    for (const row of sheet.rows) {
      const name = cell(row, 'name');
      const email = cell(row, 'email');
      const phone = cell(row, 'phone').replace(/[\s-]/g, '');

      // Same rule as the manual form: name, email and phone are mandatory.
      if (!name || !email || !phone) {
        skipped++;
        continue;
      }

      const rawLabel = cell(row, 'label').toLowerCase();
      const code = cell(row, 'countryCode');

      parsed.push({
        name,
        email,
        countryCode: code ? (code.startsWith('+') ? code : `+${code}`) : '+65',
        phone,
        dob: cell(row, 'dob') || undefined,
        nric: cell(row, 'nric') || undefined,
        // A transferred book is the firm's existing customers, so they arrive
        // as clients unless the sheet says otherwise. Everyone else defaults
        // to prospect.
        label:
          rawLabel.includes('client') || (origin === 'transferred' && !rawLabel)
            ? 'Client'
            : 'Prospect',
        source: origin ?? 'own',
        ...(origin === 'transferred'
          ? {
              transferredFrom: transferredFrom.trim() || undefined,
              transferredOn: transferredOn || undefined,
              introduced: false,
            }
          : {}),
      });
    }

    // Checked against the book and against the rest of the file, NRIC first.
    const { fresh, duplicates } = partitionIncoming(contacts, parsed);

    onImport(fresh);
    setImported({ added: fresh.length, skipped, duplicates: duplicates.length });
    setStep('complete');
  };

  const downloadTemplate = () => downloadCsv('contacts-template.csv', buildContactTemplateCsv());

  return (
    <div className="fixed inset-0 z-100 bg-white overflow-y-auto">
      <button
        onClick={onClose}
        className="fixed top-5 right-6 z-10 p-2 rounded-full text-faint hover:bg-gray-100 hover:text-body transition-colors"
        aria-label="Close"
      >
        <X size={20} />
      </button>

      <div className="mx-auto max-w-3xl px-6 py-10 flex flex-col gap-8">
        <Stepper current={step} />

        <h1 className="text-center text-[24px] font-semibold text-ink">Upload Contacts</h1>

        {step === 'origin' && (
          <OriginStep
            origin={origin}
            onPick={setOrigin}
            transferredFrom={transferredFrom}
            transferredOn={transferredOn}
            onChangeFrom={setTransferredFrom}
            onChangeOn={setTransferredOn}
            onGoToCampaigns={onGoToCampaigns}
          />
        )}

        {step === 'upload' && (
          <UploadStep
            file={file}
            sheet={sheet}
            error={error}
            isParsing={isParsing}
            isDragging={isDragging}
            setIsDragging={setIsDragging}
            fileInputRef={fileInputRef}
            onFile={acceptFile}
            onClear={() => {
              setFile(null);
              setSheet(null);
              setError('');
            }}
            onDownloadTemplate={downloadTemplate}
          />
        )}

        {step === 'match' && (
          <MatchStep
            sheet={sheet}
            matches={matches}
            isMatching={isMatching}
            missingRequired={missingRequired}
            onChange={(index, field) =>
              setMatches((prev) =>
                prev.map((m, i) => {
                  // A field can only be claimed once; release it elsewhere.
                  if (i === index) return { ...m, field, confident: true };
                  if (field !== 'ignore' && m.field === field) return { ...m, field: 'ignore' };
                  return m;
                }),
              )
            }
          />
        )}

        {step === 'complete' && <CompleteStep {...imported} />}

        <footer className="flex items-center justify-between border-t border-line pt-5">
          {step === 'complete' ? (
            <>
              <span />
              <Button variant="primary" onClick={onClose}>
                DONE
              </Button>
            </>
          ) : (
            <>
              <Button
                variant="ghost"
                onClick={
                  step === 'match'
                    ? () => setStep('upload')
                    : step === 'upload'
                      ? () => setStep('origin')
                      : onClose
                }
              >
                {step === 'origin' ? 'CANCEL' : 'BACK'}
              </Button>
              <Button
                variant="primary"
                disabled={
                  step === 'origin'
                    ? !origin || origin === 'canvassed'
                    : step === 'upload'
                      ? !sheet
                      : isMatching || missingRequired.length > 0
                }
                onClick={
                  step === 'origin'
                    ? () => setStep('upload')
                    : step === 'upload'
                      ? goToMatch
                      : runImport
                }
              >
                {step === 'match' ? 'IMPORT' : 'NEXT'}
              </Button>
            </>
          )}
        </footer>
      </div>
    </div>
  );
}

function Stepper({ current }: { current: Step }) {
  const currentIndex = STEPS.findIndex((s) => s.id === current);

  return (
    <div className="flex items-center justify-center gap-2">
      {STEPS.map((s, i) => {
        const isActive = i === currentIndex;
        const isDone = i < currentIndex;

        return (
          <div key={s.id} className="flex items-center gap-2">
            <span
              className={`w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-medium ${
                isActive || isDone ? 'bg-link text-white' : 'bg-gray-200 text-muted'
              }`}
            >
              {isDone ? '✓' : i + 1}
            </span>
            <span className={`text-[13px] ${isActive ? 'text-link font-medium' : 'text-muted'}`}>
              {s.label}
            </span>
            {i < STEPS.length - 1 && <span className="w-10 h-px bg-line mx-1" />}
          </div>
        );
      })}
    </div>
  );
}

function OriginStep({
  origin,
  onPick,
  transferredFrom,
  transferredOn,
  onChangeFrom,
  onChangeOn,
  onGoToCampaigns,
}: {
  origin: ContactSource | null;
  onPick: (source: ContactSource) => void;
  transferredFrom: string;
  transferredOn: string;
  onChangeFrom: (value: string) => void;
  onChangeOn: (value: string) => void;
  onGoToCampaigns: () => void;
}) {
  return (
    <div className="flex flex-col gap-4">
      <p className="text-center text-[13px] text-muted">
        Where did these names come from? This is recorded permanently and cannot be edited later.
      </p>

      <div className="flex flex-col gap-2.5">
        {ORIGINS.map((option) => {
          const isActive = origin === option.id;

          return (
            <button
              key={option.id}
              onClick={() => onPick(option.id)}
              className={`rounded-lg border px-4 py-3 text-left transition-colors ${
                isActive ? 'border-accent bg-accent-soft' : 'border-line hover:bg-gray-50'
              }`}
            >
              <span className="block text-[14px] font-medium text-ink">{option.title}</span>
              <span className="block text-[12px] text-muted mt-0.5">{option.blurb}</span>
            </button>
          );
        })}
      </div>

      {origin === 'transferred' && (
        <div className="rounded-lg border border-line p-4 flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <label className="field-label">Previous advisor</label>
            <input
              value={transferredFrom}
              onChange={(e) => onChangeFrom(e.target.value)}
              placeholder="Who did this book belong to?"
              className="input-field"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="field-label">Transfer date</label>
            <input
              type="date"
              value={transferredOn}
              onChange={(e) => onChangeOn(e.target.value)}
              className="input-field"
            />
          </div>
          <p className="text-[12px] text-muted">
            These arrive as clients and will be flagged for an introduction — they do not know your
            name yet.
          </p>
        </div>
      )}

      {origin === 'canvassed' && (
        <div className="rounded-lg border border-accent bg-accent-soft p-4 flex flex-col gap-3">
          <p className="text-[13px] text-body leading-relaxed">
            Canvassed names do not belong in your contact book yet. Most will never become
            anything, and importing them all makes your contact numbers meaningless.
          </p>
          <p className="text-[13px] text-body leading-relaxed">
            Upload the list onto a campaign instead — a lead list stays out of your contacts until
            you promote someone who is real. Work through it there, and promote the ones that turn
            into actual conversations.
          </p>
          <div>
            <Button variant="primary" onClick={onGoToCampaigns}>
              Take me to Campaigns
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function UploadStep({
  file,
  sheet,
  error,
  isParsing,
  isDragging,
  setIsDragging,
  fileInputRef,
  onFile,
  onClear,
  onDownloadTemplate,
}: {
  file: File | null;
  sheet: ParsedSheet | null;
  error: string;
  isParsing: boolean;
  isDragging: boolean;
  setIsDragging: (v: boolean) => void;
  fileInputRef: RefObject<HTMLInputElement | null>;
  onFile: (file: File) => void;
  onClear: () => void;
  onDownloadTemplate: () => void;
}) {
  return (
    <div className="flex flex-col gap-8">
      <section className="flex flex-col gap-3">
        <h2 className="text-[13px] font-semibold text-ink">How it works - We make it easy!</h2>

        <div className="rounded-lg bg-accent-soft/60 p-5 flex flex-col gap-4">
          <p className="text-[12.5px] text-body leading-relaxed">
            Simply upload your <span className="text-link">document of contacts</span> and let our
            AI do the heavy lifting. We'll{' '}
            <span className="text-link">automatically understand</span> your document structure and{' '}
            <span className="text-link">match the fields</span> for you!
          </p>

          <p className="text-[12.5px] font-semibold text-ink">
            Just make sure your file includes the three essential fields:
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {['Name', 'Email', 'Phone Number'].map((field) => (
              <div
                key={field}
                className="rounded-lg border border-line bg-white px-4 py-5 flex items-center gap-3"
              >
                <Users size={15} className="text-accent" />
                <span className="text-[13px] text-body">{field}</span>
              </div>
            ))}
          </div>

          <p className="text-center text-[11px] text-muted">
            Pro tip: Don't worry about formatting - our smart AI will figure it out!
          </p>
        </div>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-[13px] font-semibold text-ink">Upload Excel or CSV</h2>

        <div
          onDragOver={(e) => {
            e.preventDefault();
            setIsDragging(true);
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setIsDragging(false);
            const dropped = e.dataTransfer.files[0];
            if (dropped) onFile(dropped);
          }}
          className={`rounded-lg border bg-gray-50/70 px-6 py-10 flex flex-col items-center gap-2 transition-colors ${
            isDragging ? 'border-accent bg-accent-soft/40' : 'border-line'
          }`}
        >
          {isParsing ? (
            <span className="flex items-center gap-2 text-[13px] text-muted">
              <Loader2 size={16} className="animate-spin" />
              Reading file...
            </span>
          ) : sheet && file ? (
            <div className="flex flex-col items-center gap-2">
              <span className="flex items-center gap-2 text-[13px] font-medium text-ink">
                <CircleCheck size={16} className="text-success" />
                {file.name}
              </span>
              <span className="text-[12px] text-muted">
                {sheet.rows.length} rows · {sheet.headers.length} columns detected
              </span>
              <button onClick={onClear} className="text-[12px] text-link hover:underline">
                Choose a different file
              </button>
            </div>
          ) : (
            <>
              <div className="flex items-center gap-3">
                <Upload size={17} className="text-faint" />
                <span className="text-[13px] text-muted">Drag and drop or</span>
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="rounded-md border border-line bg-white px-3 py-1.5 text-[13px] text-body hover:bg-gray-50 transition-colors"
                >
                  Choose File
                </button>
              </div>
              <span className="text-[11px] text-muted">
                Supported formats: Excel (.xlsx, .xls) or CSV (.csv)
              </span>
              <span className="text-[11px] text-muted">
                Max file size {Math.round(MAX_UPLOAD_BYTES / 1024 / 1024)} MB
              </span>
            </>
          )}

          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx,.xls,.csv"
            className="hidden"
            onChange={(e) => {
              const chosen = e.target.files?.[0];
              if (chosen) onFile(chosen);
              e.target.value = '';
            }}
          />
        </div>

        {error && <p className="text-[12px] text-danger">{error}</p>}
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-[13px] font-semibold text-ink">Contacts Template</h2>

        <div className="rounded-lg border border-line px-5 py-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="w-9 h-9 rounded-full bg-accent-soft text-accent flex items-center justify-center shrink-0">
              <FileText size={16} />
            </span>
            <div className="flex flex-col">
              <span className="text-[13px] font-medium text-ink">Contacts Template</span>
              <span className="text-[12px] text-muted">
                CSV File containing sample data and accepted value
              </span>
            </div>
          </div>
          <Button variant="secondary" onClick={onDownloadTemplate}>
            <Download size={14} />
            Download
          </Button>
        </div>
      </section>
    </div>
  );
}

function MatchStep({
  sheet,
  matches,
  isMatching,
  missingRequired,
  onChange,
}: {
  sheet: ParsedSheet | null;
  matches: ColumnMatch[];
  isMatching: boolean;
  missingRequired: ContactField[];
  onChange: (index: number, field: ContactField) => void;
}) {
  if (isMatching || !sheet) {
    return (
      <div className="py-20 flex flex-col items-center gap-3">
        <Loader2 size={24} className="animate-spin text-accent" />
        <p className="text-[13px] text-muted">Matching your columns with AI...</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      <p className="text-[12.5px] text-muted">
        We matched your spreadsheet columns to contact fields. Review them and adjust anything we
        got wrong.
      </p>

      {missingRequired.length > 0 && (
        <div className="rounded-lg bg-danger-soft px-4 py-3 text-[12.5px] text-danger">
          Still needed before importing:{' '}
          {missingRequired.map((f) => CONTACT_FIELD_LABELS[f]).join(', ')}
        </div>
      )}

      <div className="rounded-lg border border-line overflow-hidden">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-line bg-gray-50">
              <th className="table-head">Column in your file</th>
              <th className="table-head">Sample data</th>
              <th className="table-head">Maps to</th>
            </tr>
          </thead>
          <tbody>
            {matches.map((match, i) => {
              const samples = sheet.rows
                .slice(0, 2)
                .map((row) => row[i])
                .filter(Boolean);

              return (
                <tr key={`${match.header}-${i}`} className="border-b border-line-soft last:border-0">
                  <td className="cell">
                    <span className="font-medium text-ink">{match.header || `Column ${i + 1}`}</span>
                    {!match.confident && (
                      <span className="ml-2 text-[11px] text-faint">no match found</span>
                    )}
                  </td>
                  <td className="cell text-muted">
                    {samples.length > 0 ? samples.join(', ') : EMPTY}
                  </td>
                  <td className="cell">
                    <select
                      value={match.field}
                      onChange={(e) => onChange(i, e.target.value as ContactField)}
                      className="w-full rounded-md border border-line px-2 py-1.5 text-[13px] outline-none focus:border-accent transition-colors"
                    >
                      {CONTACT_FIELDS.map((field) => (
                        <option key={field} value={field}>
                          {CONTACT_FIELD_LABELS[field]}
                        </option>
                      ))}
                    </select>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <p className="text-[11px] text-faint">
        {sheet.rows.length} rows found. Rows missing a name, email, or phone number are skipped.
      </p>
    </div>
  );
}

function CompleteStep({
  added,
  skipped,
  duplicates,
}: {
  added: number;
  skipped: number;
  duplicates: number;
}) {
  // Two different reasons a row did not import; reporting them together would
  // hide the fact that duplicates were matched rather than discarded as junk.
  const notes = [
    skipped > 0 &&
      `${skipped} row${skipped === 1 ? ' was' : 's were'} skipped for missing a name, email, or phone number.`,
    duplicates > 0 &&
      `${duplicates} ${duplicates === 1 ? 'was' : 'were'} already in your contacts and ${
        duplicates === 1 ? 'was' : 'were'
      } not added again.`,
  ].filter(Boolean) as string[];

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="py-16 flex flex-col items-center gap-4 text-center"
    >
      <span className="w-16 h-16 rounded-full bg-success-soft text-success flex items-center justify-center">
        <CircleCheck size={30} />
      </span>
      <h2 className="text-[19px] font-semibold text-ink">
        {added} contact{added === 1 ? '' : 's'} imported
      </h2>
      <div className="max-w-sm text-[13px] text-muted leading-relaxed flex flex-col gap-1">
        {notes.length === 0 ? (
          <p>Every row in your file was imported successfully.</p>
        ) : (
          notes.map((note) => <p key={note}>{note}</p>)
        )}
      </div>
    </motion.div>
  );
}
