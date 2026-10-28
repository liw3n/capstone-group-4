import { ReactNode } from 'react';
import { CampaignCriteria, NumericRange } from '../types';
import {
  AGE_GROUPS,
  AGE_GROUP_LABELS,
  CASH_BANDS,
  CASH_BAND_LABELS,
  GENDERS,
  GENDER_LABELS,
  hasRange,
  normalizeCampaignCriteria,
} from '../lib/targeting';

interface PickerProps {
  criteria: CampaignCriteria;
  onChange: (criteria: CampaignCriteria) => void;
  allowCustomRanges?: boolean;
}

const chipClass = (isOn: boolean) =>
  `rounded-full border px-3 py-1.5 text-[12px] transition-colors ${
    isOn ? 'border-accent bg-accent text-white' : 'border-line bg-white text-body hover:bg-gray-50'
  }`;

const numberClass =
  'w-full rounded-md border border-line px-2.5 py-1.5 text-[12px] outline-none focus:border-accent transition-colors';

/** Blank input means "no bound", which is different from zero. */
function toBound(value: string): number | undefined {
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : undefined;
}

function rangeIsBackwards(range: NumericRange | undefined): boolean {
  return Boolean(
    range && range.min !== undefined && range.max !== undefined && range.min > range.max,
  );
}

function Dimension({
  title,
  note,
  children,
}: {
  title: string;
  note: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-[13px] font-medium text-ink">{title}</span>
        <span className="text-[11px] text-faint">{note}</span>
      </div>
      {children}
    </div>
  );
}

/**
 * Module level, not nested inside CriteriaPicker. A component declared inside
 * another component is a new type on every render, so React unmounts and
 * remounts it — which in a text input means losing focus after every keystroke.
 */
function RangeInputs({
  keyName,
  range,
  prefix,
  minPlaceholder,
  maxPlaceholder,
  step,
  onSet,
  onClear,
}: {
  keyName: 'ageRange' | 'cashRange';
  range: NumericRange | undefined;
  prefix?: string;
  minPlaceholder: string;
  maxPlaceholder: string;
  step?: number;
  onSet: (bound: 'min' | 'max', raw: string) => void;
  onClear: () => void;
}) {
  const isAge = keyName === 'ageRange';

  return (
    <div className="flex flex-col gap-1">
      <div className="flex flex-wrap items-center gap-2">
        <span className="w-[76px] shrink-0 text-[11px] text-faint">Custom range</span>
        <div className="flex items-center gap-1.5">
          {prefix && <span className="text-[11px] text-faint">{prefix}</span>}
          <input
            type="number"
            min={0}
            step={step}
            value={range?.min ?? ''}
            onChange={(e) => onSet('min', e.target.value)}
            placeholder={minPlaceholder}
            aria-label={isAge ? 'Minimum age' : 'Minimum amount'}
            className={`${numberClass} w-24`}
          />
          <span className="text-[11px] text-faint">to</span>
          {prefix && <span className="text-[11px] text-faint">{prefix}</span>}
          <input
            type="number"
            min={0}
            step={step}
            value={range?.max ?? ''}
            onChange={(e) => onSet('max', e.target.value)}
            placeholder={maxPlaceholder}
            aria-label={isAge ? 'Maximum age' : 'Maximum amount'}
            className={`${numberClass} w-28`}
          />
        </div>
      </div>

      {rangeIsBackwards(range) && (
        <p className="text-[11px] text-danger">
          The lower bound is above the upper bound, so nothing can match.
        </p>
      )}
      {hasRange(range) && (
        <button
          type="button"
          onClick={onClear}
          className="w-fit text-[11px] text-link hover:underline"
        >
          Clear custom range
        </button>
      )}
    </div>
  );
}

/**
 * Age bands and custom age ranges are alternative filters. Selecting one clears
 * the other so the displayed age criteria match the audience filter.
 */
export function CriteriaPicker({
  criteria: storedCriteria,
  onChange,
  allowCustomRanges = true,
}: PickerProps) {
  const criteria = normalizeCampaignCriteria(storedCriteria);
  const toggle = (key: 'ageGroups' | 'genders' | 'cashBands', value: string) => {
    const current = criteria[key] as string[];
    const next = current.includes(value)
      ? current.filter((v) => v !== value)
      : [...current, value];
    onChange({
      ...criteria,
      [key]: next,
      ...(key === 'ageGroups' ? { ageRange: undefined } : {}),
    } as CampaignCriteria);
  };

  const setRange = (key: 'ageRange' | 'cashRange', bound: 'min' | 'max', raw: string) => {
    const next: NumericRange = { ...(criteria[key] ?? {}), [bound]: toBound(raw) };
    const cleared = next.min === undefined && next.max === undefined;
    onChange({
      ...criteria,
      [key]: cleared ? undefined : next,
      ...(key === 'ageRange' ? { ageGroups: [] } : {}),
    });
  };

  const noteFor = (count: number, range?: NumericRange) => {
    if (count === 0 && !hasRange(range)) return 'Any — not filtered';
    const parts = [];
    if (count > 0) parts.push(`${count} selected`);
    if (hasRange(range)) parts.push('custom range');
    return parts.join(' + ');
  };

  return (
    <div className="flex flex-col gap-5">
      <Dimension
        title="Target age group"
        note={
          criteria.ageGroups.length > 0 && hasRange(criteria.ageRange)
            ? `${criteria.ageGroups.length} selected · custom range ignored`
            : noteFor(criteria.ageGroups.length, criteria.ageRange)
        }
      >
        <div className="flex flex-wrap gap-2">
          {AGE_GROUPS.map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => toggle('ageGroups', value)}
              aria-pressed={criteria.ageGroups.includes(value)}
              className={chipClass(criteria.ageGroups.includes(value))}
            >
              {AGE_GROUP_LABELS[value]}
            </button>
          ))}
        </div>
        {allowCustomRanges && (
          <RangeInputs
            keyName="ageRange"
            range={criteria.ageRange}
            minPlaceholder="42"
            maxPlaceholder="47"
            step={1}
            onSet={(bound, raw) => setRange('ageRange', bound, raw)}
            onClear={() => onChange({ ...criteria, ageRange: undefined })}
          />
        )}
      </Dimension>

      <Dimension title="Target demographic" note={noteFor(criteria.genders.length)}>
        <div className="flex flex-wrap gap-2">
          {GENDERS.map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => toggle('genders', value)}
              aria-pressed={criteria.genders.includes(value)}
              className={chipClass(criteria.genders.includes(value))}
            >
              {GENDER_LABELS[value]}
            </button>
          ))}
        </div>
      </Dimension>

      <Dimension
        title="Target cash availability"
        note={noteFor(criteria.cashBands.length, criteria.cashRange)}
      >
        <div className="flex flex-wrap gap-2">
          {CASH_BANDS.map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => toggle('cashBands', value)}
              aria-pressed={criteria.cashBands.includes(value)}
              className={chipClass(criteria.cashBands.includes(value))}
            >
              {CASH_BAND_LABELS[value]}
            </button>
          ))}
        </div>
        {allowCustomRanges && (
          <RangeInputs
            keyName="cashRange"
            range={criteria.cashRange}
            prefix="S$"
            minPlaceholder="300000"
            maxPlaceholder="450000"
            step={1000}
            onSet={(bound, raw) => setRange('cashRange', bound, raw)}
            onClear={() => onChange({ ...criteria, cashRange: undefined })}
          />
        )}
      </Dimension>
    </div>
  );
}

/** "42 - 47", "45 and above", "up to 60" */
function describeRange(range: NumericRange, prefix = ''): string {
  const fmt = (n: number) => `${prefix}${n.toLocaleString('en-SG')}`;
  if (range.min !== undefined && range.max !== undefined) {
    return `${fmt(range.min)} - ${fmt(range.max)}`;
  }
  if (range.min !== undefined) return `${fmt(range.min)} and above`;
  return `up to ${fmt(range.max!)}`;
}

/** Read-only rendering of the same criteria, for list rows and detail headers. */
export function CriteriaSummary({ criteria: storedCriteria }: { criteria: CampaignCriteria }) {
  const criteria = normalizeCampaignCriteria(storedCriteria);
  const rows: { title: string; values: string[] }[] = [];

  const ageValues = [
    ...criteria.ageGroups.map((v) => AGE_GROUP_LABELS[v] ?? v),
    ...(criteria.ageGroups.length === 0 && hasRange(criteria.ageRange)
      ? [describeRange(criteria.ageRange!)]
      : []),
  ];
  if (ageValues.length > 0) rows.push({ title: 'Target age group', values: ageValues });

  if (criteria.genders.length > 0) {
    rows.push({
      title: 'Target demographic',
      values: criteria.genders.map((v) => GENDER_LABELS[v]),
    });
  }

  const cashValues = [
    ...criteria.cashBands.map((v) => CASH_BAND_LABELS[v] ?? v),
    ...(hasRange(criteria.cashRange) ? [describeRange(criteria.cashRange!, 'S$')] : []),
  ];
  if (cashValues.length > 0) rows.push({ title: 'Target cash availability', values: cashValues });

  if (rows.length === 0) {
    return <p className="text-[12px] text-muted">No criteria — every contact in the book.</p>;
  }

  return (
    <div className="flex flex-col gap-2">
      {rows.map((row) => (
        <div key={row.title} className="flex flex-wrap items-center gap-1.5">
          <span className="w-[104px] shrink-0 text-[11px] text-faint">{row.title}</span>
          {row.values.map((value) => (
            <span
              key={value}
              className="inline-flex items-center rounded bg-line-soft px-2 py-0.5 text-[11px] font-medium text-body"
            >
              {value}
            </span>
          ))}
        </div>
      ))}
    </div>
  );
}
