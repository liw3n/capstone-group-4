import { ReactNode, useRef, useState } from 'react';
import { motion } from 'motion/react';
import { FileText, Pencil, Sparkles, Upload, X } from 'lucide-react';
import { MeetingSummary } from '../types';
import Button from '../ui/Button';
import { TaskTypeChip } from '../ui/Chip';
import { formatTimelineDate, newId, todayISO } from '../lib/format';
import { analyseMeeting, GeneratedTask } from '../services/ai';
import EditGeneratedTaskModal from './EditGeneratedTaskModal';

interface MeetingSummaryFlowProps {
  contactName: string;
  onClose: () => void;
  onSave: (summary: MeetingSummary, tasks: GeneratedTask[]) => void;
}

type Stage = 'input' | 'loading' | 'review';

const ACCEPTED =
  '.pdf,.txt,.vtt,.srt,.doc,.docx,.mp3,.m4a,.wav,.mp4,.mov,.webm';

export default function MeetingSummaryFlow({
  contactName,
  onClose,
  onSave,
}: MeetingSummaryFlowProps) {
  const [stage, setStage] = useState<Stage>('input');
  const [date, setDate] = useState(todayISO());
  const [notes, setNotes] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [progress, setProgress] = useState(0);

  const [title, setTitle] = useState('');
  const [summary, setSummary] = useState('');
  const [tasks, setTasks] = useState<GeneratedTask[]>([]);
  const [isEditingHeader, setIsEditingHeader] = useState(false);
  const [editingTask, setEditingTask] = useState<GeneratedTask | null>(null);
  const [expanded, setExpanded] = useState<string[]>([]);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const canGenerate = files.length > 0 || notes.trim().length > 0;

  const handleGenerate = async () => {
    setStage('loading');
    setProgress(0);

    const result = await analyseMeeting({
      contactName,
      date,
      notes,
      fileNames: files.map((f) => f.name),
      onProgress: setProgress,
    });

    setTitle(result.title);
    setSummary(result.summary);
    setTasks(result.tasks);
    setStage('review');
  };

  const handleSave = () => {
    const included = tasks.filter((t) => t.include);
    onSave(
      {
        id: newId(),
        date,
        title: title.trim() || 'Meeting Summary',
        description: summary.trim(),
        tasks: included.map((t) => t.title),
      },
      included,
    );
  };

  return (
    <div className="fixed inset-0 z-100 bg-white overflow-y-auto">
      {stage !== 'loading' && (
        <button
          onClick={onClose}
          className="fixed top-5 right-6 z-10 p-2 rounded-full text-faint hover:bg-gray-100 hover:text-body transition-colors"
          aria-label="Close"
        >
          <X size={20} />
        </button>
      )}

      {stage === 'input' && (
        <div className="mx-auto max-w-2xl px-6 py-12 flex flex-col gap-8">
          <div className="flex flex-col gap-2 text-center">
            <h1 className="text-[24px] font-semibold text-ink">New Meeting Summary</h1>
            <p className="text-[13px] text-muted">
              Drop in a recording or notes and we'll turn it into a summary with follow-up tasks.
            </p>
          </div>

          <div className="flex flex-col gap-2">
            <label className="text-[13px] font-medium text-ink">
              When did the meeting take place?
            </label>
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="w-full rounded-md border border-line px-3 py-2.5 text-[13px] outline-none focus:border-accent transition-colors"
            />
          </div>

          <div className="flex flex-col gap-2">
            <label className="text-[13px] font-medium text-ink">Recording or documents</label>
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setIsDragging(true);
              }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setIsDragging(false);
                setFiles((prev) => [...prev, ...Array.from(e.dataTransfer.files)]);
              }}
              className={`rounded-lg border border-dashed bg-gray-50/70 px-6 py-10 flex flex-col items-center gap-2 transition-colors ${
                isDragging ? 'border-accent bg-accent-soft/40' : 'border-line'
              }`}
            >
              <Upload size={18} className="text-faint" />
              <div className="flex items-center gap-2">
                <span className="text-[13px] text-muted">Drag and drop or</span>
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="rounded-md border border-line bg-white px-3 py-1.5 text-[13px] text-body hover:bg-gray-50 transition-colors"
                >
                  Choose File
                </button>
              </div>
              <span className="text-[11px] text-muted">PDF, transcript, audio, or video</span>

              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept={ACCEPTED}
                className="hidden"
                onChange={(e) => {
                  setFiles((prev) => [...prev, ...Array.from(e.target.files ?? [])]);
                  e.target.value = '';
                }}
              />
            </div>

            {files.length > 0 && (
              <div className="flex flex-col gap-2 mt-1">
                {files.map((file, i) => (
                  <div
                    key={`${file.name}-${i}`}
                    className="flex items-center justify-between rounded-md border border-line px-3 py-2"
                  >
                    <span className="flex items-center gap-2 text-[13px] text-body min-w-0">
                      <FileText size={14} className="text-accent shrink-0" />
                      <span className="truncate">{file.name}</span>
                      <span className="text-[11px] text-faint shrink-0">
                        {(file.size / 1024 / 1024).toFixed(2)} MB
                      </span>
                    </span>
                    <button
                      onClick={() => setFiles((prev) => prev.filter((_, idx) => idx !== i))}
                      className="text-faint hover:text-danger transition-colors"
                      aria-label={`Remove ${file.name}`}
                    >
                      <X size={14} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="flex flex-col gap-2">
            <label className="text-[13px] font-medium text-ink">Or paste your notes</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Paste the meeting transcript or type a summary here..."
              className="h-32 w-full resize-none rounded-md border border-line px-3 py-2.5 text-[13px] outline-none focus:border-accent transition-colors"
            />
          </div>

          <footer className="flex items-center justify-between border-t border-line pt-5">
            <Button variant="ghost" onClick={onClose}>
              CANCEL
            </Button>
            <Button variant="primary" disabled={!canGenerate} onClick={handleGenerate}>
              GENERATE SUMMARY
            </Button>
          </footer>
        </div>
      )}

      {stage === 'loading' && (
        <div className="min-h-screen flex flex-col items-center justify-center px-6 gap-3">
          <h1 className="text-[22px] font-semibold text-ink">Generating meeting summary</h1>
          <p className="max-w-md text-center text-[13px] text-muted leading-relaxed">
            Our AI Agent can help assign tasks with owners, priority levels and due dates, making
            sure they get done.
          </p>
          <p className="text-[12px] text-faint">Processing with AI... {progress}%</p>
          <div className="mt-2 h-1 w-80 max-w-full rounded-full bg-line overflow-hidden">
            <div
              className="h-full bg-link transition-[width] duration-100 ease-linear"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      )}

      {stage === 'review' && (
        <div className="pb-24">
          <div className="mx-auto max-w-3xl px-6 py-10 flex flex-col gap-5">
            <h1 className="text-center text-[24px] font-semibold text-ink">AI Meeting Summary</h1>

            <div className="rounded-md bg-link-soft px-4 py-2.5 flex items-start gap-2">
              <Sparkles size={14} className="text-link mt-0.5 shrink-0" />
              <p className="text-[12.5px] text-body">
                <span className="font-medium text-link">AI Extracted Data</span>{' '}
                <span className="text-muted">
                  Review and fine-tune all automated outputs to make sure they align with your
                  schedule and tasks.
                </span>
              </p>
            </div>

            <div className="rounded-lg border border-line p-5 flex flex-col gap-4">
              <div className="flex items-start justify-between gap-3">
                {isEditingHeader ? (
                  <input
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    onBlur={() => setIsEditingHeader(false)}
                    autoFocus
                    className="flex-1 rounded-md border border-line px-2 py-1 text-[16px] font-semibold text-ink outline-none focus:border-accent"
                  />
                ) : (
                  <h2 className="text-[16px] font-semibold text-ink">
                    {title}{' '}
                    <span className="font-normal text-faint">@{formatTimelineDate(date)}</span>
                  </h2>
                )}
                <button
                  onClick={() => setIsEditingHeader((v) => !v)}
                  className="text-faint hover:text-accent transition-colors shrink-0"
                  aria-label="Edit title"
                >
                  <Pencil size={14} />
                </button>
              </div>

              <Section title="Summary">
                <textarea
                  value={summary}
                  onChange={(e) => setSummary(e.target.value)}
                  className="w-full resize-y min-h-28 rounded-md border border-transparent bg-transparent px-0 py-0 text-[13px] leading-relaxed text-ink-soft outline-none focus:border-line focus:px-2 focus:py-2 transition-all"
                />
              </Section>

              <Section title="To-Do">
                <div className="flex flex-col rounded-md border border-line overflow-hidden">
                  {tasks.map((task) => {
                    const isOpen = expanded.includes(task.id);

                    return (
                      <div
                        key={task.id}
                        className="flex items-start gap-3 border-b border-line-soft last:border-0 bg-gray-50/50 px-3 py-3"
                      >
                        <input
                          type="checkbox"
                          checked={task.include}
                          onChange={() =>
                            setTasks((prev) =>
                              prev.map((t) =>
                                t.id === task.id ? { ...t, include: !t.include } : t,
                              ),
                            )
                          }
                          className="mt-0.5 accent-accent cursor-pointer shrink-0"
                          aria-label={`Include ${task.title}`}
                        />

                        <div className="flex-1 min-w-0">
                          <p className="text-[13px] font-semibold text-ink">{task.title}</p>
                          <p
                            className={`text-[12px] text-muted leading-relaxed ${
                              isOpen ? '' : 'truncate'
                            }`}
                          >
                            {task.description}
                          </p>
                          <p className="mt-1 text-[11px] text-faint">
                            Due date {task.startDate} - {task.dueDate}
                          </p>
                        </div>

                        <div className="flex items-center gap-2 shrink-0">
                          <button
                            onClick={() =>
                              setExpanded((prev) =>
                                prev.includes(task.id)
                                  ? prev.filter((id) => id !== task.id)
                                  : [...prev, task.id],
                              )
                            }
                            className="text-[12px] text-link hover:underline"
                          >
                            {isOpen ? 'Show less' : 'Read more'}
                          </button>
                          <TaskTypeChip type={task.type} />
                          <button
                            onClick={() => setEditingTask(task)}
                            className="text-faint hover:text-accent transition-colors"
                            aria-label={`Edit ${task.title}`}
                          >
                            <Pencil size={13} />
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>

                <p className="mt-2 text-[11px] text-faint">
                  {tasks.filter((t) => t.include).length} of {tasks.length} tasks will be added to
                  your task list.
                </p>
              </Section>
            </div>
          </div>

          <div className="fixed bottom-0 inset-x-0 border-t border-line bg-white px-6 py-4 flex justify-end">
            <Button variant="primary" onClick={handleSave}>
              SAVE TO ENGAGEMENT TIMELINE
            </Button>
          </div>
        </div>
      )}

      {editingTask && (
        <EditGeneratedTaskModal
          task={editingTask}
          onClose={() => setEditingTask(null)}
          onSave={(updated) => {
            setTasks((prev) => prev.map((t) => (t.id === updated.id ? updated : t)));
            setEditingTask(null);
          }}
        />
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex flex-col gap-2"
    >
      <h3 className="flex items-center gap-2 text-[13px] font-semibold text-ink">
        <span className="w-[3px] h-4 rounded-full bg-accent" />
        {title}
      </h3>
      {children}
    </motion.section>
  );
}
