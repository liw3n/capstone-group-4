import { useState } from 'react';
import { RotateCcw } from 'lucide-react';
import { Session } from '../types';
import Modal from '../ui/Modal';
import Button from '../ui/Button';
import { DEFAULT_SIGN_OFF, SIGN_OFF_TOKENS } from '../lib/email';

interface SignOffTemplateModalProps {
  signOff: string;
  session: Session;
  onClose: () => void;
  onSave: (signOff: string) => void;
}

/**
 * The advisor's email sign-off. It belongs to the advisor rather than to any one
 * campaign, so it is set once here and reused by every campaign send.
 */
export default function SignOffTemplateModal({
  signOff,
  session,
  onClose,
  onSave,
}: SignOffTemplateModalProps) {
  const [draft, setDraft] = useState(signOff);

  const preview = draft
    .replaceAll('{{advisor_name}}', session.name)
    .replaceAll('{{advisor_email}}', session.email)
    .replaceAll('{{client_name}}', 'Joseph Rahman');

  return (
    <Modal
      title="Email sign-off"
      onClose={onClose}
      width="max-w-xl"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            CANCEL
          </Button>
          <Button variant="primary" onClick={() => onSave(draft)} disabled={!draft.trim()}>
            SAVE
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <p className="text-[13px] text-muted">
          Appended to every campaign email you send. Saved for your account, not for one campaign.
        </p>

        <div className="flex flex-col gap-1.5">
          <label className="field-label" htmlFor="sign-off">
            Template
          </label>
          <textarea
            id="sign-off"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={6}
            className="w-full resize-y rounded-md border border-line px-3 py-2 font-mono text-[12px] leading-relaxed outline-none transition-colors focus:border-accent"
            autoFocus
          />
          {!draft.trim() && (
            <p className="text-[11px] text-danger">A sign-off is required.</p>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] text-faint">Insert:</span>
          {SIGN_OFF_TOKENS.map((token) => (
            <button
              key={token}
              type="button"
              onClick={() => setDraft((prev) => prev + token)}
              className="rounded border border-line bg-white px-2 py-1 font-mono text-[11px] text-body transition-colors hover:bg-gray-50"
            >
              {token}
            </button>
          ))}
        </div>

        <div className="flex flex-col gap-1.5">
          <span className="field-label">Preview</span>
          <pre className="whitespace-pre-wrap rounded-md bg-line-soft px-4 py-3 font-sans text-[13px] leading-relaxed text-body">
            {preview}
          </pre>
        </div>

        <button
          type="button"
          onClick={() => setDraft(DEFAULT_SIGN_OFF)}
          className="flex w-fit items-center gap-1.5 text-[12px] text-link hover:underline"
        >
          <RotateCcw size={12} />
          Reset to default
        </button>
      </div>
    </Modal>
  );
}
