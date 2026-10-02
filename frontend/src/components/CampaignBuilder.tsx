import { useMemo, useRef, useState } from 'react';
import { ArrowLeft, Image as ImageIcon, Send, Upload, Users, X } from 'lucide-react';
import {
  Campaign,
  CampaignAudienceSource,
  CampaignCriteria,
  CampaignOrigin,
  Contact,
} from '../types';
import Button from '../ui/Button';
import { CriteriaPicker } from './CampaignCriteria';
import CampaignAudiencePicker from './CampaignAudiencePicker';
import LeadUploadPanel from './LeadUploadPanel';
import { EMPTY_CRITERIA, criteriaCount, resolveAudience } from '../lib/targeting';
import { CHANNELS } from '../lib/directory';
import CampaignRoutingPicker, { Routing } from './CampaignRoutingPicker';
import { newId, todayISO } from '../lib/format';

interface CampaignBuilderProps {
  /** Active contacts only — leads are never selectable as an audience. */
  contacts: Contact[];
  createdBy: string;
  /**
   * Marketing campaigns pick a channel and go out to an advisor group. Advisor
   * campaigns have no channel at all — they are private to their author, so the
   * whole routing section is absent rather than disabled.
   */
  origin: CampaignOrigin;
  /** Stamped onto advisor campaigns so only their author ever sees them. */
  advisorId?: string;
  onCancel: () => void;
  /** Leads arrive unsaved; App creates the contact records and assigns ids. */
  onSubmit: (campaign: Campaign, leads?: Omit<Contact, 'id'>[]) => void;
}

/** No backend, so the banner is held in memory as a data URL. Keep it small. */
const MAX_BANNER_BYTES = 1_000_000;

const COPY: Record<CampaignOrigin, { heading: string; blurb: string; submit: string }> = {
  marketing: {
    heading: 'New campaign',
    blurb:
      'Advisors on the selected channel receive this campaign along with the clients in their book who meet the criteria.',
    submit: 'Send to advisors',
  },
  advisor: {
    heading: 'New personal campaign',
    blurb:
      'Your own campaign. It is not sent to anyone — it stays in your campaign list and you decide who to email.',
    submit: 'Create campaign',
  },
};

const SOURCES: Record<
  CampaignOrigin,
  { id: CampaignAudienceSource; title: string; blurb: string; icon: typeof Users }[]
> = {
  marketing: [
    {
      id: 'contacts',
      title: 'Existing clients',
      blurb: 'Target by criteria. Each advisor sees the matches in their own book.',
      icon: Users,
    },
    {
      id: 'leads',
      title: 'Uploaded list',
      blurb: 'Names from an event or campaign. Advisors triage them, not your CRM.',
      icon: Upload,
    },
  ],
  advisor: [
    {
      id: 'contacts',
      title: 'My contacts',
      blurb: 'Target your book by criteria, then add or drop individuals.',
      icon: Users,
    },
    {
      id: 'leads',
      title: 'Uploaded list',
      blurb: 'Names from a roadshow or canvassing. Held apart from your contacts.',
      icon: Upload,
    },
  ],
};

export default function CampaignBuilder({
  contacts,
  createdBy,
  origin,
  advisorId,
  onCancel,
  onSubmit,
}: CampaignBuilderProps) {
  const copy = COPY[origin];

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [clientMessage, setClientMessage] = useState('');
  const [routing, setRouting] = useState<Routing>({
    channel: CHANNELS[0].code,
    teamIds: [],
    advisorIds: [],
  });
  const [criteria, setCriteria] = useState<CampaignCriteria>(EMPTY_CRITERIA);
  const [banner, setBanner] = useState<{ dataUrl: string; fileName: string } | null>(null);
  const [bannerError, setBannerError] = useState('');
  const [touched, setTouched] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  // Marketing has no book of business to pick from, so it is always criteria.
  const [audienceSource, setAudienceSource] = useState<CampaignAudienceSource>('contacts');
  const [includeIds, setIncludeIds] = useState<string[]>([]);
  const [excludeIds, setExcludeIds] = useState<string[]>([]);
  const [leads, setLeads] = useState<Omit<Contact, 'id'>[]>([]);

  const isLeadCampaign = audienceSource === 'leads';

  // Recomputed on every change — the point of the panel is that you watch the
  // audience move while you are still choosing.
  const preview = useMemo(
    () =>
      resolveAudience(
        { audienceSource: 'contacts', criteria, includeIds, excludeIds, leadIds: [] },
        contacts,
      ),
    [criteria, includeIds, excludeIds, contacts],
  );

  const fromCriteria = preview.matched.length - includeIds.length;
  const audienceCount = isLeadCampaign ? leads.length : preview.matched.length;

  const errors = {
    name: !name.trim() ? 'Campaign name is required.' : '',
    description: !description.trim() ? 'A description is required.' : '',
    clientMessage: !clientMessage.trim() ? 'Client messaging is required.' : '',
    leads: isLeadCampaign && leads.length === 0 ? 'Upload a list with at least one usable row.' : '',
  };

  const isValid = !errors.name && !errors.description && !errors.clientMessage && !errors.leads;

  const handleBanner = (file: File | undefined) => {
    if (!file) return;
    setBannerError('');

    if (!file.type.startsWith('image/')) {
      setBannerError('Choose an image file.');
      return;
    }
    if (file.size > MAX_BANNER_BYTES) {
      const mb = (file.size / 1_000_000).toFixed(1);
      setBannerError(
        'That image is ' +
          mb +
          'MB. The limit is 1MB — there is no file storage behind this prototype.',
      );
      return;
    }

    const reader = new FileReader();
    reader.onload = () => setBanner({ dataUrl: String(reader.result), fileName: file.name });
    reader.onerror = () => setBannerError('That file could not be read.');
    reader.readAsDataURL(file);
  };

  const handleSubmit = () => {
    setTouched(true);
    if (!isValid) return;

    onSubmit(
      {
        id: newId(),
        name: name.trim(),
        description: description.trim(),
        clientMessage: clientMessage.trim(),
        bannerDataUrl: banner?.dataUrl,
        origin,
        audienceSource: isLeadCampaign ? 'leads' : 'contacts',
        channel: origin === 'marketing' ? routing.channel : undefined,
        teamIds: origin === 'marketing' ? routing.teamIds : [],
        advisorIds: origin === 'marketing' ? routing.advisorIds : [],
        createdByAdvisorId: origin === 'advisor' ? advisorId : undefined,
        criteria: isLeadCampaign ? EMPTY_CRITERIA : criteria,
        includeIds: isLeadCampaign ? [] : includeIds,
        excludeIds: isLeadCampaign ? [] : excludeIds,
        leadIds: [],
        leadStats: { uploaded: 0, added: 0, removed: 0 },
        createdBy,
        createdAt: todayISO(),
        actions: {},
        emailLog: [],
      },
      isLeadCampaign ? leads : undefined,
    );
  };

  const errorFor = (key: keyof typeof errors) =>
    touched && errors[key] ? <p className="mt-1 text-[11px] text-danger">{errors[key]}</p> : null;

  return (
    <div className="flex flex-col gap-5">
      <button
        onClick={onCancel}
        className="flex w-fit items-center gap-1.5 text-[13px] text-link hover:underline"
      >
        <ArrowLeft size={15} />
        Campaigns
      </button>

      <div>
        <h1 className="text-[20px] font-semibold text-ink">{copy.heading}</h1>
        <p className="mt-1 text-[13px] text-muted">{copy.blurb}</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_340px] gap-5 items-start">
        <div className="flex flex-col gap-5">
          <section className="rounded-lg border border-line bg-white p-5 flex flex-col gap-4">
              <div>
                <h2 className="text-[14px] font-semibold text-ink">Who is this for?</h2>
                <p className="mt-1 text-[12px] text-muted">
                  A campaign works one or the other, never both.
                </p>
              </div>

              <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                {SOURCES[origin].map((option) => {
                  const Icon = option.icon;
                  const isActive = audienceSource === option.id;

                  return (
                    <button
                      key={option.id}
                      type="button"
                      onClick={() => setAudienceSource(option.id)}
                      aria-pressed={isActive}
                      className={`flex items-start gap-3 rounded-lg border p-3.5 text-left transition-colors ${
                        isActive ? 'border-accent bg-accent-soft/60' : 'border-line hover:bg-gray-50'
                      }`}
                    >
                      <span
                        className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${
                          isActive ? 'bg-accent text-white' : 'bg-line-soft text-muted'
                        }`}
                      >
                        <Icon size={14} />
                      </span>
                      <span className="flex flex-col gap-0.5">
                        <span
                          className={`text-[13px] font-semibold ${
                            isActive ? 'text-accent-hover' : 'text-ink'
                          }`}
                        >
                          {option.title}
                        </span>
                        <span className="text-[11px] leading-snug text-muted">{option.blurb}</span>
                      </span>
                    </button>
                  );
                })}
              </div>
          </section>

          <section className="rounded-lg border border-line bg-white p-5 flex flex-col gap-4">
            <h2 className="text-[14px] font-semibold text-ink">Campaign details</h2>

            <div className="flex flex-col gap-1.5">
              <label className="field-label" htmlFor="campaign-name">
                Campaign name *
              </label>
              <input
                id="campaign-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Legacy Protection Refresh"
                className="input-field"
                autoFocus
              />
              {errorFor('name')}
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="field-label" htmlFor="campaign-description">
                Campaign description *
              </label>
              <p className="-mt-1 text-[11px] text-faint">
                {origin === 'marketing'
                  ? 'Internal brief for advisors — what this is and how to position it.'
                  : 'Your own notes on what this campaign is for. Nobody else sees it.'}
              </p>
              <textarea
                id="campaign-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={4}
                placeholder="What the campaign is, who it is for, and how advisors should approach it."
                className="input-field resize-y"
              />
              {errorFor('description')}
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="field-label" htmlFor="campaign-message">
                Client messaging *
              </label>
              <p className="-mt-1 text-[11px] text-faint">
                {origin === 'marketing'
                  ? 'Goes to the client. Advisors see a personalised draft built from this.'
                  : 'Goes to the recipient. This is the body of any email you send from this campaign.'}
              </p>
              <textarea
                id="campaign-message"
                value={clientMessage}
                onChange={(e) => setClientMessage(e.target.value)}
                rows={4}
                placeholder="The message the end client reads."
                className="input-field resize-y"
              />
              {errorFor('clientMessage')}
            </div>

            <div className="flex flex-col gap-1.5">
              <span className="field-label">Banner or image</span>

              {banner ? (
                <div className="rounded-md border border-line overflow-hidden">
                  <img
                    src={banner.dataUrl}
                    alt="Campaign banner preview"
                    className="w-full max-h-44 object-cover"
                  />
                  <div className="flex items-center justify-between gap-3 border-t border-line-soft px-3 py-2">
                    <span className="truncate text-[12px] text-muted">{banner.fileName}</span>
                    <button
                      onClick={() => {
                        setBanner(null);
                        if (fileInput.current) fileInput.current.value = '';
                      }}
                      className="flex shrink-0 items-center gap-1 text-[12px] text-danger hover:underline"
                    >
                      <X size={13} />
                      Remove
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  onClick={() => fileInput.current?.click()}
                  className="flex flex-col items-center justify-center gap-1.5 rounded-md border border-dashed border-line py-7 text-muted transition-colors hover:border-accent hover:text-accent"
                >
                  <ImageIcon size={20} />
                  <span className="text-[13px]">Upload a banner</span>
                  <span className="text-[11px] text-faint">PNG or JPEG, up to 1MB</span>
                </button>
              )}

              <input
                ref={fileInput}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(e) => handleBanner(e.target.files?.[0])}
              />
              {bannerError && <p className="mt-1 text-[11px] text-danger">{bannerError}</p>}
            </div>
          </section>

          {isLeadCampaign ? (
            <section className="rounded-lg border border-line bg-white p-5 flex flex-col gap-4">
              <div>
                <h2 className="text-[14px] font-semibold text-ink">Lead list</h2>
                <p className="mt-1 text-[12px] text-muted">
                  {origin === 'marketing'
                    ? 'These names go to the advisors you route to, who promote or discard them. They never enter the CRM on upload. No targeting criteria apply.'
                    : 'These names stay out of your contacts until you promote them. No targeting criteria apply — the uploaded list is the audience.'}
                </p>
              </div>

              <LeadUploadPanel onChange={setLeads} />
              {errorFor('leads')}
            </section>
          ) : (
            <>
              <section className="rounded-lg border border-line bg-white p-5 flex flex-col gap-4">
                <div>
                  <h2 className="text-[14px] font-semibold text-ink">Targeting criteria</h2>
                  <p className="mt-1 text-[12px] text-muted">
                    Clients must match every dimension you set. Leave one untouched to ignore it.
                  </p>
                </div>

                <CriteriaPicker criteria={criteria} onChange={setCriteria} />
              </section>

              {origin === 'advisor' && (
                <section className="rounded-lg border border-line bg-white p-5 flex flex-col gap-4">
                  <div>
                    <h2 className="text-[14px] font-semibold text-ink">Audience</h2>
                    <p className="mt-1 text-[12px] text-muted">
                      Criteria stay live as your book changes. Anyone you add or drop here overrides
                      them.
                    </p>
                  </div>

                  <CampaignAudiencePicker
                    contacts={contacts}
                    audience={preview.matched}
                    includeIds={includeIds}
                    excludeIds={excludeIds}
                    onChange={(next) => {
                      setIncludeIds(next.includeIds);
                      setExcludeIds(next.excludeIds);
                    }}
                  />
                </section>
              )}
            </>
          )}

          {origin === 'marketing' && (
            <section className="rounded-lg border border-line bg-white p-5 flex flex-col gap-4">
              <div>
                <h2 className="text-[14px] font-semibold text-ink">Send to</h2>
                <p className="mt-1 text-[12px] text-muted">
                  Pick a channel, then narrow to specific teams or advisors. Leave a level
                  untouched to include all of it.
                </p>
              </div>

              <CampaignRoutingPicker routing={routing} onChange={setRouting} />
            </section>
          )}
        </div>

        <aside className="flex flex-col gap-4 rounded-lg border border-line bg-white p-5 lg:sticky lg:top-2">
          <div className="flex items-center gap-2">
            <Users size={15} className="text-accent" />
            <h2 className="text-[14px] font-semibold text-ink">
              {isLeadCampaign ? 'Uploaded leads' : 'Estimated audience'}
            </h2>
          </div>

          <div>
            <p className="text-[30px] font-semibold leading-none text-ink">{audienceCount}</p>
            <p className="mt-1 text-[12px] text-muted">
              {isLeadCampaign
                ? 'usable rows in your upload'
                : criteriaCount(criteria) === 0 && includeIds.length === 0
                  ? 'every contact — no criteria set yet'
                  : 'of ' + contacts.length + ' contacts'}
            </p>
          </div>

          {!isLeadCampaign && (includeIds.length > 0 || excludeIds.length > 0) && (
            <p className="text-[12px] text-muted">
              {fromCriteria} from criteria
              {includeIds.length > 0 && (
                <span className="text-purple"> · +{includeIds.length} added</span>
              )}
              {excludeIds.length > 0 && (
                <span className="text-danger"> · −{excludeIds.length} removed</span>
              )}
            </p>
          )}

          {!isLeadCampaign && preview.incomplete.length > 0 && (
            <div className="rounded-md bg-amber-soft px-3 py-2.5">
              <p className="text-[12px] leading-snug text-amber">
                <span className="font-semibold">{preview.incomplete.length} excluded</span> — their
                records are missing a field this campaign filters on. Advisors are prompted to
                complete them.
              </p>
            </div>
          )}

          {!isLeadCampaign && audienceCount === 0 && criteriaCount(criteria) > 0 && (
            <div className="rounded-md bg-danger-soft px-3 py-2.5">
              <p className="text-[12px] leading-snug text-danger">
                Nothing matches this combination. Widen a dimension before sending.
              </p>
            </div>
          )}

          {isLeadCampaign && audienceCount === 0 && (
            <div className="rounded-md bg-line-soft px-3 py-2.5">
              <p className="text-[12px] leading-snug text-muted">
                Upload a list to see who this campaign will cover.
              </p>
            </div>
          )}

          {!isLeadCampaign && preview.matched.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <span className="field-label">Sample</span>
              <ul className="flex flex-col gap-1">
                {preview.matched.slice(0, 5).map((contact) => (
                  <li key={contact.id} className="truncate text-[12px] text-body">
                    {contact.name}
                  </li>
                ))}
              </ul>
              {preview.matched.length > 5 && (
                <span className="text-[11px] text-faint">
                  and {preview.matched.length - 5} more
                </span>
              )}
            </div>
          )}

          <div className="flex flex-col gap-2 border-t border-line-soft pt-4">
            <Button variant="primary" onClick={handleSubmit} disabled={touched && !isValid}>
              <Send size={14} />
              {copy.submit}
            </Button>
            <Button variant="secondary" onClick={onCancel}>
              Cancel
            </Button>
          </div>
        </aside>
      </div>
    </div>
  );
}
