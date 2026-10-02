import {
  ClosedOutcome,
  Contact,
  ContactLabel,
  ContactSource,
  PipelineItem,
  PipelineStage,
  TaskType,
} from '../types';

const base =
  'inline-flex items-center rounded px-2 py-0.5 text-[11px] font-medium whitespace-nowrap';

const LABEL_STYLES: Record<ContactLabel, string> = {
  Prospect: 'bg-accent-soft text-accent-hover',
  Client: 'bg-success-soft text-success',
};

export function LabelChip({ label }: { label?: ContactLabel }) {
  if (!label) return null;
  return <span className={`${base} ${LABEL_STYLES[label]}`}>{label}</span>;
}

const SOURCE_LABELS: Record<ContactSource, string> = {
  own: 'Own contact',
  transferred: 'Transferred',
  canvassed: 'Canvassed',
  referral: 'Referral',
};

/**
 * Only shown for names the advisor did not win themselves. Marking every
 * ordinary contact "Own contact" would be noise, so 'own' renders nothing.
 */
export function SourceChip({ contact }: { contact: Pick<Contact, 'source' | 'transferredFrom'> }) {
  const source = contact.source ?? 'own';
  if (source === 'own') return null;

  const title =
    source === 'transferred' && contact.transferredFrom
      ? `Transferred from ${contact.transferredFrom}`
      : SOURCE_LABELS[source];

  return (
    <span className={`${base} bg-gray-100 text-muted`} title={title}>
      {SOURCE_LABELS[source]}
    </span>
  );
}

export const STAGE_META: Record<PipelineStage, { name: string; chip: string }> = {
  opportunities: { name: 'Opportunities', chip: 'bg-purple-soft text-purple' },
  activities: { name: 'Activities', chip: 'bg-pink-soft text-pink' },
  closed: { name: 'Closed', chip: 'bg-line-soft text-muted' },
};

const OUTCOME_META: Record<ClosedOutcome, { name: string; chip: string }> = {
  won: { name: 'Closed - Won', chip: 'bg-success-soft text-success' },
  lost: { name: 'Closed - Lost', chip: 'bg-danger-soft text-danger' },
};

/** Reads the outcome when the case is closed, otherwise falls back to the stage. */
export function stageLabel(item: Pick<PipelineItem, 'stage' | 'closedOutcome'>): string {
  if (item.stage === 'closed' && item.closedOutcome) return OUTCOME_META[item.closedOutcome].name;
  return STAGE_META[item.stage].name;
}

export function StageChip({
  stage,
  outcome,
}: {
  stage: PipelineStage;
  outcome?: ClosedOutcome;
}) {
  const meta = stage === 'closed' && outcome ? OUTCOME_META[outcome] : STAGE_META[stage];
  return <span className={`${base} ${meta.chip}`}>{meta.name}</span>;
}

const TYPE_STYLES: Record<TaskType, string> = {
  CRM: 'bg-purple-soft text-purple',
  Compliance: 'bg-link-soft text-link',
  Campaign: 'bg-accent-soft text-accent-hover',
  Manual: 'bg-line-soft text-muted',
};

export function TaskTypeChip({ type }: { type: TaskType }) {
  return <span className={`${base} ${TYPE_STYLES[type]}`}>{type}</span>;
}
