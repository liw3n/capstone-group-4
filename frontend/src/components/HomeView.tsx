import { useMemo } from 'react';
import { motion } from 'motion/react';
import { ChevronRight, CircleCheck, ListChecks, Users } from 'lucide-react';
import { Contact, PipelineItem, Task } from '../types';
import { StageChip } from '../ui/Chip';
import SummaryCard from './SummaryCard';
import { dueLabel, formatDate, initials, isOverdue } from '../lib/format';

interface HomeViewProps {
  tasks: Task[];
  contacts: Contact[];
  pipelineItems: PipelineItem[];
  onViewTasks: () => void;
  onViewPipeline: () => void;
  onViewContact: (contactId: string) => void;
}

export default function HomeView({
  tasks,
  contacts,
  pipelineItems,
  onViewTasks,
  onViewPipeline,
  onViewContact,
}: HomeViewProps) {
  const openTasks = useMemo(() => tasks.filter((t) => t.status === 'todo'), [tasks]);

  const topTasks = useMemo(
    () => [...openTasks].sort((a, b) => a.dueDate.localeCompare(b.dueDate)).slice(0, 5),
    [openTasks],
  );

  const activeDeals = useMemo(
    () => pipelineItems.filter((i) => !i.archived && i.stage !== 'closed'),
    [pipelineItems],
  );

  const overdueCount = openTasks.filter((t) => isOverdue(t.dueDate)).length;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-[24px] font-semibold text-ink">Advisor Command Center</h1>
        <p className="text-[13px] text-muted">
          Strategic overview of your book of business and priority actions.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <SummaryCard
          title="Open Tasks"
          value={openTasks.length}
          caption={`${overdueCount} overdue`}
          icon="bookmark"
        />
        <SummaryCard title="Active Deals" value={activeDeals.length} caption="in pipeline" icon="flag" />
        <SummaryCard
          title="Total Contacts"
          value={contacts.length}
          caption={`${contacts.filter((c) => c.label === 'Prospect').length} prospects`}
          icon="eye"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 items-start">
        <section className="rounded-lg border border-line bg-white p-5 flex flex-col gap-4">
          <div className="flex items-center justify-between border-b border-line-soft pb-3">
            <h2 className="flex items-center gap-2 text-[14px] font-semibold text-ink">
              <ListChecks size={16} className="text-link" />
              Highest Urgency Tasks
            </h2>
            <span className="text-[11px] text-faint">Next 5 actions</span>
          </div>

          <div className="flex flex-col gap-2">
            {topTasks.length > 0 ? (
              topTasks.map((task, i) => (
                <motion.div
                  key={task.id}
                  initial={{ opacity: 0, x: -6 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.04 }}
                  className="flex items-center gap-3 rounded-md border border-line-soft px-3 py-2.5"
                >
                  <span
                    className={`w-1 h-8 rounded-full shrink-0 ${
                      isOverdue(task.dueDate) ? 'bg-danger' : 'bg-link'
                    }`}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-[11px] text-faint truncate">
                        {task.contactName || 'Unassigned'}
                      </span>
                      <span
                        className={`text-[11px] shrink-0 ${
                          isOverdue(task.dueDate) ? 'text-danger' : 'text-muted'
                        }`}
                      >
                        {dueLabel(task.dueDate)}
                      </span>
                    </div>
                    <p className="text-[13px] font-medium text-ink truncate">{task.title}</p>
                  </div>
                </motion.div>
              ))
            ) : (
              <div className="flex flex-col items-center gap-2 py-10 text-faint">
                <CircleCheck size={22} />
                <p className="text-[13px]">All caught up.</p>
              </div>
            )}

            <button
              onClick={onViewTasks}
              className="mt-1 w-full rounded-md py-2 text-[13px] text-muted hover:bg-gray-50 hover:text-link transition-colors"
            >
              Go to Tasks
            </button>
          </div>
        </section>

        <section className="rounded-lg border border-line bg-white p-5 flex flex-col gap-4">
          <div className="flex items-center justify-between border-b border-line-soft pb-3">
            <h2 className="flex items-center gap-2 text-[14px] font-semibold text-ink">
              <Users size={16} className="text-accent" />
              Priority Relationship Review
            </h2>
            <span className="text-[11px] text-faint">Active stages</span>
          </div>

          <div className="flex flex-col gap-2">
            {activeDeals.length > 0 ? (
              activeDeals.map((item, i) => (
                <motion.button
                  key={item.id}
                  initial={{ opacity: 0, x: 6 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.04 }}
                  onClick={() => onViewContact(item.contactId)}
                  className="group flex items-center gap-3 rounded-md border border-line-soft px-3 py-2.5 text-left hover:border-accent transition-colors"
                >
                  <span className="w-8 h-8 rounded-full bg-accent-soft text-accent-hover flex items-center justify-center text-[11px] font-semibold shrink-0">
                    {initials(item.contactName)}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-[13px] font-medium text-ink truncate">
                        {item.contactName}
                      </p>
                      <StageChip stage={item.stage} />
                    </div>
                    <p className="text-[11px] text-faint">
                      Case {item.caseId} · started {formatDate(item.startDate)}
                    </p>
                  </div>
                  <ChevronRight
                    size={14}
                    className="text-gray-300 group-hover:text-accent transition-colors shrink-0"
                  />
                </motion.button>
              ))
            ) : (
              <div className="py-10 text-center text-[13px] text-muted">
                No active deals in the pipeline.
              </div>
            )}

            <button
              onClick={onViewPipeline}
              className="mt-1 w-full rounded-md py-2 text-[13px] text-muted hover:bg-gray-50 hover:text-accent transition-colors"
            >
              Go to Pipeline
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}
