import { useState } from 'react';
import { motion } from 'motion/react';
import { Megaphone, UserRound } from 'lucide-react';
import { Role, Session } from '../types';
import Button from '../ui/Button';
import { DEMO_ADVISOR, channelName, teamById } from '../lib/directory';

interface LoginViewProps {
  onSignIn: (session: Session) => void;
}

/**
 * There is no authentication behind this screen, and it does not pretend
 * otherwise — no password field, and the footnote says so. Its real job is to
 * pick which role the prototype runs as, because Marketing and advisors see
 * different halves of the app.
 */
const ROLES: {
  role: Role;
  title: string;
  name: string;
  email: string;
  advisorId?: string;
  icon: typeof UserRound;
  blurb: string;
}[] = [
  {
    role: 'advisor',
    title: 'Financial Advisor',
    name: DEMO_ADVISOR.name,
    email: DEMO_ADVISOR.email,
    advisorId: DEMO_ADVISOR.id,
    icon: UserRound,
    blurb: 'Your book of business, tasks, pipeline, and campaigns sent to you.',
  },
  {
    role: 'marketing',
    title: 'Marketing',
    name: 'Marketing Team',
    email: 'campaigns@mywealth.com.sg',
    icon: Megaphone,
    blurb: 'Author campaigns and set the targeting criteria advisors receive.',
  },
];

export default function LoginView({ onSignIn }: LoginViewProps) {
  const [selected, setSelected] = useState<Role>('advisor');

  const active = ROLES.find((r) => r.role === selected)!;
  const team = active.advisorId ? teamById(DEMO_ADVISOR.teamId) : undefined;

  return (
    <div className="min-h-screen flex items-center justify-center bg-canvas px-4">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2 }}
        className="w-full max-w-md"
      >
        <div className="flex items-center justify-center gap-2 mb-8">
          <div className="w-8 h-8 rounded bg-link flex items-center justify-center">
            <span className="text-white font-bold text-[19px] leading-none">P</span>
          </div>
          <span className="text-[22px] font-semibold text-ink tracking-tight">MyWealth</span>
        </div>

        <div className="rounded-xl border border-line bg-white shadow-sm p-6">
          <h1 className="text-[16px] font-semibold text-ink">Sign in</h1>
          <p className="mt-1 text-[13px] text-muted">Choose the role you want to work as.</p>

          <div className="mt-5 flex flex-col gap-2.5">
            {ROLES.map((option) => {
              const Icon = option.icon;
              const isActive = option.role === selected;

              return (
                <button
                  key={option.role}
                  onClick={() => setSelected(option.role)}
                  aria-pressed={isActive}
                  className={`flex items-start gap-3 rounded-lg border p-3.5 text-left transition-colors ${
                    isActive
                      ? 'border-accent bg-accent-soft/60'
                      : 'border-line hover:bg-gray-50'
                  }`}
                >
                  <span
                    className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
                      isActive ? 'bg-accent text-white' : 'bg-line-soft text-muted'
                    }`}
                  >
                    <Icon size={15} />
                  </span>
                  <span className="flex flex-col gap-0.5">
                    <span
                      className={`text-[13px] font-semibold ${
                        isActive ? 'text-accent-hover' : 'text-ink'
                      }`}
                    >
                      {option.title}
                    </span>
                    <span className="text-[12px] text-muted leading-snug">{option.blurb}</span>
                  </span>
                </button>
              );
            })}
          </div>

          <div className="mt-5 flex flex-col gap-1.5">
            <span className="field-label">Signing in as</span>
            <div className="rounded-md border border-line bg-gray-50 px-3 py-2">
              <p className="text-[13px] text-body">{active.name}</p>
              <p className="text-[12px] text-faint">{active.email}</p>
              {active.advisorId && team && (
                <p className="mt-1 text-[11px] text-faint">
                  {team.name} · {channelName(team.channel)}
                </p>
              )}
            </div>
          </div>

          <Button
            variant="primary"
            className="mt-5 w-full"
            onClick={() =>
              onSignIn({
                name: active.name,
                email: active.email,
                role: active.role,
                advisorId: active.advisorId,
              })
            }
          >
            Sign in as {active.title}
          </Button>
        </div>

        <p className="mt-4 text-center text-[11px] text-faint">
          Prototype sign-in. No password or account — this only selects a role.
        </p>
      </motion.div>
    </div>
  );
}
