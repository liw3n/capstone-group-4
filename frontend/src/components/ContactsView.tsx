import { useMemo, useState } from 'react';
import { ChevronDown, ChevronsUpDown, Plus, Search, Upload } from 'lucide-react';
import { Contact, ContactLabel, PipelineItem } from '../types';
import { LabelChip, SourceChip, stageLabel } from '../ui/Chip';
import Button from '../ui/Button';
import SummaryCard from './SummaryCard';
import { display } from '../lib/format';

interface ContactsViewProps {
  contacts: Contact[];
  pipelineItems: PipelineItem[];
  onSelectContact: (contact: Contact) => void;
  onAddToPipeline: (contact: Contact) => void;
  onAddContact: () => void;
  onUploadContacts: () => void;
}

type SortKey = 'name' | 'email' | 'label';

const LABEL_OPTIONS: (ContactLabel | 'All Labels')[] = ['All Labels', 'Prospect', 'Client'];

export default function ContactsView({
  contacts,
  pipelineItems,
  onSelectContact,
  onAddToPipeline,
  onAddContact,
  onUploadContacts,
}: ContactsViewProps) {
  const [query, setQuery] = useState('');
  const [labelFilter, setLabelFilter] = useState<ContactLabel | ''>('');
  const [showLabelMenu, setShowLabelMenu] = useState(false);
  const [sort, setSort] = useState<{ key: SortKey; dir: 'asc' | 'desc' } | null>(null);
  const [selected, setSelected] = useState<string[]>([]);

  const stats = useMemo(
    () => ({
      bookmarked: contacts.filter((c) => c.bookmarked).length,
      attention: contacts.filter((c) => c.needsAttention).length,
      prospects: contacts.filter((c) => c.label === 'Prospect').length,
    }),
    [contacts],
  );

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    const rows = contacts.filter((c) => {
      const matchesQuery =
        !q || c.name.toLowerCase().includes(q) || c.email.toLowerCase().includes(q);
      const matchesLabel = !labelFilter || c.label === labelFilter;
      return matchesQuery && matchesLabel;
    });

    if (!sort) return rows;

    return [...rows].sort((a, b) => {
      const av = (sort.key === 'label' ? a.label ?? '' : a[sort.key]).toLowerCase();
      const bv = (sort.key === 'label' ? b.label ?? '' : b[sort.key]).toLowerCase();
      return sort.dir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
    });
  }, [contacts, query, labelFilter, sort]);

  const toggleSort = (key: SortKey) => {
    setSort((prev) =>
      prev?.key === key
        ? { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' }
        : { key, dir: 'asc' },
    );
  };

  const allVisibleSelected = visible.length > 0 && visible.every((c) => selected.includes(c.id));

  const toggleAll = () => {
    setSelected(allVisibleSelected ? [] : visible.map((c) => c.id));
  };

  const toggleOne = (id: string) => {
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const pipelineFor = (contactId: string) =>
    pipelineItems.find((p) => p.contactId === contactId && !p.archived);

  return (
    <div className="flex flex-col gap-5">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <SummaryCard
          title="Bookmark Contacts"
          value={stats.bookmarked}
          caption={`out of total of ${contacts.length} contacts`}
          icon="bookmark"
        />
        <SummaryCard
          title="Need Attention"
          value={stats.attention}
          change={{ value: '10%', direction: 'down' }}
          icon="eye"
        />
        <SummaryCard
          title="New Prospects"
          value={stats.prospects}
          change={{ value: '10%', direction: 'up' }}
          icon="flag"
        />
      </div>

      <div className="relative">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search"
          className="w-full rounded-full border border-line bg-white pl-5 pr-11 py-2.5 text-[13px] outline-none focus:border-accent transition-colors"
        />
        <Search size={17} className="absolute right-4 top-1/2 -translate-y-1/2 text-ink" />
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="relative">
          <button
            onClick={() => setShowLabelMenu((v) => !v)}
            className="flex items-center gap-2 rounded-full border border-line bg-white px-4 py-1.5 text-[13px] font-medium text-body hover:bg-gray-50 transition-colors"
          >
            {labelFilter || 'All Labels'}
            <ChevronDown size={14} className="text-muted" />
          </button>
          {showLabelMenu && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setShowLabelMenu(false)} />
              <div className="absolute left-0 mt-1.5 z-20 w-44 rounded-lg border border-line bg-white py-1 shadow-lg">
                {LABEL_OPTIONS.map((opt) => (
                  <button
                    key={opt}
                    onClick={() => {
                      setLabelFilter(opt === 'All Labels' ? '' : opt);
                      setShowLabelMenu(false);
                    }}
                    className={`block w-full px-4 py-2 text-left text-[13px] hover:bg-gray-50 transition-colors ${
                      (opt === 'All Labels' && !labelFilter) || opt === labelFilter
                        ? 'text-accent font-medium'
                        : 'text-body'
                    }`}
                  >
                    {opt}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>

        <div className="flex items-center gap-2">
          <Button variant="primary" onClick={onAddContact}>
            <Plus size={15} />
            Add Contact
          </Button>
          <Button variant="secondary" onClick={onUploadContacts}>
            <Upload size={15} />
            Upload Contacts
          </Button>
        </div>
      </div>

      <div className="rounded-lg border border-line bg-white overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr className="border-b border-line">
                <th className="table-head w-10">
                  <input
                    type="checkbox"
                    checked={allVisibleSelected}
                    onChange={toggleAll}
                    className="accent-accent cursor-pointer"
                    aria-label="Select all contacts"
                  />
                </th>
                <SortHeader
                  label="Name"
                  sortKey="name"
                  activeKey={sort?.key}
                  onSort={toggleSort}
                />
                <SortHeader
                  label="Email"
                  sortKey="email"
                  activeKey={sort?.key}
                  onSort={toggleSort}
                />
                <th className="table-head">Contact Number</th>
                <SortHeader
                  label="Labels"
                  sortKey="label"
                  activeKey={sort?.key}
                  onSort={toggleSort}
                />
                <th className="table-head text-right">Pipeline Status</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((contact) => {
                const pipeline = pipelineFor(contact.id);

                return (
                  <tr key={contact.id} className="border-b border-line-soft last:border-0 hover:bg-gray-50/60 transition-colors">
                    <td className="cell">
                      <input
                        type="checkbox"
                        checked={selected.includes(contact.id)}
                        onChange={() => toggleOne(contact.id)}
                        className="accent-accent cursor-pointer"
                        aria-label={`Select ${contact.name}`}
                      />
                    </td>
                    <td className="cell">
                      <button
                        onClick={() => onSelectContact(contact)}
                        className="text-link hover:underline font-medium"
                      >
                        {contact.name}
                      </button>
                    </td>
                    <td className="cell text-body">{display(contact.email)}</td>
                    <td className="cell text-body">{display(contact.phone)}</td>
                    <td className="cell">
                      <span className="inline-flex flex-wrap items-center gap-1.5">
                        <LabelChip label={contact.label} />
                        <SourceChip contact={contact} />
                      </span>
                    </td>
                    <td className="cell text-right">
                      {pipeline ? (
                        <span className="text-[13px] text-muted">{stageLabel(pipeline)}</span>
                      ) : (
                        <button
                          onClick={() => onAddToPipeline(contact)}
                          className="text-[13px] text-link hover:underline"
                        >
                          Add to pipeline
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}

              {visible.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-16 text-center text-[13px] text-muted">
                    No contacts match your search.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <p className="text-[12px] text-faint">
        Showing {visible.length} of {contacts.length} contacts
        {selected.length > 0 && ` · ${selected.length} selected`}
      </p>
    </div>
  );
}

/**
 * Module level, not nested inside ContactsView. A component declared inside
 * another is a new type on every render, so React unmounts and remounts it.
 */
function SortHeader({
  label,
  sortKey,
  activeKey,
  onSort,
}: {
  label: string;
  sortKey: SortKey;
  activeKey?: SortKey;
  onSort: (key: SortKey) => void;
}) {
  return (
    <th className="table-head">
      <button
        onClick={() => onSort(sortKey)}
        className="inline-flex items-center gap-1 hover:text-ink transition-colors"
      >
        {label}
        <ChevronsUpDown size={12} className={activeKey === sortKey ? 'text-accent' : 'text-faint'} />
      </button>
    </th>
  );
}
