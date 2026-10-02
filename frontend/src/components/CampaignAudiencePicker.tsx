import { useMemo, useState } from 'react';
import { Plus, RotateCcw, Search, X } from 'lucide-react';
import { Contact } from '../types';
import { describeContactTargeting } from '../lib/targeting';
import { display } from '../lib/format';

interface CampaignAudiencePickerProps {
  /** Everyone selectable — active contacts only, never leads. */
  contacts: Contact[];
  /** The resolved audience: criteria matches plus additions, minus removals. */
  audience: Contact[];
  includeIds: string[];
  excludeIds: string[];
  onChange: (next: { includeIds: string[]; excludeIds: string[] }) => void;
}

/**
 * The hand-picked half of a contact campaign. Criteria still drive the bulk of
 * the audience and stay live; this layers explicit overrides on top, so an
 * advisor can pull in someone the rules missed or drop someone they know is
 * wrong for it.
 */
export default function CampaignAudiencePicker({
  contacts,
  audience,
  includeIds,
  excludeIds,
  onChange,
}: CampaignAudiencePickerProps) {
  const [query, setQuery] = useState('');

  const included = useMemo(() => new Set(includeIds), [includeIds]);
  const inAudience = useMemo(() => new Set(audience.map((c) => c.id)), [audience]);

  const removed = useMemo(
    () => excludeIds.map((id) => contacts.find((c) => c.id === id)).filter(Boolean) as Contact[],
    [excludeIds, contacts],
  );

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return contacts
      .filter(
        (c) =>
          !inAudience.has(c.id) &&
          (c.name.toLowerCase().includes(q) || c.email.toLowerCase().includes(q)),
      )
      .slice(0, 6);
  }, [query, contacts, inAudience]);

  const add = (id: string) =>
    onChange({
      includeIds: includeIds.includes(id) ? includeIds : [...includeIds, id],
      excludeIds: excludeIds.filter((x) => x !== id),
    });

  /** Dropping a hand-picked addition just un-adds it; dropping a criteria match excludes it. */
  const drop = (id: string) =>
    included.has(id)
      ? onChange({ includeIds: includeIds.filter((x) => x !== id), excludeIds })
      : onChange({ includeIds, excludeIds: [...excludeIds, id] });

  const restore = (id: string) =>
    onChange({ includeIds, excludeIds: excludeIds.filter((x) => x !== id) });

  return (
    <div className="flex flex-col gap-4">
      <div className="relative">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Add a specific client by name or email"
          className="w-full rounded-md border border-line py-2 pl-9 pr-3 text-[13px] outline-none transition-colors focus:border-accent"
        />
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-faint" />

        {query.trim() && (
          <div className="absolute left-0 right-0 top-full z-20 mt-1 overflow-hidden rounded-md border border-line bg-white shadow-lg">
            {results.length === 0 ? (
              <p className="px-3 py-3 text-[12px] text-muted">
                No matching client outside the audience.
              </p>
            ) : (
              results.map((contact) => (
                <button
                  key={contact.id}
                  type="button"
                  onClick={() => {
                    add(contact.id);
                    setQuery('');
                  }}
                  className="flex w-full items-center gap-2 border-b border-line-soft px-3 py-2 text-left last:border-0 hover:bg-gray-50"
                >
                  <Plus size={13} className="shrink-0 text-accent" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] text-body">{contact.name}</span>
                    <span className="block truncate text-[11px] text-faint">
                      {display(contact.email)}
                    </span>
                  </span>
                </button>
              ))
            )}
          </div>
        )}
      </div>

      <div className="max-h-64 overflow-y-auto rounded-md border border-line">
        {audience.length === 0 ? (
          <p className="px-3 py-8 text-center text-[13px] text-muted">
            Nobody in the audience yet. Set criteria above, or add clients by name.
          </p>
        ) : (
          audience.map((contact) => (
            <div
              key={contact.id}
              className="flex items-center gap-3 border-b border-line-soft px-3 py-2 last:border-0"
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[13px] text-body">{contact.name}</span>
                <span className="block truncate text-[11px] text-faint">
                  {describeContactTargeting(contact) || display(contact.email)}
                </span>
              </span>

              {included.has(contact.id) && (
                <span className="shrink-0 rounded bg-purple-soft px-2 py-0.5 text-[11px] font-medium text-purple">
                  Added by you
                </span>
              )}

              <button
                type="button"
                onClick={() => drop(contact.id)}
                aria-label={`Remove ${contact.name} from the audience`}
                className="shrink-0 text-faint transition-colors hover:text-danger"
              >
                <X size={14} />
              </button>
            </div>
          ))
        )}
      </div>

      {removed.length > 0 && (
        <div className="flex flex-col gap-2">
          <span className="field-label">Removed by you ({removed.length})</span>
          <div className="flex flex-wrap gap-1.5">
            {removed.map((contact) => (
              <button
                key={contact.id}
                type="button"
                onClick={() => restore(contact.id)}
                className="inline-flex items-center gap-1 rounded-full border border-line bg-white px-2.5 py-1 text-[11px] text-body transition-colors hover:bg-gray-50"
              >
                <RotateCcw size={10} className="text-faint" />
                {contact.name}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
