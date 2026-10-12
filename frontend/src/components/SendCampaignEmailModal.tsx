import { ReactNode, useMemo, useState } from 'react';
import { CircleAlert, Mail, Pencil, TriangleAlert } from 'lucide-react';
import { Campaign, Contact, Session } from '../types';
import Modal from '../ui/Modal';
import Button from '../ui/Button';
import { composeEmailBody, emailedContactIds, hasUsableEmail } from '../lib/email';
import { display } from '../lib/format';

interface SendCampaignEmailModalProps {
  campaign: Campaign;
  /** The matched audience. Who actually gets an email is chosen in here. */
  recipients: Contact[];
  session: Session;
  signOff: string;
  onEditSignOff: () => void;
  onClose: () => void;
  onSend: (recipientIds: string[], subject: string) => void;
}

type Stage = 'review' | 'confirm' | 'sent';

export default function SendCampaignEmailModal({
  campaign,
  recipients,
  session,
  signOff,
  onEditSignOff,
  onClose,
  onSend,
}: SendCampaignEmailModalProps) {
  const [stage, setStage] = useState<Stage>('review');
  const [subject, setSubject] = useState(campaign.name);

  const { eligible, unreachable, unconsented } = useMemo(() => {
    const eligible: Contact[] = [];
    const unreachable: Contact[] = [];
    const unconsented: Contact[] = [];
    for (const contact of recipients) {
      if (!hasUsableEmail(contact)) unreachable.push(contact);
      else if (!contact.optInEmail) unconsented.push(contact);
      else eligible.push(contact);
    }
    return { eligible, unreachable, unconsented };
  }, [recipients]);

  /** Everyone already emailed on this campaign, so a resend is a deliberate act. */
  const alreadyEmailed = useMemo(() => emailedContactIds(campaign.emailLog), [campaign.emailLog]);

  const [selected, setSelected] = useState<string[]>(() =>
    eligible
      .filter((c) => campaign.actions[c.id] !== 'dismissed' && !alreadyEmailed.has(c.id))
      .map((c) => c.id),
  );

  const [previewId, setPreviewId] = useState<string>(() => eligible[0]?.id ?? '');

  const previewContact =
    eligible.find((c) => c.id === previewId) ??
    eligible.find((c) => selected.includes(c.id)) ??
    eligible[0];

  const body = previewContact
    ? composeEmailBody({
        contact: previewContact,
        clientMessage: campaign.clientMessage,
        signOff,
        session,
      })
    : '';

  const toggle = (id: string) =>
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  const allSelected = eligible.length > 0 && selected.length === eligible.length;

  const canSend = selected.length > 0 && subject.trim().length > 0;

  /* ---------- sent receipt ---------- */

  if (stage === 'sent') {
    return (
      <Modal
        title="Campaign email sent"
        onClose={onClose}
        width="max-w-lg"
        footer={
          <Button variant="primary" onClick={onClose}>
            DONE
          </Button>
        }
      >
        <div className="flex flex-col gap-4">
          <div className="flex items-start gap-3 rounded-md bg-success-soft px-4 py-3">
            <Mail size={16} className="mt-0.5 shrink-0 text-success" />
            <div>
              <p className="text-[13px] font-medium text-success">
                {selected.length} email{selected.length === 1 ? '' : 's'} recorded as sent
              </p>
              <p className="mt-0.5 text-[12px] text-body">
                Subject: {subject.trim()} · from {session.email}
              </p>
            </div>
          </div>

          <div className="flex items-start gap-2 rounded-md bg-amber-soft px-4 py-3">
            <TriangleAlert size={15} className="mt-0.5 shrink-0 text-amber" />
            <p className="text-[12px] leading-snug text-amber">
              Nothing actually left the building. This prototype has no mail transport — the send
              is recorded against the campaign so the flow can be reviewed, and that is all.
            </p>
          </div>
        </div>
      </Modal>
    );
  }

  /* ---------- final confirmation ---------- */

  if (stage === 'confirm') {
    return (
      <Modal
        title="Confirm send"
        onClose={onClose}
        width="max-w-lg"
        footer={
          <>
            <Button variant="ghost" onClick={() => setStage('review')}>
              BACK
            </Button>
            <Button
              variant="primary"
              onClick={() => {
                onSend(selected, subject.trim());
                setStage('sent');
              }}
            >
              <Mail size={14} />
              Send {selected.length} email{selected.length === 1 ? '' : 's'}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          <p className="text-[13px] text-body">
            You are about to send this campaign to{' '}
            <span className="font-semibold text-ink">{selected.length}</span> client
            {selected.length === 1 ? '' : 's'}.
          </p>

          <dl className="flex flex-col gap-2 rounded-md border border-line px-4 py-3">
            <Row label="From">
              {session.name} &lt;{session.email}&gt;
            </Row>
            <Row label="Subject">{subject.trim()}</Row>
            <Row label="Recipients">
              {selected.length} of {eligible.length} identified clients with an email on file
            </Row>
            <Row label="Body">Campaign client messaging, plus your saved sign-off</Row>
          </dl>

          <div className="flex items-start gap-2 rounded-md bg-amber-soft px-4 py-3">
            <TriangleAlert size={15} className="mt-0.5 shrink-0 text-amber" />
            <p className="text-[12px] leading-snug text-amber">
              Prototype — no mail is actually transmitted. The send is recorded against the
              campaign only.
            </p>
          </div>
        </div>
      </Modal>
    );
  }

  /* ---------- review ---------- */

  return (
    <Modal
      title="Email identified clients"
      onClose={onClose}
      width="max-w-3xl"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            CANCEL
          </Button>
          <Button variant="primary" onClick={() => setStage('confirm')} disabled={!canSend}>
            <Mail size={14} />
            Review and send to {selected.length}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-5">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <span className="field-label">From</span>
            <div className="rounded-md border border-line bg-gray-50 px-3 py-2">
              <p className="text-[13px] text-body">{session.name}</p>
              <p className="text-[12px] text-faint">{session.email}</p>
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="field-label" htmlFor="email-subject">
              Subject
            </label>
            <input
              id="email-subject"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              className="input-field"
            />
            {!subject.trim() && <p className="text-[11px] text-danger">A subject is required.</p>}
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <span className="field-label">
              To — {selected.length} of {eligible.length} selected
            </span>
            <button
              type="button"
              onClick={() => setSelected(allSelected ? [] : eligible.map((c) => c.id))}
              className="text-[12px] text-link hover:underline"
            >
              {allSelected ? 'Clear all' : 'Select all'}
            </button>
          </div>

          <div className="max-h-52 overflow-y-auto rounded-md border border-line">
            {eligible.map((contact) => {
              const dismissed = campaign.actions[contact.id] === 'dismissed';
              const emailed = alreadyEmailed.has(contact.id);

              return (
                <label
                  key={contact.id}
                  className="flex cursor-pointer items-center gap-3 border-b border-line-soft px-3 py-2 last:border-0 hover:bg-gray-50"
                >
                  <input
                    type="checkbox"
                    checked={selected.includes(contact.id)}
                    onChange={() => toggle(contact.id)}
                    className="accent-accent cursor-pointer"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] text-body">{contact.name}</span>
                    <span className="block truncate text-[12px] text-faint">
                      {display(contact.email)}
                    </span>
                  </span>

                  {dismissed && (
                    <span className="shrink-0 rounded bg-line-soft px-2 py-0.5 text-[11px] text-muted">
                      Dismissed
                    </span>
                  )}
                  {emailed && (
                    <span className="shrink-0 rounded bg-link-soft px-2 py-0.5 text-[11px] text-link">
                      Already emailed
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={(e) => {
                      e.preventDefault();
                      setPreviewId(contact.id);
                    }}
                    className="shrink-0 text-[12px] text-link hover:underline"
                  >
                    Preview
                  </button>
                </label>
              );
            })}

            {eligible.length === 0 && (
              <p className="px-3 py-6 text-center text-[13px] text-muted">
                No identified client has both a usable email address and email consent.
              </p>
            )}
          </div>

          {unreachable.length > 0 && (
            <div className="flex items-start gap-2 rounded-md bg-amber-soft px-3 py-2.5">
              <CircleAlert size={14} className="mt-0.5 shrink-0 text-amber" />
              <p className="text-[12px] leading-snug text-amber">
                <span className="font-semibold">
                  {unreachable.length} excluded — no email on file:
                </span>{' '}
                {unreachable.map((c) => c.name).join(', ')}
              </p>
            </div>
          )}

          {unconsented.length > 0 && (
            <div className="flex items-start gap-2 rounded-md bg-amber-soft px-3 py-2.5">
              <CircleAlert size={14} className="mt-0.5 shrink-0 text-amber" />
              <p className="text-[12px] leading-snug text-amber">
                <span className="font-semibold">
                  {unconsented.length} excluded — no email consent:
                </span>{' '}
                {unconsented.map((contact) => contact.name).join(', ')}
              </p>
            </div>
          )}
        </div>

        {previewContact && (
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="field-label">
                Preview — as {previewContact.name} receives it
              </span>
              <button
                type="button"
                onClick={onEditSignOff}
                className="flex items-center gap-1 text-[12px] text-link hover:underline"
              >
                <Pencil size={11} />
                Edit sign-off
              </button>
            </div>

            <div className="rounded-md border border-line">
              <div className="border-b border-line-soft px-4 py-2 text-[12px] text-muted">
                <p>
                  <span className="text-faint">To:</span> {previewContact.name} &lt;
                  {previewContact.email}&gt;
                </p>
                <p>
                  <span className="text-faint">Subject:</span> {subject.trim() || '—'}
                </p>
              </div>
              <pre className="whitespace-pre-wrap px-4 py-3 font-sans text-[13px] leading-relaxed text-body">
                {body}
              </pre>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[92px_1fr] items-start gap-3">
      <dt className="text-[12px] text-faint">{label}</dt>
      <dd className="text-[13px] text-body">{children}</dd>
    </div>
  );
}
