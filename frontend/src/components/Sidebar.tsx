import { Home, Users, Check, Briefcase, Settings, Megaphone } from 'lucide-react';
import { Role } from '../types';

export type TabId = 'home' | 'contacts' | 'tasks' | 'pipeline' | 'campaigns' | 'settings';

interface SidebarProps {
  activeTab: TabId;
  role: Role;
  onTabChange: (id: TabId) => void;
}

const NAV: { id: TabId; label: string; icon: typeof Home }[] = [
  { id: 'home', label: 'Home', icon: Home },
  { id: 'contacts', label: 'Contacts', icon: Users },
  { id: 'tasks', label: 'Tasks', icon: Check },
  { id: 'pipeline', label: 'CRM Pipeline', icon: Briefcase },
  { id: 'campaigns', label: 'Campaigns', icon: Megaphone },
  { id: 'settings', label: 'Settings', icon: Settings },
];

/**
 * Marketing authors campaigns and nothing else — it has no book of business, so
 * showing it Contacts or Pipeline would be showing it someone else's clients.
 */
const ROLE_TABS: Record<Role, TabId[]> = {
  advisor: ['home', 'contacts', 'tasks', 'pipeline', 'campaigns', 'settings'],
  marketing: ['campaigns', 'settings'],
};

export default function Sidebar({ activeTab, role, onTabChange }: SidebarProps) {
  const allowed = ROLE_TABS[role];
  const items = NAV.filter((item) => allowed.includes(item.id));

  return (
    <aside className="w-[108px] shrink-0 bg-white hidden md:flex flex-col pt-4">
      <nav className="flex flex-col">
        {items.map((item) => {
          const isActive = activeTab === item.id;
          const Icon = item.icon;

          return (
            <button
              key={item.id}
              onClick={() => onTabChange(item.id)}
              className={`relative flex items-start gap-2 px-3 py-3 text-left transition-colors ${
                isActive ? 'text-accent' : 'text-body hover:text-ink'
              }`}
            >
              <Icon size={15} className="mt-px shrink-0" />
              <span className={`text-[13px] leading-tight ${isActive ? 'font-semibold' : ''}`}>
                {item.label}
              </span>
              {isActive && (
                <span className="absolute bottom-0 left-3 right-2 h-[2px] bg-accent rounded-full" />
              )}
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
