import { ChevronRight, Mail, Megaphone, PenLine, Plus, Upload, User, Users } from 'lucide-react';
import { Campaign, Contact } from '../types';
import Button from '../ui/Button';
import SummaryCard from './SummaryCard';
import { CriteriaSummary } from './CampaignCriteria';
import { resolveAudience } from '../lib/targeting';
import { channelName, teamById } from '../lib/directory';
import { emailedContactIds } from '../lib/email';
import { formatDate } from '../lib/format';

interface CampaignsViewProps {
  campaigns: Campaign[];
  contacts: Contact[];
  onOpenCampaign: (campaignId: string) => void;
  onNewCampaign: () => void;
  onEditSignOff: () => void;
}

/**
 * The advisor's inbox. Campaigns arrive here from Marketing; the advisor never
 * authors one, so there is no create action on this screen.
 */
export default function CampaignsView({
  campaigns,
  contacts,
  onOpenCampaign,
  onNewCampaign,
  onEditSignOff,
}: CampaignsViewProps) {
  const received = campaigns.filter((c) => c.origin === 'marketing').length;
  const own = campaigns.length - received;
  const stats = campaigns.reduce(
    (acc, campaign) => {
      const { matched } = resolveAudience(campaign, contacts);

      // A lead is outstanding until it is promoted; removed ones are gone from
      // the list entirely, so what is left un-promoted is the work remaining.
      const handled =
        campaign.audienceSource === 'leads'
          ? matched.filter((c) => c.status !== 'lead').length
          : Object.keys(campaign.actions).length;

      acc.reach += matched.length;
      acc.outstanding += Math.max(matched.length - handled, 0);
      return acc;
    },
    { reach: 0, outstanding: 0 },
  );

  return (
    <div className="flex flex-col gap-5">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <SummaryCard
          title="Campaigns"
          value={campaigns.length}
          caption={`${received} from Marketing · ${own} your own`}
          icon="flag"
        />
        <SummaryCard
          title="Clients Identified"
          value={stats.reach}
          caption="across all campaigns"
          icon="eye"
        />
        <SummaryCard
          title="Awaiting Your Action"
          value={stats.outstanding}
          caption="clients you have not responded to"
          icon="alert"
        />
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-[18px] font-semibold text-ink">Campaigns</h1>
          <p className="mt-0.5 text-[13px] text-muted">
            Sent by Marketing, plus your own. Each lists the clients from your book who match.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button variant="primary" onClick={onNewCampaign}>
            <Plus size={15} />
            New Campaign
          </Button>
          <Button variant="secondary" onClick={onEditSignOff}>
            <PenLine size={14} />
            Email sign-off
          </Button>
        </div>
      </div>

      {campaigns.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-line bg-white py-16">
          <Megaphone size={22} className="text-faint" />
          <p className="text-[13px] text-muted">
            No campaigns yet — none received, and none of your own.
          </p>
          <Button variant="primary" onClick={onNewCampaign}>
            <Plus size={15} />
            Create your own
          </Button>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {campaigns.map((campaign) => {
            const { matched } = resolveAudience(campaign, contacts);
            const isLeads = campaign.audienceSource === 'leads';
            const handled = isLeads
              ? matched.filter((c) => c.status !== 'lead').length
              : Object.keys(campaign.actions).length;
            const outstanding = Math.max(matched.length - handled, 0);
            const emailed = emailedContactIds(campaign.emailLog).size;

            return (
              <button
                key={campaign.id}
                onClick={() => onOpenCampaign(campaign.id)}
                className="flex flex-col gap-4 rounded-lg border border-line bg-white p-5 text-left transition-colors hover:border-accent"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h2 className="text-[15px] font-semibold text-ink">{campaign.name}</h2>
                      {campaign.origin === 'advisor' && (
                        <span className="inline-flex items-center gap-1 rounded bg-purple-soft px-2 py-0.5 text-[11px] font-medium text-purple">
                          <User size={10} />
                          Your campaign
                        </span>
                      )}
                      {isLeads && (
                        <span className="inline-flex items-center gap-1 rounded bg-amber-soft px-2 py-0.5 text-[11px] font-medium text-amber">
                          <Upload size={10} />
                          Lead list
                        </span>
                      )}
                    </div>
                    <p className="mt-0.5 text-[12px] text-faint">
                      {campaign.origin === 'advisor'
                        ? `Created by you · ${
                            isLeads ? `${campaign.leadStats.uploaded} uploaded · ` : ''
                          }${formatDate(campaign.createdAt)}`
                        : `${campaign.createdBy} · ${channelName(campaign.channel ?? '')}${
                            campaign.teamIds.length > 0
                              ? ` · ${campaign.teamIds
                                  .map((id) => teamById(id)?.name ?? id)
                                  .join(', ')}`
                              : ''
                          }${
                            campaign.advisorIds.length > 0 ? ' · sent to you directly' : ''
                          } · ${formatDate(campaign.createdAt)}`}
                    </p>
                  </div>

                  <div className="flex items-center gap-3">
                    <div className="flex items-center gap-1.5 rounded-full bg-accent-soft px-3 py-1">
                      <Users size={13} className="text-accent-hover" />
                      <span className="text-[12px] font-medium text-accent-hover">
                        {matched.length} {isLeads ? 'leads' : 'identified'}
                      </span>
                    </div>
                    <ChevronRight size={16} className="text-faint" />
                  </div>
                </div>

                {campaign.bannerDataUrl && (
                  <img
                    src={campaign.bannerDataUrl}
                    alt={'Banner for ' + campaign.name}
                    className="max-h-28 w-full rounded-md object-cover"
                  />
                )}

                <p className="line-clamp-2 text-[13px] leading-relaxed text-body">
                  {campaign.description}
                </p>

                {!isLeads && <CriteriaSummary criteria={campaign.criteria} />}

                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line-soft pt-3 text-[12px]">
                  {outstanding > 0 ? (
                    <span className="text-accent-hover">
                      {outstanding} {isLeads ? 'lead' : 'client'}
                      {outstanding === 1 ? '' : 's'} awaiting your action
                    </span>
                  ) : (
                    <span className="text-success">
                      {isLeads ? 'Every lead dealt with' : 'All identified clients handled'}
                    </span>
                  )}

                  {emailed > 0 && (
                    <span className="flex items-center gap-1 text-muted">
                      <Mail size={11} />
                      {emailed} emailed
                    </span>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
