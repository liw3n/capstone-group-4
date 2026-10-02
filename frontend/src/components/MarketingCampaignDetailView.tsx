import { useMemo } from 'react';
import { ArrowLeft, Mail, Upload, Users } from 'lucide-react';
import { Campaign, Contact } from '../types';
import SummaryCard from './SummaryCard';
import { CriteriaSummary } from './CampaignCriteria';
import { resolveAudience } from '../lib/targeting';
import { describeRouting, resolveRecipients, resolveTeams } from '../lib/directory';
import { emailedContactIds } from '../lib/email';
import { formatDate } from '../lib/format';

interface MarketingCampaignDetailViewProps {
  campaign: Campaign;
  contacts: Contact[];
  onBack: () => void;
}

/**
 * Marketing's read-only view of a campaign it sent.
 *
 * Everything here is an aggregate. Marketing sets the criteria and owns the
 * message; the advisor owns the relationship, so this screen never names a
 * client. It does name advisors — they are staff, and knowing which of them has
 * not touched a campaign is the whole point of sending it.
 */
export default function MarketingCampaignDetailView({
  campaign,
  contacts,
  onBack,
}: MarketingCampaignDetailViewProps) {
  const isLeads = campaign.audienceSource === 'leads';

  const { matched, incomplete } = useMemo(
    () => resolveAudience(campaign, contacts),
    [campaign, contacts],
  );

  const recipients = useMemo(() => resolveRecipients(campaign), [campaign]);
  const teams = useMemo(() => resolveTeams(campaign), [campaign]);

  const emailedIds = useMemo(() => emailedContactIds(campaign.emailLog), [campaign.emailLog]);

  /**
   * Four mutually exclusive buckets over the audience, so the bar always sums
   * to the whole. "Emailed, awaiting" is the one marketing should care about:
   * the message landed and nothing came of it yet.
   */
  const funnel = useMemo(() => {
    const actions = campaign.actions;
    let takenUp = 0;
    let dismissed = 0;
    let emailedWaiting = 0;
    let untouched = 0;

    for (const person of matched) {
      const action = actions[person.id];
      if (action === 'pipeline' || action === 'task') takenUp++;
      else if (action === 'dismissed') dismissed++;
      else if (emailedIds.has(person.id)) emailedWaiting++;
      else untouched++;
    }

    return { takenUp, dismissed, emailedWaiting, untouched, total: matched.length };
  }, [matched, campaign.actions, emailedIds]);

  const totalEmailed = emailedIds.size;
  const takeUpRate =
    funnel.total > 0 ? Math.round((funnel.takenUp / funnel.total) * 100) : 0;

  const leadConversion =
    campaign.leadStats.uploaded > 0
      ? Math.round((campaign.leadStats.added / campaign.leadStats.uploaded) * 100)
      : 0;

  const SEGMENTS = [
    { key: 'takenUp', label: 'Taken up', value: funnel.takenUp, bar: 'bg-success', dot: 'bg-success' },
    {
      key: 'emailedWaiting',
      label: 'Emailed, awaiting',
      value: funnel.emailedWaiting,
      bar: 'bg-link',
      dot: 'bg-link',
    },
    { key: 'dismissed', label: 'Dismissed', value: funnel.dismissed, bar: 'bg-danger', dot: 'bg-danger' },
    {
      key: 'untouched',
      label: 'Not contacted',
      value: funnel.untouched,
      bar: 'bg-line',
      dot: 'bg-line',
    },
  ];

  return (
    <div className="flex flex-col gap-5">
      <button
        onClick={onBack}
        className="flex w-fit items-center gap-1.5 text-[13px] text-link hover:underline"
      >
        <ArrowLeft size={15} />
        Campaigns
      </button>

      <div>
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-[20px] font-semibold text-ink">{campaign.name}</h1>
          {isLeads && (
            <span className="inline-flex items-center gap-1 rounded bg-amber-soft px-2 py-0.5 text-[11px] font-medium text-amber">
              <Upload size={10} />
              Lead list
            </span>
          )}
        </div>
        <p className="mt-1 text-[12px] text-faint">
          {describeRouting(campaign)} · sent {formatDate(campaign.createdAt)}
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <SummaryCard
          title="Advisors Reached"
          value={recipients.length}
          caption={`across ${teams.length} team${teams.length === 1 ? '' : 's'}`}
          icon="flag"
        />
        <SummaryCard
          title={isLeads ? 'Leads Uploaded' : 'Clients Identified'}
          value={isLeads ? campaign.leadStats.uploaded : matched.length}
          caption={isLeads ? 'names sent to advisors' : 'matched the criteria'}
          icon="eye"
        />
        <SummaryCard
          title={isLeads ? 'Added To Contacts' : 'Taken Up'}
          value={isLeads ? campaign.leadStats.added : funnel.takenUp}
          caption={isLeads ? `${leadConversion}% conversion` : `${takeUpRate}% of those identified`}
          icon="bookmark"
        />
        <SummaryCard
          title={isLeads ? 'Removed' : 'Dismissed'}
          value={isLeads ? campaign.leadStats.removed : funnel.dismissed}
          caption={isLeads ? 'discarded by advisors' : 'advisors passed on these'}
          icon="alert"
        />
      </div>

      {!isLeads && funnel.total > 0 && (
        <section className="rounded-lg border border-line bg-white p-5 flex flex-col gap-4">
          <div>
            <h2 className="text-[14px] font-semibold text-ink">What advisors did</h2>
            <p className="mt-1 text-[12px] text-muted">
              Every identified client, by outcome. A large "emailed, awaiting" share means the
              message landed but did not move anyone.
            </p>
          </div>

          <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-line-soft">
            {SEGMENTS.filter((s) => s.value > 0).map((segment) => (
              <div
                key={segment.key}
                className={segment.bar}
                style={{ width: `${(segment.value / funnel.total) * 100}%` }}
                title={`${segment.label}: ${segment.value}`}
              />
            ))}
          </div>

          <div className="flex flex-wrap gap-x-5 gap-y-2">
            {SEGMENTS.map((segment) => (
              <span key={segment.key} className="flex items-center gap-1.5 text-[12px]">
                <span className={`h-2 w-2 rounded-full ${segment.dot}`} />
                <span className="font-medium text-ink">{segment.value}</span>
                <span className="text-muted">{segment.label}</span>
              </span>
            ))}
          </div>

          {incomplete.length > 0 && (
            <p className="rounded-md bg-amber-soft px-3 py-2 text-[12px] text-amber">
              <span className="font-semibold">{incomplete.length} more</span> would have matched but
              are missing a field this campaign filters on. Advisors are prompted to complete them.
            </p>
          )}
        </section>
      )}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <section className="rounded-lg border border-line bg-white p-5 flex flex-col gap-4">
          <h2 className="text-[14px] font-semibold text-ink">Campaign content</h2>

          {campaign.bannerDataUrl && (
            <img
              src={campaign.bannerDataUrl}
              alt={'Banner for ' + campaign.name}
              className="max-h-40 w-full rounded-md object-cover"
            />
          )}

          <div className="flex flex-col gap-1.5">
            <span className="field-label">Brief to advisors</span>
            <p className="text-[13px] leading-relaxed text-body">{campaign.description}</p>
          </div>

          <div className="flex flex-col gap-1.5">
            <span className="field-label">Client messaging</span>
            <p className="rounded-md bg-link-soft px-4 py-3 text-[13px] leading-relaxed text-body">
              {campaign.clientMessage}
            </p>
          </div>

          <div className="flex flex-col gap-2 border-t border-line-soft pt-4">
            <span className="field-label">{isLeads ? 'Audience' : 'Targeting criteria'}</span>
            {isLeads ? (
              <p className="text-[12px] text-muted">
                Uploaded list of {campaign.leadStats.uploaded} names. No targeting criteria apply.
              </p>
            ) : (
              <CriteriaSummary criteria={campaign.criteria} />
            )}
          </div>
        </section>

        <div className="flex flex-col gap-5">
          <section className="rounded-lg border border-line bg-white p-5 flex flex-col gap-3">
            <div className="flex items-center gap-2">
              <Users size={15} className="text-accent" />
              <h2 className="text-[14px] font-semibold text-ink">
                Recipients ({recipients.length})
              </h2>
            </div>

            <div className="flex max-h-52 flex-col gap-3 overflow-y-auto">
              {teams.map((team) => {
                const members = recipients.filter((a) => a.teamId === team.id);
                if (members.length === 0) return null;

                return (
                  <div key={team.id} className="flex flex-col gap-1">
                    <span className="text-[11px] text-faint">
                      {team.name} · {members.length}
                    </span>
                    <p className="text-[12px] leading-relaxed text-body">
                      {members.map((m) => m.name).join(', ')}
                    </p>
                  </div>
                );
              })}
            </div>
          </section>

          <section className="rounded-lg border border-line bg-white p-5 flex flex-col gap-3">
            <div className="flex items-center gap-2">
              <Mail size={15} className="text-accent" />
              <h2 className="text-[14px] font-semibold text-ink">Email activity</h2>
            </div>

            {campaign.emailLog.length === 0 ? (
              <p className="text-[12px] text-muted">
                No advisor has emailed this campaign yet.
              </p>
            ) : (
              <>
                <p className="text-[12px] text-muted">
                  <span className="font-semibold text-ink">{totalEmailed}</span> recipient
                  {totalEmailed === 1 ? '' : 's'} across {campaign.emailLog.length} send
                  {campaign.emailLog.length === 1 ? '' : 's'}
                </p>

                <div className="flex flex-col gap-2">
                  {campaign.emailLog.slice(0, 5).map((entry) => (
                    <div
                      key={entry.id}
                      className="flex flex-col gap-0.5 border-b border-line-soft pb-2 last:border-0 last:pb-0"
                    >
                      <span className="text-[12px] text-body">{entry.subject}</span>
                      <span className="text-[11px] text-faint">
                        {entry.fromName} · {entry.recipientIds.length} recipient
                        {entry.recipientIds.length === 1 ? '' : 's'} · {formatDate(entry.sentAt)}
                      </span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
