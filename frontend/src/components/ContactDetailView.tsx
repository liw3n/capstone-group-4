import { ReactNode, useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { Briefcase, FileText, Handshake, Home, MapPin, Pencil, User } from 'lucide-react';
import {
  Contact,
  CONTACT_LABELS,
  ContactLabel,
  ContactProfile,
  MeetingSummary,
  PipelineStage,
} from '../types';
import { GeneratedTask } from '../services/ai';
import { LabelChip, SourceChip, STAGE_META } from '../ui/Chip';
import Button from '../ui/Button';
import MeetingSummaryFlow from './MeetingSummaryFlow';
import EditSummaryModal from './EditSummaryModal';
import { display, EMPTY, formatPhone, formatTimelineDate, yesNo } from '../lib/format';
import { GENDER_LABELS, formatCash } from '../lib/targeting';

interface ContactDetailViewProps {
  contact: Contact;
  pipelineStage: PipelineStage | null;
  onUpdateContact: (updates: Partial<Contact>) => void;
  onAddMeetingSummary: (summary: MeetingSummary, tasks: GeneratedTask[]) => void;
  onAddToPipeline: () => void;
  onChangePipelineStage: (stage: PipelineStage) => void;
  onBack: () => void;
}

type Tab = 'timeline' | 'info';


export default function ContactDetailView({
  contact,
  pipelineStage,
  onUpdateContact,
  onAddMeetingSummary,
  onAddToPipeline,
  onChangePipelineStage,
  onBack,
}: ContactDetailViewProps) {
  const [activeTab, setActiveTab] = useState<Tab>('timeline');
  const [showSummaryFlow, setShowSummaryFlow] = useState(false);
  const [editingSummary, setEditingSummary] = useState<MeetingSummary | null>(null);
  const [isEditingNotes, setIsEditingNotes] = useState(false);
  const [notesDraft, setNotesDraft] = useState(contact.notes ?? '');

  // The component is reused across contacts, so local drafts must resync.
  useEffect(() => {
    setNotesDraft(contact.notes ?? '');
    setIsEditingNotes(false);
    setActiveTab('timeline');
  }, [contact.id]);

  const meetings = contact.meetings ?? [];

  const handleEditSummary = (summary: MeetingSummary) => {
    onUpdateContact({ meetings: meetings.map((m) => (m.id === summary.id ? summary : m)) });
    setEditingSummary(null);
  };

  return (
    <div className="flex flex-col gap-5">
      <nav className="flex items-center gap-1 text-[12px]">
        <button onClick={onBack} className="text-accent hover:underline">
          Home
        </button>
        <span className="text-faint">/</span>
        <button onClick={onBack} className="text-accent hover:underline">
          Contacts
        </button>
        <span className="text-faint">/</span>
        <span className="text-body">{contact.name}</span>
      </nav>

      <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <h1 className="text-[28px] font-semibold text-ink leading-none">{contact.name}</h1>
          <LabelChip label={contact.label} />
          <SourceChip contact={contact} />
        </div>

        <div className="flex flex-wrap items-center gap-5">
          <div className="flex flex-col gap-1">
            <span className="field-label uppercase tracking-wide">Label</span>
            <select
              value={contact.label ?? ''}
              onChange={(e) =>
                onUpdateContact({ label: (e.target.value || undefined) as ContactLabel })
              }
              className="rounded border border-link-soft bg-link-soft px-2 py-1 text-[11px] font-medium text-link uppercase outline-none cursor-pointer"
            >
              <option value="">Unlabelled</option>
              {CONTACT_LABELS.map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-col gap-1">
            <span className="field-label uppercase tracking-wide">Pipeline Status</span>
            <select
              value={pipelineStage ?? ''}
              onChange={(e) => onChangePipelineStage(e.target.value as PipelineStage)}
              disabled={!pipelineStage}
              className="rounded border border-pink-soft bg-pink-soft px-2 py-1 text-[11px] font-medium text-pink uppercase outline-none cursor-pointer disabled:cursor-default"
            >
              {!pipelineStage && <option value="">Not in pipeline</option>}
              {Object.entries(STAGE_META).map(([id, meta]) => (
                <option key={id} value={id}>
                  {meta.name}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-2">
            <Button variant="secondary">
              <Pencil size={14} />
              Edit Contact
            </Button>
            <Button variant="secondary" onClick={onAddToPipeline} disabled={!!pipelineStage}>
              {pipelineStage ? 'In Pipeline' : 'Add to Pipeline'}
            </Button>
          </div>
        </div>
      </div>

      {contact.source === 'transferred' && !contact.introduced && (
        <div className="rounded-lg border border-accent bg-accent-soft px-4 py-3 flex flex-wrap items-center gap-3">
          <Handshake size={16} className="text-accent shrink-0" />
          <p className="text-[13px] text-body flex-1 min-w-[260px] leading-relaxed">
            Transferred to you
            {contact.transferredFrom ? ` from ${contact.transferredFrom}` : ''}
            {contact.transferredOn ? ` on ${formatTimelineDate(contact.transferredOn)}` : ''}. They
            have not been introduced to you yet — any history below is the previous advisor's, not
            yours.
          </p>
          <Button variant="primary" onClick={() => onUpdateContact({ introduced: true })}>
            Mark as introduced
          </Button>
        </div>
      )}

      <div className="flex flex-col lg:grid lg:grid-cols-[1fr_280px] gap-5">
        <div className="rounded-lg border border-line bg-white">
          <div className="flex border-b border-line px-5">
            {([
              ['timeline', 'Engagement Timeline'],
              ['info', 'Contact Info'],
            ] as [Tab, string][]).map(([id, label]) => (
              <button
                key={id}
                onClick={() => setActiveTab(id)}
                className={`relative px-3 py-3.5 text-[13px] transition-colors ${
                  activeTab === id ? 'text-accent font-medium' : 'text-muted hover:text-body'
                }`}
              >
                {label}
                {activeTab === id && (
                  <motion.div
                    layoutId="contact-tab"
                    className="absolute bottom-0 left-2 right-2 h-[2px] bg-accent rounded-full"
                  />
                )}
              </button>
            ))}
          </div>

          <div className="p-5">
            {activeTab === 'timeline' ? (
              <TimelineTab
                meetings={meetings}
                onNewSummary={() => setShowSummaryFlow(true)}
                onEditSummary={(m) => setEditingSummary(m)}
              />
            ) : (
              <ContactInfoTab contact={contact} />
            )}
          </div>
        </div>

        <aside className="flex flex-col gap-4">
          <div className="rounded-lg border border-line bg-white p-5 flex flex-col gap-4">
            <div className="flex items-center gap-2">
              <FileText size={15} className="text-accent" />
              <h2 className="text-[14px] font-semibold text-ink">Notes</h2>
            </div>

            {isEditingNotes ? (
              <div className="flex flex-col gap-2">
                <textarea
                  value={notesDraft}
                  onChange={(e) => setNotesDraft(e.target.value)}
                  placeholder="Add a note about this contact..."
                  className="h-32 w-full resize-none rounded-md border border-line p-3 text-[13px] outline-none focus:border-accent transition-colors"
                />
                <div className="flex items-center gap-2">
                  <Button
                    variant="primary"
                    className="flex-1"
                    onClick={() => {
                      onUpdateContact({ notes: notesDraft });
                      setIsEditingNotes(false);
                    }}
                  >
                    Save
                  </Button>
                  <Button
                    variant="secondary"
                    className="flex-1"
                    onClick={() => {
                      setNotesDraft(contact.notes ?? '');
                      setIsEditingNotes(false);
                    }}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <div className="flex flex-col gap-4">
                <p
                  className={`text-[13px] leading-relaxed ${
                    contact.notes ? 'text-body' : 'text-faint text-center py-2'
                  }`}
                >
                  {contact.notes || 'No notes yet.'}
                </p>
                <Button variant="secondary" onClick={() => setIsEditingNotes(true)}>
                  <Pencil size={14} />
                  Edit Notes
                </Button>
              </div>
            )}
          </div>
        </aside>
      </div>

      {showSummaryFlow && (
        <MeetingSummaryFlow
          contactName={contact.name}
          onClose={() => setShowSummaryFlow(false)}
          onSave={(summary, tasks) => {
            onAddMeetingSummary(summary, tasks);
            setShowSummaryFlow(false);
          }}
        />
      )}

      <AnimatePresence>
        {editingSummary && (
          <EditSummaryModal
            initial={editingSummary}
            onClose={() => setEditingSummary(null)}
            onSave={handleEditSummary}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

function TimelineTab({
  meetings,
  onNewSummary,
  onEditSummary,
}: {
  meetings: MeetingSummary[];
  onNewSummary: () => void;
  onEditSummary: (m: MeetingSummary) => void;
}) {
  return (
    <div className="flex flex-col gap-6">
      {meetings.length > 0 ? (
        <div className="flex flex-col gap-5">
          {meetings.map((meeting) => (
            <motion.div
              key={meeting.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex flex-col sm:flex-row gap-4"
            >
              <span className="w-24 shrink-0 pt-4 text-[12px] text-body">
                {formatTimelineDate(meeting.date)}
              </span>

              <div className="flex-1 rounded-lg border border-line p-4 flex flex-col gap-3">
                <h3 className="text-[14px] font-semibold text-ink-soft">{meeting.title}</h3>
                <p className="text-[12.5px] leading-relaxed text-body">{meeting.description}</p>

                {meeting.tasks.length > 0 && (
                  <div className="flex flex-col gap-2">
                    <span className="text-[12px] font-semibold text-ink-soft">To-Do</span>
                    <div className="flex flex-wrap gap-2">
                      {meeting.tasks.map((task, i) => (
                        <span
                          key={i}
                          className="rounded bg-link-soft px-2 py-1 text-[11px] text-link"
                        >
                          {task}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                <div className="flex justify-end">
                  <Button variant="secondary" onClick={() => onEditSummary(meeting)}>
                    <Pencil size={13} />
                    Edit Summary
                  </Button>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      ) : (
        <div className="rounded-lg border border-dashed border-line py-14 text-center text-[13px] text-muted">
          No meetings recorded yet.
        </div>
      )}

      <div className="flex justify-center border-t border-line-soft pt-5">
        <button
          onClick={onNewSummary}
          className="rounded-full border border-accent px-6 py-2.5 text-[13px] font-medium text-accent hover:bg-accent hover:text-white transition-colors"
        >
          New Meeting Summary
        </button>
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="field-label">{label}</span>
      <span className="text-[13px] text-body">{value}</span>
    </div>
  );
}

function Section({
  icon: Icon,
  title,
  children,
}: {
  icon: typeof User;
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="flex flex-col gap-4 border-b border-line-soft pb-6 last:border-0 last:pb-0">
      <div className="flex items-center gap-2">
        <Icon size={15} className="text-accent" />
        <h3 className="text-[14px] font-semibold text-ink">{title}</h3>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-5">
        {children}
      </div>
    </section>
  );
}

function ContactInfoTab({ contact }: { contact: Contact }) {
  const p: ContactProfile = contact.profile ?? {};

  return (
    <div className="flex flex-col gap-6">
      <Section icon={User} title="Personal Information">
        <Field label="Secondary Phone Number" value={display(p.secondaryPhone)} />
        <Field label="NRIC/Passport Number" value={display(contact.nric)} />
        <Field label="Date of Birth" value={display(contact.dob)} />
        <Field label="Opt-In Email Address" value={display(p.optInEmail)} />
        <Field label="Opt-in for e-Statement?" value={yesNo(p.eStatement)} />
        <Field label="Accredited Investor" value={yesNo(p.accreditedInvestor)} />
        <Field
          label="Demographic"
          value={contact.gender ? GENDER_LABELS[contact.gender] : EMPTY}
        />
        <Field
          label="Cash Availability"
          value={formatCash(contact.cashAmount) ?? EMPTY}
        />
        <Field label="Last Contacted" value={display(contact.lastContacted)} />
      </Section>

      {contact.policies && contact.policies.length > 0 && (
        <Section icon={FileText} title="Policies Held">
          {contact.policies.map((policy, i) => (
            <Field
              key={`${policy.provider}-${policy.type}-${i}`}
              label={`${policy.provider} — ${policy.type}`}
              value={`Since ${display(policy.since)}`}
            />
          ))}
        </Section>
      )}

      <Section icon={Home} title="Residential Address">
        <Field label="Street Address" value={display(p.streetAddress)} />
        <Field label="City" value={display(p.city)} />
        <Field label="State/Province" value={display(p.stateProvince)} />
        <Field label="Postcode" value={display(p.postcode)} />
        <Field label="Country" value={display(p.country)} />
        <Field label="Mailing Address?" value={yesNo(p.mailingAddress)} />
      </Section>

      <Section icon={Briefcase} title="Employment Details">
        <Field label="Occupation" value={display(p.occupation)} />
        <Field label="Company/Firm Name" value={display(p.companyName)} />
        <Field label="Annual Income" value={display(p.annualIncome)} />
        <Field label="Office Number" value={display(p.officeNumber)} />
        <Field label="Office Street Address" value={display(p.officeStreetAddress)} />
        <Field label="City" value={display(p.officeCity)} />
        <Field label="State/Province" value={display(p.officeStateProvince)} />
        <Field label="ZIP/Postal Code" value={display(p.officePostalCode)} />
        <Field label="Country" value={display(p.officeCountry)} />
      </Section>

      <Section icon={MapPin} title="Primary Contact">
        <Field label="Email" value={display(contact.email)} />
        <Field label="Contact Number" value={formatPhone(contact)} />
      </Section>
    </div>
  );
}
