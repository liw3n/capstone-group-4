import { LogOut } from 'lucide-react';
import { Session } from '../types';
import { initials } from '../lib/format';

interface TopBarProps {
  session: Session;
  onSignOut: () => void;
}

const ROLE_LABELS: Record<Session['role'], string> = {
  advisor: 'Financial Advisor',
  marketing: 'Marketing',
};

export default function TopBar({ session, onSignOut }: TopBarProps) {
  return (
    <header className="h-14 shrink-0 border-b border-line bg-white flex items-center justify-between px-5">
      <div className="flex items-center gap-2">
        <div className="w-6 h-6 rounded bg-link flex items-center justify-center">
          <span className="text-white font-bold text-[15px] leading-none">P</span>
        </div>
        <span className="text-[18px] font-semibold text-ink tracking-tight">MyWealth</span>
      </div>

      <div className="flex items-center gap-3">
        <div className="hidden sm:flex flex-col items-end leading-tight">
          <span className="text-[12px] font-medium text-ink">{session.name}</span>
          <span className="text-[11px] text-faint">{ROLE_LABELS[session.role]}</span>
        </div>
        <div className="w-7 h-7 rounded-full bg-gray-200 flex items-center justify-center text-[11px] font-medium text-body">
          {initials(session.name)}
        </div>
        <button
          onClick={onSignOut}
          className="text-faint hover:text-body transition-colors"
          title="Sign out"
          aria-label="Sign out"
        >
          <LogOut size={16} />
        </button>
      </div>
    </header>
  );
}
