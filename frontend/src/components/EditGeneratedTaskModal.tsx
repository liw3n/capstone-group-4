import { ReactNode, useState } from 'react';
import { TASK_TYPES, TaskType } from '../types';
import { GeneratedTask } from '../services/ai';
import Modal from '../ui/Modal';
import Button from '../ui/Button';

interface EditGeneratedTaskModalProps {
  task: GeneratedTask;
  onClose: () => void;
  onSave: (task: GeneratedTask) => void;
}


export default function EditGeneratedTaskModal({
  task,
  onClose,
  onSave,
}: EditGeneratedTaskModalProps) {
  const [title, setTitle] = useState(task.title);
  const [type, setType] = useState<TaskType>(task.type);
  const [startDate, setStartDate] = useState(task.startDate);
  const [dueDate, setDueDate] = useState(task.dueDate);
  const [description, setDescription] = useState(task.description);

  // The reference design lets a due date precede its start date; that is a bug.
  const datesInvalid = Boolean(startDate && dueDate && dueDate < startDate);
  const canSave = title.trim().length > 0 && !datesInvalid;

  return (
    <Modal
      title="Edit To-Do Task"
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            CANCEL
          </Button>
          <Button
            variant="primary"
            disabled={!canSave}
            onClick={() =>
              onSave({ ...task, title: title.trim(), type, startDate, dueDate, description })
            }
          >
            SAVE
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <Field label="Task Title">
          <input value={title} onChange={(e) => setTitle(e.target.value)} className="input-field" />
        </Field>

        <Field label="Task Type">
          <select
            value={type}
            onChange={(e) => setType(e.target.value as TaskType)}
            className="input-field"
          >
            {TASK_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </Field>

        <div className="grid grid-cols-2 gap-4">
          <Field label="Start Date">
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="input-field"
            />
          </Field>
          <Field label="Due Date">
            <input
              type="date"
              value={dueDate}
              min={startDate || undefined}
              onChange={(e) => setDueDate(e.target.value)}
              className="input-field"
            />
          </Field>
        </div>

        {datesInvalid && (
          <p className="text-[11px] text-danger">The due date cannot fall before the start date.</p>
        )}

        <Field label="Description">
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="input-field h-24 resize-none"
          />
        </Field>
      </div>
    </Modal>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-[12px] text-body">{label}</label>
      {children}
    </div>
  );
}
