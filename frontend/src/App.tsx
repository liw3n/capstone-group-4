import { useEffect, useMemo, useState } from 'react';
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
import CampaignDraftReview from './components/CampaignDraftReview';
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
import { addDaysISO, newId, todayISO } from './lib/format';
import { DEFAULT_SIGN_OFF } from './lib/email';
import {
  createCampaign,
  listCampaigns,
  updateCampaignState,
} from './services/campaignApi';
import { createContact, listContacts, replaceContact } from './services/contactApi';
import { CampaignDraftArtifact } from './services/chatApi';

export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>('home');
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [pipelineItems, setPipelineItems] = useState<PipelineItem[]>([]);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [campaignLoading, setCampaignLoading] = useState(false);
  const [campaignError, setCampaignError] = useState<string | null>(null);
  const [contactError, setContactError] = useState<string | null>(null);
  const [selectedContactId, setSelectedContactId] = useState<string | null>(null);
  const [selectedCampaignId, setSelectedCampaignId] = useState<string | null>(null);
  const [buildingCampaign, setBuildingCampaign] = useState(false);
  const [campaignDraftReview, setCampaignDraftReview] = useState<{
    draft: CampaignDraftArtifact;
    sessionId: string;
  } | null>(null);
  // Belongs to the advisor, not to a campaign — one template, reused by every send.
  const [signOff, setSignOff] = useState(DEFAULT_SIGN_OFF);
  const [editingSignOff, setEditingSignOff] = useState(false);
  const [showAddContact, setShowAddContact] = useState(false);
  const [showUploadWizard, setShowUploadWizard] = useState(false);

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

  /** The API already excludes an advisor's private campaigns for Marketing. */
  const marketingCampaigns = useMemo(
    () => campaigns.filter((c) => c.origin === 'marketing'),
    [campaigns],
  );

  /** Adviser ownership and routing are enforced by the campaign API. */
  const advisorCampaigns = campaigns;

  const selectedPipelineItem = useMemo(
    () =>
      selectedContactId
        ? pipelineItems.find((p) => p.contactId === selectedContactId && !p.archived) ?? null
        : null,
    [pipelineItems, selectedContactId],
  );

  const nextCaseId = () =>
    pipelineItems.reduce((max, item) => Math.max(max, item.caseId), 0) + 1;

  useEffect(() => {
    if (!session) {
      setCampaigns([]);
      return;
    }

    const controller = new AbortController();
    setCampaignLoading(true);
    setCampaignError(null);
    setContactError(null);
    const contactRequest = session.advisorId
      ? listContacts(session, controller.signal)
      : Promise.resolve<Contact[]>([]);
    Promise.all([listCampaigns(session, controller.signal), contactRequest])
      .then(([loaded, canonicalContacts]) => {
        setCampaigns(loaded);
        const loadedLeads = loaded.flatMap((campaign) => campaign.leadContacts ?? []);
        setContacts(() => {
          const byId = new Map(canonicalContacts.map((contact) => [contact.id, contact]));
          loadedLeads.forEach((contact) => byId.set(contact.id, contact));
          return [...byId.values()];
        });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        const message = error instanceof Error ? error.message : 'Unable to load application data.';
        setCampaignError(message);
        if (session.advisorId) setContactError(message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setCampaignLoading(false);
      });

    return () => controller.abort();
  }, [session]);

  /* ---------- session ---------- */

  const handleSignIn = (next: Session) => {
    setSession(next);
    // Marketing has no book of business, so it lands on Campaigns instead.
    setActiveTab(next.role === 'marketing' ? 'campaigns' : 'home');
    setSelectedContactId(null);
    setSelectedCampaignId(null);
    setBuildingCampaign(false);
    setCampaignDraftReview(null);
  };

  /** Campaigns are reloaded from PostgreSQL for the next signed-in role. */
  const handleSignOut = () => {
    setSession(null);
    setSelectedContactId(null);
    setSelectedCampaignId(null);
    setBuildingCampaign(false);
    setCampaignDraftReview(null);
  };

  /* ---------- contacts ---------- */

  const refreshContactsFromDatabase = async (activeSession: Session) => {
    const canonicalContacts = await listContacts(activeSession);
    setContacts((prev) => {
      const byId = new Map(canonicalContacts.map((contact) => [contact.id, contact]));
      prev
        .filter((contact) => contact.status === 'lead')
        .forEach((contact) => {
          if (!byId.has(contact.id)) byId.set(contact.id, contact);
        });
      return [...byId.values()];
    });
  };

  const openContact = (contactId: string) => {
    if (!contacts.some((c) => c.id === contactId)) return;
    setSelectedContactId(contactId);
    setSelectedCampaignId(null);
    setActiveTab('contacts');
  };

  const handleUpdateContact = async (updates: Partial<Contact>) => {
    const activeSession = session;
    if (!selectedContact || !activeSession?.advisorId) return;
    try {
      setContactError(null);
      const saved = await replaceContact({ ...selectedContact, ...updates }, activeSession);
      setContacts((prev) => prev.map((contact) => (contact.id === saved.id ? saved : contact)));

      // Keep the browser-only pipeline card's label badge in step.
      if (updates.label !== undefined) {
        setPipelineItems((prev) =>
          prev.map((item) =>
            item.contactId === saved.id ? { ...item, contactLabel: saved.label } : item,
          ),
        );
      }
    } catch (error) {
      setContactError(error instanceof Error ? error.message : 'Unable to update contact.');
    }
  };

  /**
   * Saving a generated meeting summary writes the timeline entry and creates a
   * task row for every item the advisor left checked.
   */
  const handleAddMeetingSummary = async (
    summary: MeetingSummary,
    generated: GeneratedTask[],
  ) => {
    const activeSession = session;
    if (!selectedContact || !activeSession?.advisorId) return;
    let saved: Contact;
    try {
      setContactError(null);
      saved = await replaceContact(
        { ...selectedContact, meetings: [summary, ...(selectedContact.meetings ?? [])] },
        activeSession,
      );
      setContacts((prev) =>
        prev.map((contact) => (contact.id === saved.id ? saved : contact)),
      );
    } catch (error) {
      setContactError(error instanceof Error ? error.message : 'Unable to save meeting summary.');
      return;
    }

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

  const handleCreateContacts = async (incoming: Omit<Contact, 'id'>[]) => {
    const activeSession = session;
    if (!activeSession?.advisorId) return false;
    try {
      setContactError(null);
      await Promise.all(
        incoming.map((contact) =>
          createContact({ ...contact, id: newId(), status: 'contact' }, activeSession),
        ),
      );
      try {
        await refreshContactsFromDatabase(activeSession);
      } catch (error) {
        setContactError(
          error instanceof Error
            ? `Contact created, but the saved contact list could not be refreshed: ${error.message}`
            : 'Contact created, but the saved contact list could not be refreshed.',
        );
      }
      return true;
    } catch (error) {
      setContactError(error instanceof Error ? error.message : 'Unable to create contacts.');
      return false;
    }
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

  const handleUpdatePipelineItem = async (id: string, updates: Partial<PipelineItem>) => {
    setPipelineItems((prev) => prev.map((p) => (p.id === id ? { ...p, ...updates } : p)));

    // The label lives in mock_client; the browser-only card only mirrors it.
    if (updates.contactLabel !== undefined) {
      const item = pipelineItems.find((p) => p.id === id);
      const contact = contacts.find((candidate) => candidate.id === item?.contactId);
      const activeSession = session;
      if (contact && activeSession?.advisorId) {
        try {
          const saved = await replaceContact(
            { ...contact, label: updates.contactLabel },
            activeSession,
          );
          setContacts((prev) =>
            prev.map((candidate) => (candidate.id === saved.id ? saved : candidate)),
          );
        } catch (error) {
          setContactError(error instanceof Error ? error.message : 'Unable to update contact.');
        }
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
   * Lead campaign rows are assigned stable prototype IDs here, marked as leads,
   * and saved with the campaign before they enter the local contact view.
   */
  const handleCreateCampaign = async (
    campaign: Campaign,
    leads?: Omit<Contact, 'id'>[],
  ) => {
    if (!session) return;
    let next = campaign;
    let created: Contact[] = [];

    if (leads && leads.length > 0) {
      created = leads.map((lead) => ({
        ...lead,
        id: newId(),
        status: 'lead' as const,
      }));

      next = {
        ...campaign,
        leadIds: created.map((c) => c.id),
        leadStats: { uploaded: created.length, added: 0, removed: 0 },
        leadContacts: created,
      };
    }

    try {
      setCampaignError(null);
      const saved = await createCampaign(next, created, session);
      setCampaigns((prev) => [saved, ...prev]);
      if (created.length > 0) {
        setContacts((prev) => [...prev, ...created]);
      }
      setBuildingCampaign(false);
    } catch (error) {
      setCampaignError(error instanceof Error ? error.message : 'Unable to create campaign.');
    }
  };

  const persistCampaign = async (campaign: Campaign): Promise<Campaign | null> => {
    if (!session) return null;
    try {
      setCampaignError(null);
      const saved = await updateCampaignState(campaign, session);
      setCampaigns((prev) => prev.map((item) => (item.id === saved.id ? saved : item)));
      return saved;
    } catch (error) {
      setCampaignError(error instanceof Error ? error.message : 'Unable to update campaign.');
      return null;
    }
  };

  /**
   * Promotes a lead into the book. It keeps its id, so the campaign row stays
   * linked and simply reads as handled from here on.
   */
  const handleAddLeadToContacts = async (campaignId: string, contactId: string) => {
    const activeSession = session;
    if (!activeSession?.advisorId) return;
    const campaign = campaigns.find((item) => item.id === campaignId);
    if (!campaign) return;
    const promotedLeadContacts = (campaign.leadContacts ?? []).map((contact) =>
      contact.id === contactId
        ? { ...contact, status: 'contact' as const, label: contact.label ?? 'Prospect' }
        : contact,
    );
    const promoted = promotedLeadContacts.find((contact) => contact.id === contactId);
    if (!promoted) return;
    try {
      await createContact(promoted, activeSession);
    } catch (error) {
      setContactError(error instanceof Error ? error.message : 'Unable to promote lead.');
      return;
    }
    const saved = await persistCampaign({
      ...campaign,
      leadContacts: promotedLeadContacts,
      leadStats: { ...campaign.leadStats, added: campaign.leadStats.added + 1 },
    });
    if (!saved) return;
    try {
      await refreshContactsFromDatabase(activeSession);
    } catch (error) {
      setContactError(
        error instanceof Error
          ? `Contact promoted, but the saved contact list could not be refreshed: ${error.message}`
          : 'Contact promoted, but the saved contact list could not be refreshed.',
      );
    }
  };

  /**
   * Deletes the lead outright — it was never a real record. The counter is the
   * only thing that survives, which is the point: the campaign still knows how
   * many names it started with and how many came to nothing.
   */
  const handleRemoveLead = async (campaignId: string, contactId: string) => {
    const campaign = campaigns.find((item) => item.id === campaignId);
    if (!campaign) return;
    const saved = await persistCampaign({
      ...campaign,
      leadIds: campaign.leadIds.filter((id) => id !== contactId),
      leadContacts: (campaign.leadContacts ?? []).filter((contact) => contact.id !== contactId),
      leadStats: { ...campaign.leadStats, removed: campaign.leadStats.removed + 1 },
    });
    if (saved) {
      setContacts((prev) => prev.filter((contact) => contact.id !== contactId));
    }
  };

  /**
   * One advisor decision about one targeted client. Spreading the campaign keeps
   * its `criteria` object identity, so the detail view's memoised audience does
   * not recompute and re-run the ranking on every click.
   */
  const handleCampaignAction = async (
    campaignId: string,
    contactId: string,
    action: CampaignActionType,
    draftMessage: string,
  ) => {
    const campaign = campaigns.find((c) => c.id === campaignId);
    const contact = contacts.find((c) => c.id === contactId);
    if (!campaign || !contact) return;

    const saved = await persistCampaign({
      ...campaign,
      actions: { ...campaign.actions, [contactId]: action },
    });
    if (!saved) return;

    if (action === 'pipeline') addContactToPipeline(contact);

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

  };

  /**
   * Records a mass send against the campaign. Nothing is transmitted — there is
   * no mail transport in this app — but the log is what the UI reports from, so
   * it has to capture exactly what the advisor confirmed.
   */
  const handleSendCampaignEmail = async (
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

    const campaign = campaigns.find((item) => item.id === campaignId);
    if (!campaign) return;
    await persistCampaign({ ...campaign, emailLog: [entry, ...campaign.emailLog] });
  };

  /* ---------- render ---------- */

  if (!session) return <LoginView onSignIn={handleSignIn} />;

  const isMarketing = session.role === 'marketing';

  const viewKey =
    activeTab === 'contacts' && selectedContact
      ? 'contact-detail'
      : activeTab === 'campaigns' && campaignDraftReview
        ? `campaign-draft-${campaignDraftReview.draft.draftId}`
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
            setCampaignDraftReview(null);
          }}
        />

        <main className="flex-1 overflow-y-auto border-l border-line bg-canvas">
          <div className="mx-auto max-w-[1400px] px-6 py-6">
            {activeTab === 'campaigns' && campaignLoading && (
              <div className="mb-4 rounded-lg border border-line bg-white px-4 py-3 text-sm text-muted-foreground">
                Loading campaigns…
              </div>
            )}
            {activeTab === 'campaigns' && campaignError && (
              <div role="alert" className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                {campaignError}
              </div>
            )}
            {!isMarketing && (activeTab === 'home' || activeTab === 'contacts') && contactError && (
              <div role="alert" className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                {contactError}
              </div>
            )}
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
                  (campaignDraftReview && session.advisorId ? (
                    <CampaignDraftReview
                      advisorId={session.advisorId}
                      sessionId={campaignDraftReview.sessionId}
                      initialDraft={campaignDraftReview.draft}
                      onCancel={() => setCampaignDraftReview(null)}
                      onDraftUpdated={(draft) => setCampaignDraftReview((current) =>
                        current ? { ...current, draft } : current,
                      )}
                    />
                  ) : buildingCampaign ? (
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
                        onNewCampaign={() => {
                          setCampaignDraftReview(null);
                          setBuildingCampaign(true);
                        }}
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
                      onNewCampaign={() => {
                        setCampaignDraftReview(null);
                        setBuildingCampaign(true);
                      }}
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
            onSave={async (contact) => {
              if (await handleCreateContacts([contact])) setShowAddContact(false);
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
        <ChatPanel
          key={session.advisorId}
          advisorId={session.advisorId}
          onReviewCampaignDraft={(draft, sessionId) => {
            setActiveTab('campaigns');
            setSelectedCampaignId(null);
            setBuildingCampaign(false);
            setCampaignDraftReview({ draft, sessionId });
          }}
        />
      )}
    </div>
  );
}
