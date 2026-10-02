import { useState } from 'react';
import { Contact, Task, TASK_TYPES, TaskStatus, TaskType } from '../types';
import Modal, { ModalRow } from '../ui/Modal';
import Button from '../ui/Button';
import { addDaysISO, todayISO } from '../lib/format';

interface AddTaskModalProps {
  contacts: Contact[];
  initial?: Task | null;
  onClose: () => void;
  onSave: (task: Omit<Task, 'id' | 'status'> & { status: TaskStatus }) => void;
}


export default function AddTaskModal({ contacts, initial, onClose, onSave }: AddTaskModalProps) {
  const [title, setTitle] = useState(initial?.title ?? '');
  const [contactId, setContactId] = useState(initial?.contactId ?? '');
  const [type, setType] = useState<TaskType>(initial?.type ?? 'Manual');
  const [status, setStatus] = useState<TaskStatus>(initial?.status ?? 'todo');
  const [startDate, setStartDate] = useState(initial?.startDate ?? todayISO());
  const [dueDate, setDueDate] = useState(initial?.dueDate ?? addDaysISO(todayISO(), 7));
  const [description, setDescription] = useState(initial?.description ?? '');

  const datesInvalid = Boolean(startDate && dueDate && dueDate < startDate);
  const canSave = title.trim().length > 0 && !datesInvalid;

  const handleSave = () => {
    if (!canSave) return;
    const contact = contacts.find((c) => c.id === contactId);
    onSave({
      title: title.trim(),
      contactId: contact?.id ?? '',
      contactName: contact?.name ?? '',
      type,
      status,
      startDate,
      dueDate,
      description: description.trim(),
    });
  };

  return (
    <Modal
      title={initial ? 'Edit Task' : 'Add Task'}
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
        <ModalRow label="Task Title">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Collect signed client agreement"
            className="input-field"
          />
        </ModalRow>

        <ModalRow label="Contact">
          <select
            value={contactId}
            onChange={(e) => setContactId(e.target.value)}
            className="input-field"
          >
            <option value="">Not linked to a contact</option>
            {contacts.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </ModalRow>

        <ModalRow label="Task Type">
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
        </ModalRow>

        <ModalRow label="Status">
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value as TaskStatus)}
            className="input-field"
          >
            <option value="todo">To-Do</option>
            <option value="done">Done</option>
          </select>
        </ModalRow>

        <ModalRow label="Start Date">
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="input-field"
          />
        </ModalRow>

        <ModalRow label="Due Date">
          <input
            type="date"
            value={dueDate}
            min={startDate || undefined}
            onChange={(e) => setDueDate(e.target.value)}
            className="input-field"
          />
          {datesInvalid && (
            <p className="mt-1 text-[11px] text-danger">
              The due date cannot fall before the start date.
            </p>
          )}
        </ModalRow>

        <ModalRow label="Description">
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Add any supporting detail..."
            className="input-field h-28 resize-none"
          />
        </ModalRow>
      </div>
    </Modal>
  );
}
