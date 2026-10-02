import { Check, Mail, UserPlus, X } from 'lucide-react';
import { Campaign, Contact } from '../types';
import Button from '../ui/Button';
import { display, formatPhone } from '../lib/format';

interface LeadAudienceTableProps {
  campaign: Campaign;
  leads: Contact[];
  totalEmailed: number;
  onAddToContacts: (contactId: string) => void;
  onRemove: (contactId: string) => void;
  onEmail: () => void;
  onViewContact: (contactId: string) => void;
}

/**
 * Deliberately not the criteria table. A lead has no age band, no cash band, no
 * meeting history and no label, so priority, targeting match and the AI
 * rationale would all be blank or identical for every row — noise dressed up as
 * insight. What a roadshow list actually has is the contact details someone
 * scribbled down, so that is what this shows.
 */
export default function LeadAudienceTable({
  campaign,
  leads,
  totalEmailed,
  onAddToContacts,
  onRemove,
  onEmail,
  onViewContact,
}: LeadAudienceTableProps) {
  const { uploaded, added, removed } = campaign.leadStats;
  const pending = leads.filter((c) => c.status === 'lead').length;

  return (
    <section className="rounded-lg border border-line bg-white">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-5 py-4">
        <div>
          <h2 className="text-[15px] font-semibold text-ink">Uploaded leads ({leads.length})</h2>
          <p className="mt-0.5 text-[12px] text-muted">
            Held apart from your contacts. Promote the ones worth keeping, remove the rest.
          </p>
        </div>

        <div className="flex flex-col items-end gap-1">
          <Button variant="primary" onClick={onEmail} disabled={leads.length === 0}>
            <Mail size={14} />
            Email leads
          </Button>
          {totalEmailed > 0 && (
            <span className="text-[11px] text-faint">{totalEmailed} already emailed</span>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-x-6 gap-y-2 border-b border-line-soft bg-gray-50/60 px-5 py-3 text-[12px]">
        <Stat label="Uploaded" value={uploaded} />
        <Stat label="Pending" value={pending} />
        <Stat label="Added to contacts" value={added} tone="text-success" />
        <Stat label="Removed" value={removed} tone="text-danger" />
      </div>

      {leads.length === 0 ? (
        <p className="px-5 py-14 text-center text-[13px] text-muted">
          {removed > 0 || added > 0
            ? 'Every lead on this list has been dealt with.'
            : 'No leads on this campaign.'}
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr className="border-b border-line">
                <th className="table-head">Name</th>
                <th className="table-head">Email</th>
                <th className="table-head">Mobile</th>
                <th className="table-head text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {leads.map((lead) => {
                const promoted = lead.status !== 'lead';

                return (
                  <tr
                    key={lead.id}
                    className="border-b border-line-soft transition-colors last:border-0 hover:bg-gray-50/60"
                  >
                    <td className="cell">
                      {promoted ? (
                        <button
                          onClick={() => onViewContact(lead.id)}
                          className="font-medium text-link hover:underline"
                        >
                          {lead.name}
                        </button>
                      ) : (
                        <span className="flex items-center gap-2">
                          <span className="font-medium text-body">{lead.name}</span>
                          <span className="rounded bg-amber-soft px-2 py-0.5 text-[11px] font-medium text-amber">
                            Lead
                          </span>
                        </span>
                      )}
                    </td>
                    <td className="cell text-body">{display(lead.email)}</td>
                    <td className="cell text-body">{formatPhone(lead)}</td>
                    <td className="cell text-right">
                      {promoted ? (
                        <span className="inline-flex items-center gap-1.5 text-[12px] text-muted">
                          <Check size={13} className="text-success" />
                          Added to contacts
                        </span>
                      ) : (
                        <div className="flex items-center justify-end gap-1">
                          <Button variant="link" onClick={() => onAddToContacts(lead.id)}>
                            <UserPlus size={13} />
                            Add to contacts
                          </Button>
                          <Button
                            variant="danger"
                            onClick={() => onRemove(lead.id)}
                            aria-label={`Remove ${lead.name}`}
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
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return (
    <span className="flex items-baseline gap-1.5">
      <span className={`font-semibold ${tone ?? 'text-ink'}`}>{value}</span>
      <span className="text-muted">{label}</span>
    </span>
  );
}
