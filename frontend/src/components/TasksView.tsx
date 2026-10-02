import { ReactNode, useEffect, useMemo, useState } from 'react';
import { AnimatePresence } from 'motion/react';
import { ChevronDown, ChevronLeft, ChevronRight, Plus, Search } from 'lucide-react';
import { Contact, Task, TASK_TYPES, TaskStatus, TaskType } from '../types';
import { TaskTypeChip } from '../ui/Chip';
import Button from '../ui/Button';
import AddTaskModal from './AddTaskModal';
import TaskDetailModal from './TaskDetailModal';
import { dueLabel, EMPTY, isOverdue } from '../lib/format';

interface TasksViewProps {
  tasks: Task[];
  contacts: Contact[];
  onToggleStatus: (id: string) => void;
  onViewContact: (contactId: string) => void;
  onAddTask: (task: Omit<Task, 'id' | 'status'>) => void;
  onUpdateTask: (id: string, updates: Partial<Task>) => void;
}

const PAGE_SIZE = 10;

export default function TasksView({
  tasks,
  contacts,
  onToggleStatus,
  onViewContact,
  onAddTask,
  onUpdateTask,
}: TasksViewProps) {
  const [tab, setTab] = useState<TaskStatus>('todo');
  const [query, setQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState<TaskType[]>([]);
  const [contactFilter, setContactFilter] = useState<string[]>([]);
  const [contactQuery, setContactQuery] = useState('');
  const [openMenu, setOpenMenu] = useState<'type' | 'contact' | null>(null);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string[]>([]);

  const [showAddModal, setShowAddModal] = useState(false);
  const [editingTask, setEditingTask] = useState<Task | null>(null);
  const [detailTask, setDetailTask] = useState<Task | null>(null);

  const todoCount = tasks.filter((t) => t.status === 'todo').length;
  const doneCount = tasks.filter((t) => t.status === 'done').length;

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return tasks
      .filter((t) => t.status === tab)
      .filter((t) => {
        const matchesQuery =
          !q ||
          t.title.toLowerCase().includes(q) ||
          t.description.toLowerCase().includes(q) ||
          t.contactName.toLowerCase().includes(q);
        const matchesType = typeFilter.length === 0 || typeFilter.includes(t.type);
        const matchesContact =
          contactFilter.length === 0 || contactFilter.includes(t.contactId);
        return matchesQuery && matchesType && matchesContact;
      })
      .sort((a, b) => a.dueDate.localeCompare(b.dueDate));
  }, [tasks, tab, query, typeFilter, contactFilter]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));

  // Keep the page in range when filters shrink the result set.
  useEffect(() => {
    if (page > pageCount) setPage(1);
  }, [page, pageCount]);

  const pageRows = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const allPageSelected = pageRows.length > 0 && pageRows.every((t) => selected.includes(t.id));

  const resetToFirstPage = () => setPage(1);

  const contactOptions = contacts.filter((c) =>
    c.name.toLowerCase().includes(contactQuery.trim().toLowerCase()),
  );

  return (
    <div className="flex flex-col gap-5">
      <h1 className="text-[24px] font-semibold text-ink">Tasks</h1>

      <div className="flex items-center gap-8 border-b border-line">
        {([
          ['todo', `To-Do (${todoCount})`],
          ['done', `Done (${doneCount})`],
        ] as [TaskStatus, string][]).map(([id, label]) => (
          <button
            key={id}
            onClick={() => {
              setTab(id);
              resetToFirstPage();
            }}
            className={`relative -mb-px py-2.5 text-[13px] transition-colors ${
              tab === id
                ? 'text-accent font-medium border-b-2 border-accent'
                : 'text-muted hover:text-body border-b-2 border-transparent'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative w-full max-w-sm">
          <input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              resetToFirstPage();
            }}
            placeholder="Search by title, summary, or contact..."
            className="w-full rounded-full border border-line bg-white pl-4 pr-10 py-2 text-[13px] outline-none focus:border-accent transition-colors"
          />
          <Search size={15} className="absolute right-4 top-1/2 -translate-y-1/2 text-faint" />
        </div>

        <Button variant="secondary" onClick={() => setShowAddModal(true)}>
          <Plus size={15} />
          Add Task
        </Button>

        <FilterMenu
          label="Task Type"
          open={openMenu === 'type'}
          activeCount={typeFilter.length}
          onToggle={() => setOpenMenu(openMenu === 'type' ? null : 'type')}
        >
          {TASK_TYPES.map((type) => (
            <label
              key={type}
              className="flex items-center gap-2 px-3 py-2 text-[13px] hover:bg-gray-50 cursor-pointer"
            >
              <input
                type="checkbox"
                className="accent-accent"
                checked={typeFilter.includes(type)}
                onChange={() => {
                  setTypeFilter((prev) =>
                    prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type],
                  );
                  resetToFirstPage();
                }}
              />
              {type}
            </label>
          ))}
        </FilterMenu>

        <FilterMenu
          label="Contacts"
          open={openMenu === 'contact'}
          activeCount={contactFilter.length}
          onToggle={() => setOpenMenu(openMenu === 'contact' ? null : 'contact')}
          width="w-64"
        >
          <div className="p-2 border-b border-line-soft">
            <input
              value={contactQuery}
              onChange={(e) => setContactQuery(e.target.value)}
              placeholder="Find a contact..."
              className="w-full rounded border border-line px-2 py-1.5 text-[12px] outline-none focus:border-accent"
            />
          </div>
          <div className="max-h-56 overflow-y-auto">
            {contactOptions.map((c) => (
              <label
                key={c.id}
                className="flex items-center gap-2 px-3 py-2 text-[13px] hover:bg-gray-50 cursor-pointer"
              >
                <input
                  type="checkbox"
                  className="accent-accent"
                  checked={contactFilter.includes(c.id)}
                  onChange={() => {
                    setContactFilter((prev) =>
                      prev.includes(c.id) ? prev.filter((x) => x !== c.id) : [...prev, c.id],
                    );
                    resetToFirstPage();
                  }}
                />
                <span className="truncate">{c.name}</span>
              </label>
            ))}
            {contactOptions.length === 0 && (
              <p className="px-3 py-4 text-[12px] text-faint">No matches.</p>
            )}
          </div>
        </FilterMenu>

        {(typeFilter.length > 0 || contactFilter.length > 0) && (
          <button
            onClick={() => {
              setTypeFilter([]);
              setContactFilter([]);
              resetToFirstPage();
            }}
            className="text-[12px] text-link hover:underline"
          >
            Clear filters
          </button>
        )}
      </div>

      <div className="rounded-lg border border-line bg-white overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr className="border-b border-line">
                <th className="table-head w-12">
                  <span className="inline-flex items-center gap-0.5">
                    <input
                      type="checkbox"
                      className="accent-accent cursor-pointer"
                      checked={allPageSelected}
                      onChange={() =>
                        setSelected(allPageSelected ? [] : pageRows.map((t) => t.id))
                      }
                      aria-label="Select all tasks on this page"
                    />
                    <ChevronDown size={12} className="text-faint" />
                  </span>
                </th>
                <th className="table-head">Task</th>
                <th className="table-head">Description</th>
                <th className="table-head">Contacts</th>
                <th className="table-head">Task Type</th>
                <th className="table-head">Due in</th>
              </tr>
            </thead>
            <tbody>
              {pageRows.map((task) => (
                <tr
                  key={task.id}
                  onClick={() => setDetailTask(task)}
                  className="border-b border-line-soft last:border-0 hover:bg-gray-50/60 transition-colors cursor-pointer"
                >
                  <td className="cell" onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      className="accent-accent cursor-pointer"
                      checked={selected.includes(task.id)}
                      onChange={() =>
                        setSelected((prev) =>
                          prev.includes(task.id)
                            ? prev.filter((x) => x !== task.id)
                            : [...prev, task.id],
                        )
                      }
                      aria-label={`Select ${task.title}`}
                    />
                  </td>
                  <td className="cell">
                    <span
                      className={`font-semibold ${
                        task.status === 'done' ? 'text-faint line-through' : 'text-ink'
                      }`}
                    >
                      {task.title}
                    </span>
                  </td>
                  <td className="cell max-w-sm text-ink-soft">
                    {task.description || <span className="text-faint">{EMPTY}</span>}
                  </td>
                  <td className="cell" onClick={(e) => e.stopPropagation()}>
                    {task.contactId ? (
                      <button
                        onClick={() => onViewContact(task.contactId)}
                        className="text-link hover:underline"
                      >
                        {task.contactName}
                      </button>
                    ) : (
                      <span className="text-link">{EMPTY}</span>
                    )}
                  </td>
                  <td className="cell">
                    <TaskTypeChip type={task.type} />
                  </td>
                  <td className="cell">
                    <span
                      className={
                        task.status === 'done'
                          ? 'text-faint'
                          : isOverdue(task.dueDate)
                            ? 'text-danger'
                            : 'text-body'
                      }
                    >
                      {dueLabel(task.dueDate)}
                    </span>
                  </td>
                </tr>
              ))}

              {pageRows.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-16 text-center text-[13px] text-muted">
                    No tasks found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <Pagination page={page} pageCount={pageCount} onChange={setPage} />

      <AnimatePresence>
        {showAddModal && (
          <AddTaskModal
            contacts={contacts}
            initial={editingTask}
            onClose={() => {
              setShowAddModal(false);
              setEditingTask(null);
            }}
            onSave={(data) => {
              if (editingTask) {
                onUpdateTask(editingTask.id, data);
              } else {
                onAddTask(data);
              }
              setShowAddModal(false);
              setEditingTask(null);
              setDetailTask(null);
            }}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {detailTask && !showAddModal && (
          <TaskDetailModal
            task={detailTask}
            onClose={() => setDetailTask(null)}
            onToggleStatus={() => {
              onToggleStatus(detailTask.id);
              setDetailTask(null);
            }}
            onEdit={() => {
              setEditingTask(detailTask);
              setShowAddModal(true);
            }}
            onViewContact={() => {
              onViewContact(detailTask.contactId);
              setDetailTask(null);
            }}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

function FilterMenu({
  label,
  open,
  activeCount,
  onToggle,
  children,
  width = 'w-48',
}: {
  label: string;
  open: boolean;
  activeCount: number;
  onToggle: () => void;
  children: ReactNode;
  width?: string;
}) {
  return (
    <div className="relative">
      <button
        onClick={onToggle}
        className={`flex items-center gap-1.5 rounded-md border px-3 py-2 text-[13px] font-medium transition-colors ${
          activeCount > 0
            ? 'border-accent bg-accent-soft text-accent-hover'
            : 'border-line bg-white text-body hover:bg-gray-50'
        }`}
      >
        {label}
        {activeCount > 0 && <span>({activeCount})</span>}
        <ChevronDown size={13} className={open ? 'rotate-180 transition-transform' : 'transition-transform'} />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={onToggle} />
          <div
            className={`absolute left-0 mt-1.5 z-20 ${width} rounded-lg border border-line bg-white py-1 shadow-lg`}
          >
            {children}
          </div>
        </>
      )}
    </div>
  );
}

function Pagination({
  page,
  pageCount,
  onChange,
}: {
  page: number;
  pageCount: number;
  onChange: (p: number) => void;
}) {
  if (pageCount <= 1) return null;

  // Window the page numbers so long lists stay on one row.
  const pages: (number | 'gap')[] = [];
  for (let i = 1; i <= pageCount; i++) {
    if (i === 1 || i === pageCount || Math.abs(i - page) <= 3) {
      pages.push(i);
    } else if (pages[pages.length - 1] !== 'gap') {
      pages.push('gap');
    }
  }

  const arrow =
    'w-8 h-8 rounded-md border border-line text-[13px] flex items-center justify-center text-muted hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors';

  return (
    <div className="flex items-center justify-center gap-1.5 flex-wrap">
      <button className={arrow} onClick={() => onChange(page - 1)} disabled={page === 1}>
        <ChevronLeft size={14} />
      </button>

      {pages.map((p, i) =>
        p === 'gap' ? (
          <span key={`gap-${i}`} className="px-1 text-faint">
            …
          </span>
        ) : (
          <button
            key={p}
            onClick={() => onChange(p)}
            className={`w-8 h-8 rounded-md border text-[13px] transition-colors ${
              p === page
                ? 'border-accent text-accent font-medium'
                : 'border-line text-body hover:bg-gray-50'
            }`}
          >
            {p}
          </button>
        ),
      )}

      <button className={arrow} onClick={() => onChange(page + 1)} disabled={page === pageCount}>
        <ChevronRight size={14} />
      </button>
    </div>
  );
}
