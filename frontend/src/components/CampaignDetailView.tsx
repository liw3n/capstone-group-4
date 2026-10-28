import { useEffect, useMemo, useState } from 'react';
import {
  ArrowLeft,
  Briefcase,
  Check,
  CircleAlert,
  Mail,
  Sparkles,
  Upload,
  User,
  X,
} from 'lucide-react';
import { Campaign, CampaignActionType, Contact, PipelineItem, Session } from '../types';
import Button from '../ui/Button';
import { LabelChip } from '../ui/Chip';
import { CriteriaSummary } from './CampaignCriteria';
import SendCampaignEmailModal from './SendCampaignEmailModal';
import {
  describeContactTargeting,
  missingFieldsFor,
  resolveAudience,
} from '../lib/targeting';
import { describeRouting } from '../lib/directory';
import LeadAudienceTable from './LeadAudienceTable';
import { CampaignRecommendation, rankCampaignAudience } from '../services/ai';
import { emailedContactIds } from '../lib/email';
import { EMPTY, formatDate } from '../lib/format';
import {
  EngagementStatus,
  getCampaignEngagementStatus,
  updateCampaignEngagementStatus,
} from '../services/campaignApi';

interface CampaignDetailViewProps {
  campaign: Campaign;
  contacts: Contact[];
  pipelineItems: PipelineItem[];
  session: Session;
  signOff: string;
  onBack: () => void;
  onAction: (contactId: string, action: CampaignActionType, draftMessage: string) => void;
  onAddLeadToContacts: (contactId: string) => void;
  onRemoveLead: (contactId: string) => void;
  onSendEmail: (recipientIds: string[], subject: string) => void;
  onEditSignOff: () => void;
  onViewContact: (contactId: string) => void;
}

const ACTION_LABELS: Record<CampaignActionType, string> = {
  pipeline: 'Added to pipeline',
  task: 'Task created',
  dismissed: 'Dismissed',
};

export default function CampaignDetailView({
  campaign,
  contacts,
  pipelineItems,
  session,
  signOff,
  onBack,
  onAction,
  onAddLeadToContacts,
  onRemoveLead,
  onSendEmail,
  onEditSignOff,
  onViewContact,
}: CampaignDetailViewProps) {
  const [ranking, setRanking] = useState<CampaignRecommendation[] | null>(null);
  const [sendingEmail, setSendingEmail] = useState(false);
  const [clientStatuses, setClientStatuses] = useState<Record<string, EngagementStatus>>({});
  const [statusLoading, setStatusLoading] = useState(false);
  const [statusSavingClientId, setStatusSavingClientId] = useState<string | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);

  const isLeadCampaign = campaign.audienceSource === 'leads';

  const handleEngagementStatusChange = async (
    contactId: string,
    status: EngagementStatus,
  ) => {
    setStatusSavingClientId(contactId);
    setStatusError(null);
    try {
      const result = await updateCampaignEngagementStatus(
        campaign.id,
        contactId,
        status,
        session,
      );
      setClientStatuses((current) => ({
        ...current,
        [contactId]: result.status,
      }));
    } catch (error) {
      setStatusError(
        error instanceof Error ? error.message : 'Could not update campaign status.',
      );
    } finally {
      setStatusSavingClientId(null);
    }
  };

  // Depend on the audience fields, not the campaign object: actions, emailLog
  // and leadStats all replace the object, and a fresh `matched` array on every
  // click would restart the ranking effect below.
  const { matched, incomplete } = useMemo(
    () => resolveAudience(campaign, contacts),
    [
      campaign.audienceSource,
      campaign.criteria,
      campaign.includeIds,
      campaign.excludeIds,
      campaign.leadIds,
      contacts,
    ],
  );

  useEffect(() => {
    if (isLeadCampaign || matched.length === 0) {
      setClientStatuses({});
      setStatusLoading(false);
      return;
    }

    let cancelled = false;
    setClientStatuses({});
    setStatusLoading(true);
    setStatusError(null);

    Promise.allSettled(
      matched.map(async (contact) => [
        contact.id,
        await getCampaignEngagementStatus(campaign.id, contact.id, session),
      ] as const),
    )
      .then((results) => {
        if (cancelled) return;
        const statuses: Record<string, EngagementStatus> = {};
        let firstError: unknown;
        let hasError = false;

        for (const result of results) {
          if (result.status === 'rejected') {
            hasError = true;
            firstError ??= result.reason;
            continue;
          }
          const [contactId, status] = result.value;
          if (status !== null) statuses[contactId] = status;
        }

        setClientStatuses(statuses);
        if (hasError) {
          setStatusError(
            firstError instanceof Error
              ? firstError.message
              : 'Could not load one or more campaign statuses.',
          );
        }
      })
      .finally(() => {
        if (!cancelled) setStatusLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [campaign.id, isLeadCampaign, matched, session]);

  // The rules pick the audience; this only orders it. Re-running on a criteria
  // change is fine — the score is deterministic, so the order never wobbles.
  useEffect(() => {
    if (isLeadCampaign) return;

    let cancelled = false;
    setRanking(null);

    rankCampaignAudience({
      campaignName: campaign.name,
      clientMessage: campaign.clientMessage,
      contacts: matched,
    }).then((result) => {
      if (!cancelled) setRanking(result);
    });

    return () => {
      cancelled = true;
    };
  }, [campaign.id, campaign.name, campaign.clientMessage, matched, isLeadCampaign]);

  const contactById = useMemo(
    () => new Map(contacts.map((c) => [c.id, c])),
    [contacts],
  );

  const inPipeline = (contactId: string) =>
    pipelineItems.some((p) => p.contactId === contactId && !p.archived);

  const emailedIds = useMemo(() => emailedContactIds(campaign.emailLog), [campaign.emailLog]);

  const totalEmailed = emailedIds.size;

  return (
    <div className="flex flex-col gap-5">
      <button
        onClick={onBack}
        className="flex w-fit items-center gap-1.5 text-[13px] text-link hover:underline"
      >
        <ArrowLeft size={15} />
        Campaigns
      </button>

      <section className="overflow-hidden rounded-lg border border-line bg-white">
        {campaign.bannerDataUrl && (
          <img
            src={campaign.bannerDataUrl}
            alt={'Banner for ' + campaign.name}
            className="max-h-52 w-full object-cover"
          />
        )}

        <div className="flex flex-col gap-4 p-5">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-[20px] font-semibold text-ink">{campaign.name}</h1>
              {campaign.origin === 'advisor' && (
                <span className="inline-flex items-center gap-1 rounded bg-purple-soft px-2 py-0.5 text-[11px] font-medium text-purple">
                  <User size={10} />
                  Your campaign
                </span>
              )}
              {isLeadCampaign && (
                <span className="inline-flex items-center gap-1 rounded bg-amber-soft px-2 py-0.5 text-[11px] font-medium text-amber">
                  <Upload size={10} />
                  Lead list
                </span>
              )}
            </div>
            <p className="mt-1 text-[12px] text-faint">
              {campaign.origin === 'advisor'
                ? `Created by you · not sent to anyone · ${formatDate(campaign.createdAt)}`
                : `From ${campaign.createdBy} · ${describeRouting(campaign)} · ${formatDate(
                    campaign.createdAt,
                  )}`}
            </p>
          </div>

          <div className="flex flex-col gap-1.5">
            <span className="field-label">
              {campaign.origin === 'advisor' ? 'Your notes' : 'Campaign brief'}
            </span>
            <p className="text-[13px] leading-relaxed text-body">{campaign.description}</p>
          </div>

          <div className="flex flex-col gap-1.5">
            <span className="field-label">Client messaging</span>
            <p className="rounded-md bg-link-soft px-4 py-3 text-[13px] leading-relaxed text-body">
              {campaign.clientMessage}
            </p>
          </div>

          <div className="flex flex-col gap-2 border-t border-line-soft pt-4">
            {isLeadCampaign ? (
              <>
                <span className="field-label">Audience</span>
                <p className="text-[12px] text-muted">
                  An uploaded lead list of {campaign.leadStats.uploaded}{' '}
                  {campaign.leadStats.uploaded === 1 ? 'name' : 'names'}. No targeting criteria
                  apply.
                </p>
              </>
            ) : (
              <>
                <span className="field-label">Targeting criteria</span>
                <CriteriaSummary criteria={campaign.criteria} />
              </>
            )}
          </div>
        </div>
      </section>

      {isLeadCampaign && (
        <LeadAudienceTable
          campaign={campaign}
          leads={matched}
          totalEmailed={totalEmailed}
          onAddToContacts={onAddLeadToContacts}
          onRemove={onRemoveLead}
          onEmail={() => setSendingEmail(true)}
          onViewContact={onViewContact}
        />
      )}

      {!isLeadCampaign && (
      <section className="rounded-lg border border-line bg-white">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
          <div>
            <h2 className="text-[15px] font-semibold text-ink">
              Identified clients ({matched.length})
            </h2>
            <p className="mt-0.5 flex items-center gap-1.5 text-[12px] text-muted">
              <Sparkles size={12} className="text-accent" />
              Selected by criteria, ordered by AI on fit and readiness.
            </p>
          </div>

          <div className="flex flex-col items-end gap-1">
            <Button
              variant="primary"
              onClick={() => setSendingEmail(true)}
              disabled={matched.length === 0}
            >
              <Mail size={14} />
              Email clients
            </Button>
            {totalEmailed > 0 && (
              <span className="text-[11px] text-faint">
                {totalEmailed} already emailed across {campaign.emailLog.length} send
                {campaign.emailLog.length === 1 ? '' : 's'}
              </span>
            )}
          </div>
        </div>
        {statusError && (
          <p role="alert" className="border-b border-line px-5 py-3 text-[12px] text-danger">
            {statusError}
          </p>
        )}

        {ranking === null ? (
          <p className="px-5 py-14 text-center text-[13px] text-muted">
            Prioritising your matched clients…
          </p>
        ) : matched.length === 0 ? (
          <p className="px-5 py-14 text-center text-[13px] text-muted">
            No clients in your book match this campaign's criteria.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b border-line">
                  <th className="table-head">Client</th>
                  <th className="table-head">Targeting match</th>
                  <th className="table-head">Status</th>
                  <th className="table-head text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {ranking.map((recommendation) => {
                  const contact = contactById.get(recommendation.contactId);
                  if (!contact) return null;

                  const taken = campaign.actions[contact.id];
                  const engagementStatus = clientStatuses[contact.id];

                  return (
                    <tr
                      key={contact.id}
                      className="border-b border-line-soft transition-colors last:border-0 hover:bg-gray-50/60"
                    >
                      <td className="cell">
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => onViewContact(contact.id)}
                            className="font-medium text-link hover:underline"
                          >
                            {contact.name}
                          </button>
                          <LabelChip label={contact.label} />
                          {emailedIds.has(contact.id) && (
                            <span className="inline-flex items-center gap-1 rounded bg-link-soft px-2 py-0.5 text-[11px] font-medium text-link">
                              <Mail size={10} />
                              Emailed
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="cell text-muted">{describeContactTargeting(contact)}</td>
                      <td className="cell">
                        <select
                          aria-label={`Status for ${contact.name}`}
                          className="rounded-md border border-line bg-white px-2.5 py-1.5 text-[12px] text-ink focus:border-link focus:outline-none focus:ring-2 focus:ring-link/20 disabled:cursor-wait disabled:opacity-60"
                          value={engagementStatus === undefined ? '' : String(engagementStatus)}
                          disabled={statusLoading || statusSavingClientId !== null}
                          onChange={(event) => {
                            const nextStatus = Number(event.currentTarget.value);
                            if (nextStatus === 0 || nextStatus === 1 || nextStatus === 2) {
                              void handleEngagementStatusChange(contact.id, nextStatus);
                            }
                          }}
                        >
                          <option value="" disabled>
                            Select status
                          </option>
                          <option value="0">Contacted</option>
                          <option value="1">Engaged</option>
                          <option value="2">Rejected</option>
                        </select>
                      </td>
                      <td className="cell text-right">
                        {taken ? (
                          <span className="inline-flex items-center gap-1.5 text-[12px] text-muted">
                            <Check size={13} className="text-success" />
                            {ACTION_LABELS[taken]}
                          </span>
                        ) : (
                          <div className="flex items-center justify-end gap-1">
                            <Button
                              variant="link"
                              onClick={() =>
                                onAction(contact.id, 'pipeline', recommendation.draftMessage)
                              }
                              disabled={inPipeline(contact.id)}
                              title={
                                inPipeline(contact.id)
                                  ? 'Already has an open pipeline case'
                                  : undefined
                              }
                            >
                              <Briefcase size={13} />
                              Add to pipeline
                            </Button>
                            <Button
                              variant="link"
                              onClick={() =>
                                onAction(contact.id, 'task', recommendation.draftMessage)
                              }
                            >
                              Create task
                            </Button>
                            <Button
                              variant="danger"
                              onClick={() =>
                                onAction(contact.id, 'dismissed', recommendation.draftMessage)
                              }
                              aria-label={'Dismiss ' + contact.name}
                            >
                              <X size={13} />
                            </Button>
                          </div>
                        )}
                      </td>
                      </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
      )}

      {!isLeadCampaign && incomplete.length > 0 && (
        <section className="rounded-lg border border-line bg-white">
          <div className="flex items-center gap-2 border-b border-line px-5 py-4">
            <CircleAlert size={15} className="text-amber" />
            <div>
              <h2 className="text-[15px] font-semibold text-ink">
                Incomplete profiles ({incomplete.length})
              </h2>
              <p className="mt-0.5 text-[12px] text-muted">
                Held out of the audience because a field this campaign filters on is missing. Fill
                the gap and they are included automatically.
              </p>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b border-line">
                  <th className="table-head">Client</th>
                  <th className="table-head">On file</th>
                  <th className="table-head">Missing</th>
                </tr>
              </thead>
              <tbody>
                {incomplete.map((contact) => (
                  <tr
                    key={contact.id}
                    className="border-b border-line-soft transition-colors last:border-0 hover:bg-gray-50/60"
                  >
                    <td className="cell">
                      <button
                        onClick={() => onViewContact(contact.id)}
                        className="font-medium text-link hover:underline"
                      >
                        {contact.name}
                      </button>
                    </td>
                    <td className="cell text-muted">
                      {describeContactTargeting(contact) || EMPTY}
                    </td>
                    <td className="cell">
                      <div className="flex flex-wrap gap-1.5">
                        {missingFieldsFor(contact, campaign.criteria).map((field) => (
                          <span
                            key={field}
                            className="inline-flex items-center rounded bg-amber-soft px-2 py-0.5 text-[11px] font-medium text-amber"
                          >
                            {field}
                          </span>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {sendingEmail && (
        <SendCampaignEmailModal
          campaign={campaign}
          recipients={matched}
          session={session}
          signOff={signOff}
          onEditSignOff={onEditSignOff}
          onClose={() => setSendingEmail(false)}
          onSend={onSendEmail}
        />
      )}
    </div>
  );
}
