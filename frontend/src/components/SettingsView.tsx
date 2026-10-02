import { Bell, Building2, Shield, User } from 'lucide-react';

const SECTIONS = [
  {
    icon: User,
    title: 'Profile',
    description: 'Advisor name, contact details, and signature used on client correspondence.',
  },
  {
    icon: Building2,
    title: 'Organisation',
    description: 'Firm details, licence numbers, and branding applied to generated documents.',
  },
  {
    icon: Bell,
    title: 'Notifications',
    description: 'Reminders for overdue tasks, upcoming reviews, and compliance deadlines.',
  },
  {
    icon: Shield,
    title: 'Compliance',
    description: 'Suitability form requirements, retention policy, and audit trail settings.',
  },
];

export default function SettingsView() {
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-1">
        <h1 className="text-[24px] font-semibold text-ink">Settings</h1>
        <p className="text-[13px] text-muted">
          Configuration is not wired up in this prototype.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {SECTIONS.map(({ icon: Icon, title, description }) => (
          <div
            key={title}
            className="rounded-lg border border-line bg-white p-5 flex items-start gap-4"
          >
            <span className="p-2 rounded bg-accent-soft text-accent shrink-0">
              <Icon size={16} />
            </span>
            <div className="flex flex-col gap-1">
              <h2 className="text-[14px] font-semibold text-ink">{title}</h2>
              <p className="text-[12.5px] text-muted leading-relaxed">{description}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
