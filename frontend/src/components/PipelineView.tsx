import { DragEvent, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import {
  ArrowLeftRight,
  Bookmark,
  Calendar,
  FileText,
  Flag,
  GripVertical,
  Plus,
  Search,
} from 'lucide-react';
import {
  ClosedOutcome,
  Contact,
  CONTACT_LABELS,
  ContactLabel,
  PipelineItem,
  PipelineStage,
} from '../types';
import { LabelChip, STAGE_META, StageChip } from '../ui/Chip';
import Modal, { ModalRow } from '../ui/Modal';
import Button from '../ui/Button';
import { formatDate } from '../lib/format';

interface PipelineViewProps {
  items: PipelineItem[];
  contacts: Contact[];
  onUpdateItem: (id: string, updates: Partial<PipelineItem>) => void;
  onArchiveItem: (id: string) => void;
  onRestoreItem: (id: string) => void;
  onAddContactToPipeline: (contact: Contact) => void;
  onViewContact: (contactId: string) => void;
}

const COLUMNS: { stage: PipelineStage; icon: typeof Bookmark }[] = [
  { stage: 'opportunities', icon: Bookmark },
  { stage: 'activities', icon: ArrowLeftRight },
  { stage: 'closed', icon: Flag },
];


export default function PipelineView({
  items,
  contacts,
  onUpdateItem,
  onArchiveItem,
  onRestoreItem,
  onAddContactToPipeline,
  onViewContact,
}: PipelineViewProps) {
  const [tab, setTab] = useState<'board' | 'archive'>('board');
  const [query, setQuery] = useState('');
  const [selectedItem, setSelectedItem] = useState<PipelineItem | null>(null);
  const [showPicker, setShowPicker] = useState(false);

  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [dragOverStage, setDragOverStage] = useState<PipelineStage | null>(null);

  /** Held while the advisor decides Won or Lost; cancelling leaves the card put. */
  const [pendingClose, setPendingClose] = useState<{ id: string; from: PipelineStage } | null>(
    null,
  );

  const active = useMemo(() => items.filter((i) => !i.archived), [items]);
  const archived = useMemo(() => items.filter((i) => i.archived), [items]);

  const matches = (item: PipelineItem) => {
    const q = query.trim().toLowerCase();
    return !q || item.contactName.toLowerCase().includes(q) || String(item.caseId).includes(q);
  };

  const visibleActive = active.filter(matches);

  /** Central rule for a stage change, whether from a drop or the case modal. */
  const moveToStage = (item: PipelineItem, stage: PipelineStage) => {
    if (stage === item.stage) return;

    if (stage === 'closed') {
      setPendingClose({ id: item.id, from: item.stage });
      return;
    }

    // Leaving the closed column discards the recorded outcome.
    onUpdateItem(item.id, { stage, closedOutcome: undefined });
  };

  const handleDrop = (stage: PipelineStage) => {
    setDragOverStage(null);
    const id = draggingId;
    setDraggingId(null);
    if (!id) return;

    const item = active.find((i) => i.id === id);
    if (item) moveToStage(item, stage);
  };

  return (
    <div className="flex flex-col gap-5">
      <h1 className="text-[24px] font-semibold text-ink">Pipeline</h1>

      <div className="flex items-center gap-8 border-b border-line">
        {([
          ['board', 'CRM Pipeline'],
          ['archive', `Archive${archived.length ? ` (${archived.length})` : ''}`],
        ] as ['board' | 'archive', string][]).map(([id, label]) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`relative -mb-px py-2.5 text-[13px] transition-colors border-b-2 ${
              tab === id
                ? 'text-link font-medium border-link'
                : 'text-muted hover:text-body border-transparent'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'board' ? (
        active.length === 0 ? (
          <EmptyState onAdd={() => setShowPicker(true)} />
        ) : (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="relative w-full max-w-md">
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search"
                  className="w-full rounded-full border border-line bg-white pl-4 pr-10 py-2 text-[13px] outline-none focus:border-accent transition-colors"
                />
                <Search size={15} className="absolute right-4 top-1/2 -translate-y-1/2 text-faint" />
              </div>

              <button
                onClick={() => setShowPicker(true)}
                className="rounded-md border border-link px-3.5 py-2 text-[13px] font-medium text-link hover:bg-link-soft transition-colors"
              >
                + Add to Pipeline
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-5 items-start">
              {COLUMNS.map(({ stage, icon: Icon }) => {
                const columnItems = visibleActive.filter((i) => i.stage === stage);
                const isTarget = dragOverStage === stage;

                return (
                  <div
                    key={stage}
                    onDragOver={(e) => {
                      e.preventDefault();
                      setDragOverStage(stage);
                    }}
                    onDragLeave={(e) => {
                      // Ignore bubbling from children still inside the column.
                      if (!e.currentTarget.contains(e.relatedTarget as Node)) {
                        setDragOverStage((prev) => (prev === stage ? null : prev));
                      }
                    }}
                    onDrop={() => handleDrop(stage)}
                    className={`rounded-lg border bg-white p-4 transition-colors ${
                      isTarget ? 'border-accent bg-accent-soft/30' : 'border-line'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-4">
                      <h2 className="text-[14px] font-semibold text-ink">
                        {STAGE_META[stage].name} ({columnItems.length})
                      </h2>
                      <span className="p-1.5 rounded bg-accent-soft text-accent">
                        <Icon size={14} />
                      </span>
                    </div>

                    <div className="flex flex-col gap-3 min-h-24">
                      <AnimatePresence mode="popLayout">
                        {columnItems.map((item) => (
                          <PipelineCard
                            key={item.id}
                            item={item}
                            isDragging={draggingId === item.id}
                            onDragStart={() => setDraggingId(item.id)}
                            onDragEnd={() => {
                              setDraggingId(null);
                              setDragOverStage(null);
                            }}
                            onClick={() => setSelectedItem(item)}
                          />
                        ))}
                      </AnimatePresence>

                      {columnItems.length === 0 && (
                        <div className="rounded-md border border-dashed border-line py-8 text-center text-[12px] text-faint">
                          {isTarget ? 'Drop here' : 'Nothing here yet'}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        )
      ) : (
        <ArchiveList items={archived} onRestore={onRestoreItem} />
      )}

      <AnimatePresence>
        {pendingClose && (
          <CloseOutcomeModal
            onCancel={() => setPendingClose(null)}
            onChoose={(outcome) => {
              onUpdateItem(pendingClose.id, { stage: 'closed', closedOutcome: outcome });
              setPendingClose(null);
              setSelectedItem(null);
            }}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {selectedItem && !pendingClose && (
          <PipelineCaseModal
            item={active.find((i) => i.id === selectedItem.id) ?? selectedItem}
            onClose={() => setSelectedItem(null)}
            onSave={(updates) => {
              onUpdateItem(selectedItem.id, updates);
              setSelectedItem(null);
            }}
            onRequestClose={(item) => setPendingClose({ id: item.id, from: item.stage })}
            onArchive={() => {
              onArchiveItem(selectedItem.id);
              setSelectedItem(null);
            }}
            onViewContact={() => {
              onViewContact(selectedItem.contactId);
              setSelectedItem(null);
            }}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {showPicker && (
          <ContactPickerModal
            contacts={contacts.filter((c) => !active.some((i) => i.contactId === c.id))}
            onClose={() => setShowPicker(false)}
            onPick={(contact) => {
              onAddContactToPipeline(contact);
              setShowPicker(false);
            }}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

function EmptyState({ onAdd }: { onAdd: () => void }) {
  return (
    <div className="rounded-lg bg-gradient-to-b from-gray-50 to-gray-100/70 border border-line py-24 flex flex-col items-center gap-4">
      <div className="w-20 h-20 rounded-full bg-white flex items-center justify-center text-faint">
        <FileText size={32} />
      </div>
      <h2 className="text-[19px] font-semibold text-ink">No deals yet</h2>
      <p className="max-w-xs text-center text-[13px] text-muted leading-relaxed">
        Start by adding contacts to your pipeline to track opportunities through their lifecycle.
      </p>
      <Button variant="primary" onClick={onAdd}>
        <Plus size={15} />
        Add to Pipeline
      </Button>
    </div>
  );
}

function PipelineCard({
  item,
  isDragging,
  onDragStart,
  onDragEnd,
  onClick,
}: {
  item: PipelineItem;
  isDragging: boolean;
  onDragStart: () => void;
  onDragEnd: () => void;
  onClick: () => void;
}) {
  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: isDragging ? 0.4 : 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.98 }}
      draggable
      onDragStart={(e) => {
        // Firefox needs data on the transfer object for a drag to begin.
        (e as unknown as DragEvent).dataTransfer?.setData('text/plain', item.id);
        onDragStart();
      }}
      onDragEnd={onDragEnd}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick();
        }
      }}
      className="w-full text-left rounded-lg border border-line bg-white hover:border-accent hover:shadow-sm transition-all overflow-hidden cursor-grab active:cursor-grabbing"
    >
      <div className="p-4 flex flex-col gap-2.5">
        <div className="flex items-start justify-between gap-2">
          <h3 className="text-[14px] font-semibold text-ink">{item.contactName}</h3>
          <GripVertical size={14} className="text-gray-300 shrink-0 mt-0.5" />
        </div>
        <div className="flex flex-wrap gap-2">
          <LabelChip label={item.contactLabel} />
          <StageChip stage={item.stage} outcome={item.closedOutcome} />
        </div>
      </div>

      <div className="border-t border-line-soft bg-gray-50/60 px-4 py-3 flex flex-col gap-1">
        <span className="field-label">Case ID</span>
        <span className="text-[15px] font-semibold text-link">{item.caseId}</span>
      </div>

      <div className="border-t border-line-soft px-4 py-3 grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-1">
          <span className="field-label">Start Date</span>
          <span className="flex items-center gap-1.5 text-[12px] text-body">
            <Calendar size={12} className="text-faint" />
            {formatDate(item.startDate)}
          </span>
        </div>
        <div className="flex flex-col gap-1">
          <span className="field-label">Due Date</span>
          <span className="flex items-center gap-1.5 text-[12px] text-body">
            <Calendar size={12} className="text-faint" />
            {formatDate(item.dueDate)}
          </span>
        </div>
      </div>
    </motion.div>
  );
}

function CloseOutcomeModal({
  onCancel,
  onChoose,
}: {
  onCancel: () => void;
  onChoose: (outcome: ClosedOutcome) => void;
}) {
  return (
    <Modal
      title="Close this case"
      onClose={onCancel}
      width="max-w-md"
      footer={
        <Button variant="ghost" onClick={onCancel}>
          CANCEL
        </Button>
      }
    >
      <div className="flex flex-col gap-4">
        <p className="text-[13px] text-muted">How did this opportunity end?</p>

        <div className="grid grid-cols-2 gap-3">
          <button
            onClick={() => onChoose('won')}
            className="rounded-lg border border-line px-4 py-5 flex flex-col items-center gap-1.5 hover:border-success hover:bg-success-soft/50 transition-colors"
          >
            <span className="text-[14px] font-semibold text-success">Closed - Won</span>
            <span className="text-[11px] text-muted">The client took up the plan</span>
          </button>

          <button
            onClick={() => onChoose('lost')}
            className="rounded-lg border border-line px-4 py-5 flex flex-col items-center gap-1.5 hover:border-danger hover:bg-danger-soft/50 transition-colors"
          >
            <span className="text-[14px] font-semibold text-danger">Closed - Lost</span>
            <span className="text-[11px] text-muted">The opportunity did not convert</span>
          </button>
        </div>

        <p className="text-[11px] text-faint">
          Cancelling leaves the case where it is.
        </p>
      </div>
    </Modal>
  );
}

function ArchiveList({
  items,
  onRestore,
}: {
  items: PipelineItem[];
  onRestore: (id: string) => void;
}) {
  if (items.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-line py-20 text-center text-[13px] text-muted">
        Nothing archived yet.
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-line bg-white overflow-hidden">
      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b border-line">
            <th className="table-head">Case ID</th>
            <th className="table-head">Contact</th>
            <th className="table-head">Stage when archived</th>
            <th className="table-head">Start Date</th>
            <th className="table-head text-right">Action</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id} className="border-b border-line-soft last:border-0">
              <td className="cell font-semibold text-link">{item.caseId}</td>
              <td className="cell text-body">{item.contactName}</td>
              <td className="cell">
                <StageChip stage={item.stage} outcome={item.closedOutcome} />
              </td>
              <td className="cell text-body">{formatDate(item.startDate)}</td>
              <td className="cell text-right">
                <button
                  onClick={() => onRestore(item.id)}
                  className="text-[13px] text-link hover:underline"
                >
                  Restore
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PipelineCaseModal({
  item,
  onClose,
  onSave,
  onRequestClose,
  onArchive,
  onViewContact,
}: {
  item: PipelineItem;
  onClose: () => void;
  onSave: (updates: Partial<PipelineItem>) => void;
  onRequestClose: (item: PipelineItem) => void;
  onArchive: () => void;
  onViewContact: () => void;
}) {
  const [label, setLabel] = useState<ContactLabel | ''>(item.contactLabel ?? '');
  const [stage, setStage] = useState<PipelineStage>(item.stage);
  const [description, setDescription] = useState(item.description ?? '');

  const dirty =
    label !== (item.contactLabel ?? '') ||
    stage !== item.stage ||
    description !== (item.description ?? '');

  const handleSave = () => {
    // Closing needs an outcome, so hand off to the Won/Lost prompt instead.
    if (stage === 'closed' && item.stage !== 'closed') {
      onSave({ contactLabel: (label || undefined) as ContactLabel, description });
      onRequestClose(item);
      return;
    }

    onSave({
      contactLabel: (label || undefined) as ContactLabel,
      stage,
      description,
      closedOutcome: stage === 'closed' ? item.closedOutcome : undefined,
    });
  };

  return (
    <Modal
      title={`Pipeline Case: ${item.caseId}`}
      onClose={onClose}
      footer={
        <>
          <Button variant="danger" onClick={onArchive} className="mr-auto">
            Archive
          </Button>
          <Button variant="ghost" onClick={onClose}>
            CLOSE
          </Button>
          <Button variant="primary" disabled={!dirty} onClick={handleSave}>
            SAVE
          </Button>
        </>
      }
    >
      <div className="flex flex-col">
        <ModalRow label="Contact">
          <button onClick={onViewContact} className="text-link hover:underline">
            {item.contactName}
          </button>
        </ModalRow>

        <ModalRow label="Start Date">{formatDate(item.startDate)}</ModalRow>
        <ModalRow label="Due Date">{formatDate(item.dueDate)}</ModalRow>

        <ModalRow label="Label">
          <select
            value={label}
            onChange={(e) => setLabel(e.target.value as ContactLabel | '')}
            className="rounded border border-accent-soft bg-accent-soft px-2 py-1 text-[12px] font-medium text-accent-hover outline-none cursor-pointer"
          >
            <option value="">Unlabelled</option>
            {CONTACT_LABELS.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
        </ModalRow>

        <ModalRow label="Pipeline Status">
          <select
            value={stage}
            onChange={(e) => setStage(e.target.value as PipelineStage)}
            className="rounded border border-purple-soft bg-purple-soft px-2 py-1 text-[12px] font-medium text-purple outline-none cursor-pointer"
          >
            {Object.entries(STAGE_META).map(([id, meta]) => (
              <option key={id} value={id}>
                {meta.name}
              </option>
            ))}
          </select>
          {item.stage === 'closed' && item.closedOutcome && (
            <span className="ml-2 text-[11px] text-muted">
              Recorded as {item.closedOutcome === 'won' ? 'Won' : 'Lost'}
            </span>
          )}
        </ModalRow>

        <ModalRow label="Description">
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Enter a description..."
            className="input-field h-32 resize-none"
          />
        </ModalRow>
      </div>
    </Modal>
  );
}

function ContactPickerModal({
  contacts,
  onClose,
  onPick,
}: {
  contacts: Contact[];
  onClose: () => void;
  onPick: (contact: Contact) => void;
}) {
  const [query, setQuery] = useState('');
  const q = query.trim().toLowerCase();
  const results = contacts.filter(
    (c) => !q || c.name.toLowerCase().includes(q) || c.email.toLowerCase().includes(q),
  );

  return (
    <Modal
      title="Add to Pipeline"
      onClose={onClose}
      footer={
        <Button variant="ghost" onClick={onClose}>
          CLOSE
        </Button>
      }
    >
      <div className="flex flex-col gap-3">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search contacts..."
          className="input-field"
          autoFocus
        />

        <div className="max-h-72 overflow-y-auto rounded-md border border-line divide-y divide-line-soft">
          {results.map((c) => (
            <button
              key={c.id}
              onClick={() => onPick(c)}
              className="w-full px-3 py-2.5 flex items-center justify-between gap-3 text-left hover:bg-gray-50 transition-colors"
            >
              <div className="min-w-0">
                <p className="text-[13px] font-medium text-ink truncate">{c.name}</p>
                <p className="text-[12px] text-muted truncate">{c.email}</p>
              </div>
              <LabelChip label={c.label} />
            </button>
          ))}

          {results.length === 0 && (
            <p className="px-3 py-8 text-center text-[13px] text-muted">
              Every matching contact is already in the pipeline.
            </p>
          )}
        </div>
      </div>
    </Modal>
  );
}
