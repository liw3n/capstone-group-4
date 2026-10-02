import { ExternalLink } from 'lucide-react';
import { Task } from '../types';
import Modal, { ModalRow } from '../ui/Modal';
import Button from '../ui/Button';
import { TaskTypeChip } from '../ui/Chip';
import { dueLabel, EMPTY, formatDate, isOverdue } from '../lib/format';

interface TaskDetailModalProps {
  task: Task;
  onClose: () => void;
  onToggleStatus: () => void;
  onEdit: () => void;
  onViewContact: () => void;
}

export default function TaskDetailModal({
  task,
  onClose,
  onToggleStatus,
  onEdit,
  onViewContact,
}: TaskDetailModalProps) {
  return (
    <Modal
      title={task.title}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            CLOSE
          </Button>
          <Button variant="secondary" onClick={onToggleStatus}>
            {task.status === 'todo' ? 'Mark as done' : 'Reopen'}
          </Button>
          <Button variant="primary" onClick={onEdit}>
            EDIT TASK
          </Button>
        </>
      }
    >
      <div className="flex flex-col">
        <ModalRow label="Contact">
          {task.contactId ? (
            <button
              onClick={onViewContact}
              className="inline-flex items-center gap-1.5 text-link hover:underline"
            >
              {task.contactName}
              <ExternalLink size={13} />
            </button>
          ) : (
            <span className="text-faint">{EMPTY}</span>
          )}
        </ModalRow>

        <ModalRow label="Task Type">
          <TaskTypeChip type={task.type} />
        </ModalRow>

        <ModalRow label="Status">{task.status === 'todo' ? 'To-Do' : 'Done'}</ModalRow>

        <ModalRow label="Start Date">{formatDate(task.startDate)}</ModalRow>

        <ModalRow label="Due Date">{formatDate(task.dueDate)}</ModalRow>

        <ModalRow label="Due in">
          <span className={isOverdue(task.dueDate) && task.status === 'todo' ? 'text-danger' : ''}>
            {dueLabel(task.dueDate)}
          </span>
        </ModalRow>

        <ModalRow label="Description">
          <p className="leading-relaxed">
            {task.description || <span className="text-faint">No description provided.</span>}
          </p>
        </ModalRow>
      </div>
    </Modal>
  );
}
