import { ChevronRight, Mail, Megaphone, Plus, Users } from 'lucide-react';
import { Campaign, Contact } from '../types';
import Button from '../ui/Button';
import SummaryCard from './SummaryCard';
import { CriteriaSummary } from './CampaignCriteria';
import { resolveAudience } from '../lib/targeting';
import { describeRouting } from '../lib/directory';
import { emailedContactIds } from '../lib/email';
import { formatDate } from '../lib/format';

interface MarketingCampaignsViewProps {
  campaigns: Campaign[];
  contacts: Contact[];
  onNewCampaign: () => void;
  onOpenCampaign: (campaignId: string) => void;
}

/**
 * Marketing's home screen. Deliberately shows reach and response counts rather
 * than the client list itself — marketing sets the criteria, advisors own the
 * relationships.
 */
export default function MarketingCampaignsView({
  campaigns,
  contacts,
  onNewCampaign,
  onOpenCampaign,
}: MarketingCampaignsViewProps) {
  const totalReach = campaigns.reduce(
    (sum, campaign) => sum + resolveAudience(campaign, contacts).matched.length,
    0,
  );

  const totalActions = campaigns.reduce(
    (sum, campaign) =>
      sum + Object.values(campaign.actions).filter((a) => a !== 'dismissed').length,
    0,
  );

  return (
    <div className="flex flex-col gap-5">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <SummaryCard
          title="Live Campaigns"
          value={campaigns.length}
          caption="sent to advisor channels"
          icon="flag"
        />
        <SummaryCard
          title="Total Reach"
          value={totalReach}
          caption="client matches across all campaigns"
          icon="eye"
        />
        <SummaryCard
          title="Advisor Actions"
          value={totalActions}
          caption="clients taken up by advisors"
          icon="bookmark"
        />
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-[18px] font-semibold text-ink">Campaigns</h1>
          <p className="mt-0.5 text-[13px] text-muted">
            Everything Marketing has sent out, newest first.
          </p>
        </div>

        <Button variant="primary" onClick={onNewCampaign}>
          <Plus size={15} />
          New Campaign
        </Button>
      </div>

      {campaigns.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-line bg-white py-16">
          <Megaphone size={22} className="text-faint" />
          <p className="text-[13px] text-muted">No campaigns yet.</p>
          <Button variant="primary" onClick={onNewCampaign}>
            <Plus size={15} />
            Create the first one
          </Button>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {campaigns.map((campaign) => {
            const { matched, incomplete } = resolveAudience(campaign, contacts);
            const isLeads = campaign.audienceSource === 'leads';
            const taken = Object.values(campaign.actions).filter((a) => a !== 'dismissed').length;
            const emailed = emailedContactIds(campaign.emailLog).size;

            return (
              <button
                key={campaign.id}
                onClick={() => onOpenCampaign(campaign.id)}
                className="flex flex-col gap-4 rounded-lg border border-line bg-white p-5 text-left transition-colors hover:border-accent"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h2 className="text-[15px] font-semibold text-ink">{campaign.name}</h2>
                    <p className="mt-0.5 text-[12px] text-faint">
                      {describeRouting(campaign)} · sent {formatDate(campaign.createdAt)}
                    </p>
                  </div>

                  <div className="flex items-center gap-3">
                    <div className="flex items-center gap-1.5 rounded-full bg-accent-soft px-3 py-1">
                      <Users size={13} className="text-accent-hover" />
                      <span className="text-[12px] font-medium text-accent-hover">
                        {matched.length} {isLeads ? 'leads' : 'matched'}
                      </span>
                    </div>
                    <ChevronRight size={16} className="text-faint" />
                  </div>
                </div>

                {campaign.bannerDataUrl && (
                  <img
                    src={campaign.bannerDataUrl}
                    alt={'Banner for ' + campaign.name}
                    className="max-h-32 w-full rounded-md object-cover"
                  />
                )}

                <p className="text-[13px] leading-relaxed text-body">{campaign.description}</p>

                {isLeads ? (
                  <p className="text-[12px] text-muted">
                    Uploaded lead list · {campaign.leadStats.uploaded} names ·{' '}
                    {campaign.leadStats.added} added to contacts · {campaign.leadStats.removed}{' '}
                    removed
                  </p>
                ) : (
                  <CriteriaSummary criteria={campaign.criteria} />
                )}

                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line-soft pt-3 text-[12px] text-muted">
                  <span>
                    <span className="font-medium text-ink">{taken}</span> taken up by advisors
                  </span>
                  <span className="flex items-center gap-1">
                    <Mail size={11} />
                    <span className="font-medium text-ink">{emailed}</span> emailed by advisors
                  </span>
                  {!isLeads && incomplete.length > 0 && (
                    <span className="text-amber">
                      {incomplete.length} excluded for incomplete profiles
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
