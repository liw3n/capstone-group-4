import { useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import TopBar from './components/TopBar';
import Sidebar, { TabId } from './components/Sidebar';
import LoginView from './components/LoginView';
import HomeView from './components/HomeView';
import ContactsView from './components/ContactsView';
import ContactDetailView from './components/ContactDetailView';
import TasksView from './components/TasksView';
import PipelineView from './components/PipelineView';
import SettingsView from './components/SettingsView';
import CampaignsView from './components/CampaignsView';
import CampaignDetailView from './components/CampaignDetailView';
import MarketingCampaignsView from './components/MarketingCampaignsView';
import MarketingCampaignDetailView from './components/MarketingCampaignDetailView';
import CampaignBuilder from './components/CampaignBuilder';
import SignOffTemplateModal from './components/SignOffTemplateModal';
import AddContactModal from './components/AddContactModal';
import UploadContactsWizard from './components/UploadContactsWizard';
import ChatPanel from './components/ChatPanel';
import {
  Campaign,
  CampaignActionType,
  CampaignEmail,
  Contact,
  MeetingSummary,
  PipelineItem,
  PipelineStage,
  Session,
  Task,
} from './types';
import { GeneratedTask } from './services/ai';
import { SEED_CAMPAIGNS, SEED_CONTACTS, SEED_PIPELINE, SEED_TASKS } from './data/seed';
import { addDaysISO, newId, todayISO } from './lib/format';
import { DEFAULT_SIGN_OFF } from './lib/email';
import { campaignReachesAdvisor } from './lib/directory';

export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>('home');
  const [contacts, setContacts] = useState<Contact[]>(SEED_CONTACTS);
  const [tasks, setTasks] = useState<Task[]>(SEED_TASKS);
  const [pipelineItems, setPipelineItems] = useState<PipelineItem[]>(SEED_PIPELINE);
  const [campaigns, setCampaigns] = useState<Campaign[]>(SEED_CAMPAIGNS);
  const [selectedContactId, setSelectedContactId] = useState<string | null>(null);
  const [selectedCampaignId, setSelectedCampaignId] = useState<string | null>(null);
  const [buildingCampaign, setBuildingCampaign] = useState(false);
  // Belongs to the advisor, not to a campaign — one template, reused by every send.
  const [signOff, setSignOff] = useState(DEFAULT_SIGN_OFF);
  const [editingSignOff, setEditingSignOff] = useState(false);
  const [showAddContact, setShowAddContact] = useState(false);
  const [showUploadWizard, setShowUploadWizard] = useState(false);
  const nextContactId = useRef(SEED_CONTACTS.length + 1);

  const selectedContact = useMemo(
    () => contacts.find((c) => c.id === selectedContactId) ?? null,
    [contacts, selectedContactId],
  );

  const selectedCampaign = useMemo(
    () => campaigns.find((c) => c.id === selectedCampaignId) ?? null,
    [campaigns, selectedCampaignId],
  );

  /**
   * THE LEAD BOUNDARY. Everything outside the campaign module reads this, never
   * `contacts` — Contacts, Home totals, the pipeline picker, the Tasks filter
   * and every criteria match. Leads are invisible until an advisor promotes
   * them, and keeping the filter in one place is what makes that true.
   */
  const activeContacts = useMemo(
    () => contacts.filter((c) => c.status !== 'lead'),
    [contacts],
  );

  /** Marketing never sees an advisor's private campaigns. */
  const marketingCampaigns = useMemo(
    () => campaigns.filter((c) => c.origin === 'marketing'),
    [campaigns],
  );

  /**
   * The advisor's inbox: campaigns routed to them through channel/team/advisor,
   * plus their own private ones. Routing is resolved here rather than in the
   * view so a campaign an advisor cannot see never reaches the component.
   */
  const advisorCampaigns = useMemo(() => {
    if (!session?.advisorId) return [];
    return campaigns.filter((c) => campaignReachesAdvisor(c, session.advisorId!));
  }, [campaigns, session]);

  const selectedPipelineItem = useMemo(
    () =>
      selectedContactId
        ? pipelineItems.find((p) => p.contactId === selectedContactId && !p.archived) ?? null
        : null,
    [pipelineItems, selectedContactId],
  );

  const nextCaseId = () =>
    pipelineItems.reduce((max, item) => Math.max(max, item.caseId), 0) + 1;

  /* ---------- session ---------- */

  const handleSignIn = (next: Session) => {
    setSession(next);
    // Marketing has no book of business, so it lands on Campaigns instead.
    setActiveTab(next.role === 'marketing' ? 'campaigns' : 'home');
    setSelectedContactId(null);
    setSelectedCampaignId(null);
    setBuildingCampaign(false);
  };

  /**
   * Signing out drops the session but keeps the data. That is what makes the
   * handoff demonstrable: author a campaign as Marketing, switch, and receive it
   * as the advisor without losing anything.
   */
  const handleSignOut = () => {
    setSession(null);
    setSelectedContactId(null);
    setSelectedCampaignId(null);
    setBuildingCampaign(false);
  };

  /* ---------- contacts ---------- */

  const openContact = (contactId: string) => {
    if (!contacts.some((c) => c.id === contactId)) return;
    setSelectedContactId(contactId);
    setSelectedCampaignId(null);
    setActiveTab('contacts');
  };

  const handleUpdateContact = (updates: Partial<Contact>) => {
    if (!selectedContact) return;

    setContacts((prev) =>
      prev.map((c) => (c.id === selectedContact.id ? { ...c, ...updates } : c)),
    );

    // Keep the pipeline card's label badge in step with the contact record.
    if (updates.label !== undefined) {
      setPipelineItems((prev) =>
        prev.map((p) =>
          p.contactId === selectedContact.id ? { ...p, contactLabel: updates.label } : p,
        ),
      );
    }
  };

  /**
   * Saving a generated meeting summary writes the timeline entry and creates a
   * task row for every item the advisor left checked.
   */
  const handleAddMeetingSummary = (summary: MeetingSummary, generated: GeneratedTask[]) => {
    if (!selectedContact) return;

    setContacts((prev) =>
      prev.map((c) =>
        c.id === selectedContact.id
          ? { ...c, meetings: [summary, ...(c.meetings ?? [])] }
          : c,
      ),
    );

    const rows: Task[] = generated.map((task) => ({
      id: newId(),
      contactId: selectedContact.id,
      contactName: selectedContact.name,
      title: task.title,
      description: task.description,
      type: task.type,
      startDate: task.startDate,
      dueDate: task.dueDate,
      status: 'todo',
    }));

    if (rows.length > 0) setTasks((prev) => [...rows, ...prev]);
  };

  const handleCreateContacts = (incoming: Omit<Contact, 'id'>[]) => {
    const created = incoming.map((contact) => ({
      ...contact,
      id: String(nextContactId.current++),
    }));
    setContacts((prev) => [...created, ...prev]);
  };

  /* ---------- pipeline ---------- */

  const addContactToPipeline = (contact: Contact) => {
    const existing = pipelineItems.find((p) => p.contactId === contact.id && !p.archived);
    if (existing) return;

    const start = todayISO();
    setPipelineItems((prev) => [
      ...prev,
      {
        id: newId(),
        caseId: nextCaseId(),
        contactId: contact.id,
        contactName: contact.name,
        contactLabel: contact.label,
        stage: 'opportunities',
        startDate: start,
        dueDate: addDaysISO(start, 30),
        description: '',
      },
    ]);
  };

  const handleUpdatePipelineItem = (id: string, updates: Partial<PipelineItem>) => {
    setPipelineItems((prev) => prev.map((p) => (p.id === id ? { ...p, ...updates } : p)));

    // The label lives on the contact record; the card only mirrors it.
    if (updates.contactLabel !== undefined) {
      const item = pipelineItems.find((p) => p.id === id);
      if (item) {
        setContacts((prev) =>
          prev.map((c) => (c.id === item.contactId ? { ...c, label: updates.contactLabel } : c)),
        );
      }
    }
  };

  const setStageForContact = (contactId: string, stage: PipelineStage) => {
    setPipelineItems((prev) =>
      prev.map((p) => (p.contactId === contactId && !p.archived ? { ...p, stage } : p)),
    );
  };

  /* ---------- tasks ---------- */

  const handleAddTask = (task: Omit<Task, 'id' | 'status'> & { status?: Task['status'] }) => {
    setTasks((prev) => [{ ...task, id: newId(), status: task.status ?? 'todo' }, ...prev]);
  };

  const handleUpdateTask = (id: string, updates: Partial<Task>) => {
    setTasks((prev) => prev.map((t) => (t.id === id ? { ...t, ...updates } : t)));
  };

  const handleToggleTaskStatus = (id: string) => {
    setTasks((prev) =>
      prev.map((t) => (t.id === id ? { ...t, status: t.status === 'todo' ? 'done' : 'todo' } : t)),
    );
  };

  /* ---------- campaigns ---------- */

  /**
   * Lead campaigns arrive with their rows parsed but unsaved. The contact
   * records are created here, as `status: 'lead'`, and their ids become the
   * campaign's audience.
   */
  const handleCreateCampaign = (campaign: Campaign, leads?: Omit<Contact, 'id'>[]) => {
    let next = campaign;

    if (leads && leads.length > 0) {
      const created = leads.map((lead) => ({
        ...lead,
        id: String(nextContactId.current++),
        status: 'lead' as const,
      }));

      setContacts((prev) => [...prev, ...created]);
      next = {
        ...campaign,
        leadIds: created.map((c) => c.id),
        leadStats: { uploaded: created.length, added: 0, removed: 0 },
      };
    }

    setCampaigns((prev) => [next, ...prev]);
    setBuildingCampaign(false);
  };

  /**
   * Promotes a lead into the book. It keeps its id, so the campaign row stays
   * linked and simply reads as handled from here on.
   */
  const handleAddLeadToContacts = (campaignId: string, contactId: string) => {
    setContacts((prev) =>
      prev.map((c) =>
        c.id === contactId ? { ...c, status: 'contact' as const, label: c.label ?? 'Prospect' } : c,
      ),
    );

    setCampaigns((prev) =>
      prev.map((c) =>
        c.id === campaignId
          ? { ...c, leadStats: { ...c.leadStats, added: c.leadStats.added + 1 } }
          : c,
      ),
    );
  };

  /**
   * Deletes the lead outright — it was never a real record. The counter is the
   * only thing that survives, which is the point: the campaign still knows how
   * many names it started with and how many came to nothing.
   */
  const handleRemoveLead = (campaignId: string, contactId: string) => {
    setContacts((prev) => prev.filter((c) => c.id !== contactId));

    setCampaigns((prev) =>
      prev.map((c) =>
        c.id === campaignId
          ? {
              ...c,
              leadIds: c.leadIds.filter((id) => id !== contactId),
              leadStats: { ...c.leadStats, removed: c.leadStats.removed + 1 },
            }
          : c,
      ),
    );
  };

  /**
   * One advisor decision about one targeted client. Spreading the campaign keeps
   * its `criteria` object identity, so the detail view's memoised audience does
   * not recompute and re-run the ranking on every click.
   */
  const handleCampaignAction = (
    campaignId: string,
    contactId: string,
    action: CampaignActionType,
    draftMessage: string,
  ) => {
    const campaign = campaigns.find((c) => c.id === campaignId);
    const contact = contacts.find((c) => c.id === contactId);
    if (!campaign || !contact) return;

    if (action === 'pipeline') {
      addContactToPipeline(contact);
    }

    if (action === 'task') {
      const start = todayISO();
      setTasks((prev) => [
        {
          id: newId(),
          contactId: contact.id,
          contactName: contact.name,
          title: `${campaign.name} — reach out to ${contact.name}`,
          description: draftMessage,
          type: 'Campaign',
          startDate: start,
          dueDate: addDaysISO(start, 14),
          status: 'todo',
          campaignId: campaign.id,
        },
        ...prev,
      ]);
    }

    setCampaigns((prev) =>
      prev.map((c) =>
        c.id === campaignId ? { ...c, actions: { ...c.actions, [contactId]: action } } : c,
      ),
    );
  };

  /**
   * Records a mass send against the campaign. Nothing is transmitted — there is
   * no mail transport in this app — but the log is what the UI reports from, so
   * it has to capture exactly what the advisor confirmed.
   */
  const handleSendCampaignEmail = (
    campaignId: string,
    recipientIds: string[],
    subject: string,
  ) => {
    if (!session || recipientIds.length === 0) return;

    const entry: CampaignEmail = {
      id: newId(),
      sentAt: todayISO(),
      subject,
      fromName: session.name,
      fromEmail: session.email,
      recipientIds,
      signOff,
    };

    setCampaigns((prev) =>
      prev.map((c) =>
        c.id === campaignId ? { ...c, emailLog: [entry, ...c.emailLog] } : c,
      ),
    );
  };

  /* ---------- render ---------- */

  if (!session) return <LoginView onSignIn={handleSignIn} />;

  const isMarketing = session.role === 'marketing';

  const viewKey =
    activeTab === 'contacts' && selectedContact
      ? 'contact-detail'
      : activeTab === 'campaigns' && buildingCampaign
        ? 'campaign-builder'
        : activeTab === 'campaigns' && selectedCampaign
          ? 'campaign-detail'
          : activeTab;

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <TopBar session={session} onSignOut={handleSignOut} />

      <div className="flex flex-1 overflow-hidden">
        <Sidebar
          activeTab={activeTab}
          role={session.role}
          onTabChange={(tab) => {
            setActiveTab(tab);
            setSelectedContactId(null);
            setSelectedCampaignId(null);
            setBuildingCampaign(false);
          }}
        />

        <main className="flex-1 overflow-y-auto border-l border-line bg-canvas">
          <div className="mx-auto max-w-[1400px] px-6 py-6">
            {/*
              Deliberately not wrapped in AnimatePresence: `mode="wait"` holds the
              incoming view until the outgoing exit animation finishes, which never
              happens while the tab is backgrounded (rAF is paused) and leaves the
              app stuck on the previous screen. A keyed fade-in is enough here.
            */}
            <motion.div
              key={viewKey}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.15 }}
            >
                {activeTab === 'home' && !isMarketing && (
                  <HomeView
                    tasks={tasks}
                    contacts={activeContacts}
                    pipelineItems={pipelineItems}
                    onViewTasks={() => setActiveTab('tasks')}
                    onViewPipeline={() => setActiveTab('pipeline')}
                    onViewContact={openContact}
                  />
                )}

                {activeTab === 'contacts' &&
                  !isMarketing &&
                  (selectedContact ? (
                    <ContactDetailView
                      contact={selectedContact}
                      pipelineStage={selectedPipelineItem?.stage ?? null}
                      onUpdateContact={handleUpdateContact}
                      onAddMeetingSummary={handleAddMeetingSummary}
                      onAddToPipeline={() => addContactToPipeline(selectedContact)}
                      onChangePipelineStage={(stage) =>
                        setStageForContact(selectedContact.id, stage)
                      }
                      onBack={() => setSelectedContactId(null)}
                    />
                  ) : (
                    <ContactsView
                      contacts={activeContacts}
                      pipelineItems={pipelineItems}
                      onSelectContact={(c) => openContact(c.id)}
                      onAddToPipeline={addContactToPipeline}
                      onAddContact={() => setShowAddContact(true)}
                      onUploadContacts={() => setShowUploadWizard(true)}
                    />
                  ))}

                {activeTab === 'tasks' && !isMarketing && (
                  <TasksView
                    tasks={tasks}
                    contacts={activeContacts}
                    onToggleStatus={handleToggleTaskStatus}
                    onViewContact={openContact}
                    onAddTask={handleAddTask}
                    onUpdateTask={handleUpdateTask}
                  />
                )}

                {activeTab === 'pipeline' && !isMarketing && (
                  <PipelineView
                    items={pipelineItems}
                    contacts={activeContacts}
                    onUpdateItem={handleUpdatePipelineItem}
                    onArchiveItem={(id) => handleUpdatePipelineItem(id, { archived: true })}
                    onRestoreItem={(id) => handleUpdatePipelineItem(id, { archived: false })}
                    onAddContactToPipeline={addContactToPipeline}
                    onViewContact={openContact}
                  />
                )}

                {activeTab === 'campaigns' &&
                  (buildingCampaign ? (
                    <CampaignBuilder
                      contacts={activeContacts}
                      createdBy={session.name}
                      origin={isMarketing ? 'marketing' : 'advisor'}
                      advisorId={session.advisorId}
                      onCancel={() => setBuildingCampaign(false)}
                      onSubmit={handleCreateCampaign}
                    />
                  ) : isMarketing ? (
                    /* Full contacts, not activeContacts: Marketing authors lead
                       campaigns now, and resolving one needs the lead records.
                       resolveAudience still keeps leads out of criteria matching. */
                    selectedCampaign ? (
                      <MarketingCampaignDetailView
                        campaign={selectedCampaign}
                        contacts={contacts}
                        onBack={() => setSelectedCampaignId(null)}
                      />
                    ) : (
                      <MarketingCampaignsView
                        campaigns={marketingCampaigns}
                        contacts={contacts}
                        onNewCampaign={() => setBuildingCampaign(true)}
                        onOpenCampaign={setSelectedCampaignId}
                      />
                    )
                  ) : selectedCampaign ? (
                    <CampaignDetailView
                      campaign={selectedCampaign}
                      contacts={contacts}
                      pipelineItems={pipelineItems}
                      onBack={() => setSelectedCampaignId(null)}
                      session={session}
                      signOff={signOff}
                      onAction={(contactId, action, draftMessage) =>
                        handleCampaignAction(selectedCampaign.id, contactId, action, draftMessage)
                      }
                      onAddLeadToContacts={(contactId) =>
                        handleAddLeadToContacts(selectedCampaign.id, contactId)
                      }
                      onRemoveLead={(contactId) =>
                        handleRemoveLead(selectedCampaign.id, contactId)
                      }
                      onSendEmail={(recipientIds, subject) =>
                        handleSendCampaignEmail(selectedCampaign.id, recipientIds, subject)
                      }
                      onEditSignOff={() => setEditingSignOff(true)}
                      onViewContact={openContact}
                    />
                  ) : (
                    <CampaignsView
                      campaigns={advisorCampaigns}
                      contacts={contacts}
                      onOpenCampaign={setSelectedCampaignId}
                      onNewCampaign={() => setBuildingCampaign(true)}
                      onEditSignOff={() => setEditingSignOff(true)}
                    />
                  ))}

                {activeTab === 'settings' && <SettingsView />}
            </motion.div>
          </div>
        </main>
      </div>

      <AnimatePresence>
        {editingSignOff && (
          <SignOffTemplateModal
            signOff={signOff}
            session={session}
            onClose={() => setEditingSignOff(false)}
            onSave={(next) => {
              setSignOff(next);
              setEditingSignOff(false);
            }}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {showAddContact && (
          <AddContactModal
            onClose={() => setShowAddContact(false)}
            onSave={(contact) => {
              handleCreateContacts([contact]);
              setShowAddContact(false);
            }}
          />
        )}
      </AnimatePresence>

      {showUploadWizard && (
        <UploadContactsWizard
          contacts={contacts}
          onClose={() => setShowUploadWizard(false)}
          onImport={handleCreateContacts}
          onGoToCampaigns={() => {
            setShowUploadWizard(false);
            setActiveTab('campaigns');
          }}
        />
      )}

      {activeTab === 'campaigns' && !isMarketing && session.advisorId && (
        <ChatPanel key={session.advisorId} advisorId={session.advisorId} />
      )}
    </div>
  );
}
