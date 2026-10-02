import { Bookmark, Eye, Flag, TriangleAlert } from 'lucide-react';

const ICONS = { bookmark: Bookmark, eye: Eye, flag: Flag, alert: TriangleAlert };

export interface SummaryCardProps {
  title: string;
  value: number | string;
  caption?: string;
  change?: { value: string; direction: 'up' | 'down' };
  icon: keyof typeof ICONS;
}

export default function SummaryCard({ title, value, caption, change, icon }: SummaryCardProps) {
  const Icon = ICONS[icon];

  return (
    <div className="bg-white rounded-lg border border-line px-5 py-4 flex flex-col gap-2">
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-[13px] text-muted">{title}</h3>
        <div className="p-1.5 rounded bg-accent-soft text-accent shrink-0">
          <Icon size={14} />
        </div>
      </div>

      <span className="text-[26px] font-semibold text-ink leading-none">{value}</span>

      {caption && <span className="text-[11px] text-faint">{caption}</span>}

      {change && (
        <span className="text-[11px] flex items-center gap-1.5">
          <span className={change.direction === 'up' ? 'text-success' : 'text-danger'}>
            {change.direction === 'up' ? '▲' : '▼'} {change.value}
          </span>
          <span className="text-faint">vs. prior 30 days</span>
        </span>
      )}
    </div>
  );
}
