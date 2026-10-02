import { useState } from 'react';
import { MeetingSummary } from '../types';
import Modal, { ModalRow } from '../ui/Modal';
import Button from '../ui/Button';
import { newId, todayISO } from '../lib/format';

interface EditSummaryModalProps {
  initial?: MeetingSummary | null;
  onClose: () => void;
  onSave: (summary: MeetingSummary) => void;
}

export default function EditSummaryModal({
  initial,
  onClose,
  onSave,
}: EditSummaryModalProps) {
  const [date, setDate] = useState(initial?.date ?? todayISO());
  const [title, setTitle] = useState(initial?.title ?? '');
  const [description, setDescription] = useState(initial?.description ?? '');
  const [tasks, setTasks] = useState((initial?.tasks ?? []).join('\n'));

  const canSave = title.trim().length > 0 && description.trim().length > 0;

  const handleSave = () => {
    if (!canSave) return;
    onSave({
      id: initial?.id ?? newId(),
      date,
      title: title.trim(),
      description: description.trim(),
      tasks: tasks
        .split('\n')
        .map((t) => t.trim())
        .filter(Boolean),
    });
  };

  return (
    <Modal
      title="Edit Meeting Summary"
      onClose={onClose}
      width="max-w-xl"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            CLOSE
          </Button>
          <Button variant="primary" onClick={handleSave} disabled={!canSave}>
            SAVE
          </Button>
        </>
      }
    >
      <div className="flex flex-col">
        <ModalRow label="Date">
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="input-field"
          />
        </ModalRow>

        <ModalRow label="Title">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Conducted initial discovery"
            className="input-field"
          />
        </ModalRow>

        <ModalRow label="Summary">
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What was discussed and agreed?"
            className="input-field h-36 resize-none"
          />
        </ModalRow>

        <ModalRow label="To-Do">
          <textarea
            value={tasks}
            onChange={(e) => setTasks(e.target.value)}
            placeholder={'One action item per line'}
            className="input-field h-24 resize-none"
          />
          <p className="mt-1.5 text-[11px] text-faint">
            Each line becomes a task assigned to this contact.
          </p>
        </ModalRow>
      </div>
    </Modal>
  );
}
