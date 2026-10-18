import { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Eye,
  RefreshCw,
  Save,
  Users,
} from 'lucide-react';
import Button from '../ui/Button';
import { CriteriaPicker } from './CampaignCriteria';
import { CampaignCriteria } from '../types';
import {
  CampaignDraftArtifact,
  CampaignDraftField,
} from '../services/chatApi';
import {
  CampaignDraftApiError,
  CampaignDraftChanges,
  getCampaignDraft,
  regenerateCampaignDraft,
  updateCampaignDraft,
} from '../services/campaignDraftApi';

interface CampaignDraftReviewProps {
  advisorId: string;
  sessionId: string;
  initialDraft: CampaignDraftArtifact;
  onCancel: () => void;
  onDraftUpdated: (draft: CampaignDraftArtifact) => void;
}

interface ReviewForm {
  name: string;
  description: string;
  clientMessage: string;
  criteria: CampaignCriteria;
  targetDemographicSummary: string;
}

const FIELD_LABELS: Record<CampaignDraftField, string> = {
  name: 'Campaign name',
  description: 'Campaign description',
  clientMessage: 'Client messaging',
  ageGroups: 'Target age groups',
  genders: 'Target demographic',
  cashBands: 'Target cash availability',
  targetDemographicSummary: 'Target demographic summary',
};

const FIELD_ORDER = Object.keys(FIELD_LABELS) as CampaignDraftField[];

function formFromDraft(artifact: CampaignDraftArtifact): ReviewForm {
  return {
    name: artifact.draft.name,
    description: artifact.draft.description,
    clientMessage: artifact.draft.clientMessage,
    criteria: {
      ageGroups: [...artifact.draft.criteria.ageGroups],
      genders: [...artifact.draft.criteria.genders],
      cashBands: [...artifact.draft.criteria.cashBands],
    },
    targetDemographicSummary: artifact.draft.targetDemographicSummary,
  };
}

function sameValues(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

export function campaignDraftChanges(
  artifact: CampaignDraftArtifact,
  form: ReviewForm,
): CampaignDraftChanges {
  const changes: CampaignDraftChanges = {};
  if (form.name.trim() !== artifact.draft.name) changes.name = form.name.trim();
  if (form.description.trim() !== artifact.draft.description) {
    changes.description = form.description.trim();
  }
  if (form.clientMessage.trim() !== artifact.draft.clientMessage) {
    changes.clientMessage = form.clientMessage.trim();
  }
  if (!sameValues(form.criteria.ageGroups, artifact.draft.criteria.ageGroups)) {
    changes.ageGroups = form.criteria.ageGroups;
  }
  if (!sameValues(form.criteria.genders, artifact.draft.criteria.genders)) {
    changes.genders = form.criteria.genders;
  }
  if (!sameValues(form.criteria.cashBands, artifact.draft.criteria.cashBands)) {
    changes.cashBands = form.criteria.cashBands;
  }
  if (
    form.targetDemographicSummary.trim()
    !== artifact.draft.targetDemographicSummary
  ) {
    changes.targetDemographicSummary = form.targetDemographicSummary.trim();
  }
  return changes;
}

function ReviewMetadata({ artifact }: { artifact: CampaignDraftArtifact }) {
  return (
    <section className="rounded-lg border border-line bg-white p-5">
      <h2 className="text-[14px] font-semibold text-ink">Review information</h2>

      {artifact.validation.warnings.length > 0 && (
        <div className="mt-4 rounded-md bg-amber-soft px-3 py-3 text-[12px] text-amber">
          <div className="flex items-center gap-2 font-semibold">
            <AlertTriangle size={14} /> Adviser checks required
          </div>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            {artifact.validation.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-4 grid gap-4 md:grid-cols-3">
        {(['ageGroups', 'genders', 'cashBands'] as const).map((dimension) => (
          <div key={dimension}>
            <p className="text-[11px] font-semibold uppercase tracking-wide text-faint">
              {FIELD_LABELS[dimension]}
            </p>
            <p className="mt-1 text-[12px] leading-relaxed text-body">
              {artifact.draft.rationale[dimension]}
            </p>
          </div>
        ))}
      </div>

      <div className="mt-4 border-t border-line-soft pt-4">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-faint">Assumptions</p>
        {artifact.draft.assumptions.length > 0 ? (
          <ul className="mt-2 list-disc space-y-1 pl-5 text-[12px] text-body">
            {artifact.draft.assumptions.map((assumption) => (
              <li key={assumption}>{assumption}</li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-[12px] text-muted">No material assumptions recorded.</p>
        )}
      </div>

      <div className="mt-4 border-t border-line-soft pt-4">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-faint">Disclaimer</p>
        <p className="mt-1 whitespace-pre-wrap text-[12px] leading-relaxed text-body">
          {artifact.draft.disclaimer}
        </p>
      </div>

      <div className="mt-4 border-t border-line-soft pt-4">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-faint">
          Synthetic catalogue references
        </p>
        {artifact.referencesUsed.length > 0 ? (
          <ul className="mt-2 space-y-1 text-[12px] text-body">
            {artifact.referencesUsed.map((reference) => (
              <li key={`${reference.referenceId}:${reference.version}`}>
                {reference.referenceId} · version {reference.version}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-[12px] text-muted">No catalogue reference was used.</p>
        )}
      </div>
    </section>
  );
}

function DraftPreview({
  artifact,
  onBack,
  onCancel,
}: {
  artifact: CampaignDraftArtifact;
  onBack: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="flex flex-col gap-5">
      <button onClick={onCancel} className="flex w-fit items-center gap-1.5 text-[13px] text-link hover:underline">
        <ArrowLeft size={15} /> Campaigns
      </button>
      <div>
        <h1 className="text-xl font-semibold text-ink">Preview generated campaign</h1>
        <p className="mt-1 text-[12px] text-muted">
          Review-only preview of revision {artifact.revision}. No campaign has been created.
        </p>
      </div>
      <section className="rounded-lg border border-line bg-white p-5">
        <h2 className="text-[18px] font-semibold text-ink">{artifact.draft.name}</h2>
        <p className="mt-3 whitespace-pre-wrap text-[13px] leading-relaxed text-body">
          {artifact.draft.description}
        </p>
        <div className="mt-5 border-t border-line-soft pt-4">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-faint">Client message</p>
          <p className="mt-2 whitespace-pre-wrap text-[13px] leading-relaxed text-body">
            {artifact.draft.clientMessage}
          </p>
        </div>
        <div className="mt-5 border-t border-line-soft pt-4">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-faint">Intended audience</p>
          <p className="mt-2 text-[13px] leading-relaxed text-body">
            {artifact.draft.targetDemographicSummary}
          </p>
        </div>
      </section>
      <ReviewMetadata artifact={artifact} />
      <div className="flex flex-wrap gap-2">
        <Button variant="primary" onClick={onBack}>Back to editing</Button>
        <Button variant="secondary" onClick={onCancel}>Return to campaigns</Button>
      </div>
      <p className="text-[11px] text-muted">
        Confirmation and campaign creation are intentionally unavailable in this review stage.
      </p>
    </div>
  );
}

export default function CampaignDraftReview({
  advisorId,
  sessionId,
  initialDraft,
  onCancel,
  onDraftUpdated,
}: CampaignDraftReviewProps) {
  const [artifact, setArtifact] = useState(initialDraft);
  const [form, setForm] = useState<ReviewForm>(() => formFromDraft(initialDraft));
  const [selectedFields, setSelectedFields] = useState<CampaignDraftField[]>([]);
  const [instruction, setInstruction] = useState('Make the selected sections clearer and more engaging while preserving the campaign objective.');
  const [saving, setSaving] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [error, setError] = useState('');
  const request = useRef<AbortController | null>(null);

  useEffect(() => () => request.current?.abort(), []);

  useEffect(() => {
    if (
      initialDraft.draftId !== artifact.draftId
      || initialDraft.revision > artifact.revision
    ) {
      setArtifact(initialDraft);
      setForm(formFromDraft(initialDraft));
      setSelectedFields([]);
      setError('');
    }
  }, [artifact.draftId, artifact.revision, initialDraft]);

  const changes = useMemo(() => campaignDraftChanges(artifact, form), [artifact, form]);
  const changedFields = Object.keys(changes) as CampaignDraftField[];
  const dirty = changedFields.length > 0;
  const invalid = !form.name.trim() || !form.description.trim()
    || !form.clientMessage.trim() || !form.targetDemographicSummary.trim();

  const applyArtifact = (next: CampaignDraftArtifact) => {
    setArtifact(next);
    setForm(formFromDraft(next));
    setSelectedFields([]);
    setError('');
    onDraftUpdated(next);
  };

  const showError = async (reason: unknown, controller: AbortController) => {
    if (reason instanceof DOMException && reason.name === 'AbortError') return;
    if (reason instanceof CampaignDraftApiError && reason.status === 409) {
      try {
        const latest = await getCampaignDraft(
          advisorId,
          sessionId,
          artifact.draftId,
          controller.signal,
        );
        if (!controller.signal.aborted) {
          applyArtifact(latest);
          setError(`A newer revision (${latest.revision}) was loaded. Review it before continuing.`);
        }
      } catch (refreshReason) {
        if (refreshReason instanceof DOMException && refreshReason.name === 'AbortError') return;
        setError('This draft has a newer revision, but it could not be reloaded. Reopen it from PULSE.');
      }
      return;
    }
    setError(reason instanceof Error ? reason.message : 'Unable to update the campaign draft.');
  };

  const saveDraft = async () => {
    if (!dirty || invalid || saving || regenerating) return;
    const controller = new AbortController();
    request.current?.abort();
    request.current = controller;
    setSaving(true);
    setError('');
    try {
      const updated = await updateCampaignDraft(
        advisorId, sessionId, artifact, changes, controller.signal,
      );
      if (!controller.signal.aborted) applyArtifact(updated);
    } catch (reason) {
      await showError(reason, controller);
    } finally {
      if (request.current === controller) {
        request.current = null;
        setSaving(false);
      }
    }
  };

  const regenerate = async () => {
    if (dirty || selectedFields.length === 0 || !instruction.trim() || saving || regenerating) return;
    const controller = new AbortController();
    request.current?.abort();
    request.current = controller;
    setRegenerating(true);
    setError('');
    try {
      const updated = await regenerateCampaignDraft(
        advisorId,
        sessionId,
        artifact,
        selectedFields,
        instruction.trim(),
        controller.signal,
      );
      if (!controller.signal.aborted) applyArtifact(updated);
    } catch (reason) {
      await showError(reason, controller);
    } finally {
      if (request.current === controller) {
        request.current = null;
        setRegenerating(false);
      }
    }
  };

  if (previewing) {
    return <DraftPreview artifact={artifact} onBack={() => setPreviewing(false)} onCancel={onCancel} />;
  }

  return (
    <div className="flex flex-col gap-5">
      <button onClick={onCancel} className="flex w-fit items-center gap-1.5 text-[13px] text-link hover:underline">
        <ArrowLeft size={15} /> Campaigns
      </button>

      <div>
        <h1 className="text-xl font-semibold text-ink">Review generated campaign</h1>
        <p className="mt-1 text-[12px] text-muted">
          AI-generated revision {artifact.revision}. Edit and validate the draft before a later confirmation step.
        </p>
      </div>

      {error && (
        <div role="alert" className="rounded-md border border-danger/20 bg-danger-soft px-4 py-3 text-[12px] text-danger">
          {error}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_300px] lg:items-start">
        <div className="flex min-w-0 flex-col gap-4">
          <section className="rounded-lg border border-line bg-white p-5">
            <h2 className="text-[14px] font-semibold text-ink">Who is this for?</h2>
            <p className="mt-1 text-[11px] text-muted">Generated criteria are reviewed against your contacts only after creation.</p>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <div className="rounded-lg border border-accent bg-accent-soft px-4 py-3">
                <div className="flex items-center gap-2 text-[12px] font-semibold text-accent-hover">
                  <Users size={14} /> My contacts
                </div>
                <p className="mt-1 text-[10px] text-muted">Target using the generated criteria after adviser confirmation.</p>
              </div>
              <div className="rounded-lg border border-line bg-gray-50 px-4 py-3 opacity-60">
                <p className="text-[12px] font-semibold text-body">Uploaded list</p>
                <p className="mt-1 text-[10px] text-muted">Not available for a generated criteria draft.</p>
              </div>
            </div>
          </section>

          <section className="rounded-lg border border-line bg-white p-5 flex flex-col gap-4">
            <h2 className="text-[14px] font-semibold text-ink">Campaign details</h2>
            <label className="flex flex-col gap-1.5">
              <span className="field-label">Campaign name *</span>
              <input value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} className="input-field" />
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="field-label">Campaign description *</span>
              <textarea value={form.description} onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))} rows={4} className="input-field resize-y" />
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="field-label">Client messaging *</span>
              <textarea value={form.clientMessage} onChange={(event) => setForm((current) => ({ ...current, clientMessage: event.target.value }))} rows={5} className="input-field resize-y" />
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="field-label">Target demographic summary *</span>
              <textarea value={form.targetDemographicSummary} onChange={(event) => setForm((current) => ({ ...current, targetDemographicSummary: event.target.value }))} rows={3} className="input-field resize-y" />
            </label>
          </section>

          <section className="rounded-lg border border-line bg-white p-5 flex flex-col gap-4">
            <div>
              <h2 className="text-[14px] font-semibold text-ink">Targeting criteria</h2>
              <p className="mt-1 text-[12px] text-muted">These values remain review-only and do not select clients at this stage.</p>
            </div>
            <CriteriaPicker
              criteria={form.criteria}
              onChange={(criteria) => setForm((current) => ({ ...current, criteria }))}
              allowCustomRanges={false}
            />
            <p className="text-[11px] text-muted">
              Generated drafts currently support the fixed age and cash bands only.
            </p>
          </section>

          <ReviewMetadata artifact={artifact} />
        </div>

        <aside className="flex flex-col gap-4 rounded-lg border border-line bg-white p-5 lg:sticky lg:top-2">
          <div className="flex items-center gap-2">
            <CheckCircle2 size={16} className="text-success" />
            <div>
              <h2 className="text-[14px] font-semibold text-ink">Review draft</h2>
              <p className="text-[11px] text-muted">Revision {artifact.revision} · {artifact.status}</p>
            </div>
          </div>

          <div className="border-t border-line-soft pt-4">
            <p className="text-[12px] font-semibold text-ink">Regenerate sections</p>
            <div className="mt-2 space-y-2">
              {FIELD_ORDER.map((field) => (
                <label key={field} className="flex items-center gap-2 text-[11px] text-body">
                  <input
                    type="checkbox"
                    checked={selectedFields.includes(field)}
                    onChange={(event) => setSelectedFields((current) =>
                      event.target.checked
                        ? [...current, field]
                        : current.filter((item) => item !== field),
                    )}
                  />
                  {FIELD_LABELS[field]}
                </label>
              ))}
            </div>
            <textarea
              value={instruction}
              onChange={(event) => setInstruction(event.target.value)}
              rows={3}
              className="input-field mt-3 resize-y text-[11px]"
              aria-label="Regeneration instruction"
            />
            <Button
              variant="secondary"
              onClick={() => void regenerate()}
              disabled={dirty || selectedFields.length === 0 || regenerating || saving}
            >
              <RefreshCw size={14} /> {regenerating ? 'Regenerating…' : 'Regenerate selected'}
            </Button>
            {dirty && <p className="mt-2 text-[10px] text-amber">Save or discard manual edits before regenerating.</p>}
          </div>

          <div className="border-t border-line-soft pt-4">
            <p className="text-[11px] text-muted">
              {dirty ? `${changedFields.length} unsaved section${changedFields.length === 1 ? '' : 's'}.` : 'All changes are saved.'}
            </p>
            {invalid && <p className="mt-1 text-[10px] text-danger">Complete every required field before saving.</p>}
          </div>

          <div className="flex flex-col gap-2 border-t border-line-soft pt-4">
            <Button variant="primary" onClick={() => void saveDraft()} disabled={!dirty || invalid || saving || regenerating}>
              <Save size={14} /> {saving ? 'Saving…' : 'Save draft'}
            </Button>
            <Button variant="secondary" onClick={() => setPreviewing(true)} disabled={dirty || saving || regenerating}>
              <Eye size={14} /> Preview draft
            </Button>
            <Button variant="secondary" onClick={onCancel}>Cancel</Button>
          </div>

          <p className="text-[10px] leading-relaxed text-faint">
            Saving updates only the review draft. It does not create, activate, or send a campaign.
          </p>
        </aside>
      </div>
    </div>
  );
}
