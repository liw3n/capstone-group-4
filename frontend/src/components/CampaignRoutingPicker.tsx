import { useMemo, useState } from 'react';
import { ChevronDown, Users } from 'lucide-react';
import {
  ADVISORS,
  CHANNELS,
  channelName,
  resolveRecipients,
  resolveTeams,
  teamsForChannel,
} from '../lib/directory';

export interface Routing {
  channel: string;
  teamIds: string[];
  advisorIds: string[];
}

interface CampaignRoutingPickerProps {
  routing: Routing;
  onChange: (routing: Routing) => void;
}

const chipClass = (isOn: boolean) =>
  `rounded-full border px-2.5 py-1 text-[12px] transition-colors ${
    isOn ? 'border-accent bg-accent text-white' : 'border-line bg-white text-body hover:bg-gray-50'
  }`;

/**
 * Channel is the decision; everything below it is an exception.
 *
 * Picking a channel includes every team and advisor in it, which is what most
 * campaigns want, so the team and advisor controls stay collapsed until someone
 * actually needs to narrow. They open automatically when a campaign is already
 * narrowed, so a saved exception is never hidden from the person editing it.
 */
export default function CampaignRoutingPicker({ routing, onChange }: CampaignRoutingPickerProps) {
  const isNarrowed = routing.teamIds.length > 0 || routing.advisorIds.length > 0;
  const [open, setOpen] = useState(isNarrowed);

  const teams = useMemo(() => teamsForChannel(routing.channel), [routing.channel]);
  const activeTeams = useMemo(() => resolveTeams(routing), [routing]);
  const recipients = useMemo(() => resolveRecipients(routing), [routing]);

  /** Everyone the channel could reach, for the "N of M" line when narrowed. */
  const channelSize = useMemo(
    () => ADVISORS.filter((a) => teams.some((t) => t.id === a.teamId)).length,
    [teams],
  );

  const setChannel = (channel: string) =>
    // A team from the old channel would silently keep filtering, so reset both.
    onChange({ channel, teamIds: [], advisorIds: [] });

  const toggleTeam = (teamId: string) => {
    const nextTeams = routing.teamIds.includes(teamId)
      ? routing.teamIds.filter((id) => id !== teamId)
      : [...routing.teamIds, teamId];

    // Drop any named advisor who is no longer inside the selected teams.
    const scope = resolveTeams({ ...routing, teamIds: nextTeams }).map((t) => t.id);
    const nextAdvisors = routing.advisorIds.filter((id) => {
      const advisor = ADVISORS.find((a) => a.id === id);
      return advisor ? scope.includes(advisor.teamId) : false;
    });

    onChange({ ...routing, teamIds: nextTeams, advisorIds: nextAdvisors });
  };

  const toggleAdvisor = (advisorId: string) =>
    onChange({
      ...routing,
      advisorIds: routing.advisorIds.includes(advisorId)
        ? routing.advisorIds.filter((id) => id !== advisorId)
        : [...routing.advisorIds, advisorId],
    });

  const reset = () => onChange({ ...routing, teamIds: [], advisorIds: [] });

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-1.5">
        <label className="field-label" htmlFor="campaign-channel">
          Channel
        </label>
        <select
          id="campaign-channel"
          value={routing.channel}
          onChange={(e) => setChannel(e.target.value)}
          className="input-field"
        >
          {CHANNELS.map((option) => (
            <option key={option.code} value={option.code}>
              {option.code} — {option.name}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-accent-soft px-3 py-2">
        <span className="flex items-center gap-2 text-[12px] text-accent-hover">
          <Users size={13} className="shrink-0" />
          {isNarrowed ? (
            <span>
              <span className="font-semibold">{recipients.length}</span> of {channelSize} advisors
              in {channelName(routing.channel)}
            </span>
          ) : (
            <span>
              Everyone in {channelName(routing.channel)} —{' '}
              <span className="font-semibold">{recipients.length}</span> advisors across{' '}
              {activeTeams.length} teams
            </span>
          )}
        </span>

        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="flex items-center gap-1 text-[12px] font-medium text-accent-hover hover:underline"
        >
          {open ? 'Done' : 'Narrow'}
          <ChevronDown
            size={12}
            className={open ? 'rotate-180 transition-transform' : 'transition-transform'}
          />
        </button>
      </div>

      {open && (
        <div className="flex flex-col gap-3 rounded-md border border-line p-3">
          <div className="flex flex-col gap-1.5">
            <span className="field-label">FA Team</span>
            <div className="flex flex-wrap gap-1.5">
              <button type="button" onClick={reset} className={chipClass(!isNarrowed)}>
                All teams
              </button>
              {teams.map((team) => (
                <button
                  key={team.id}
                  type="button"
                  onClick={() => toggleTeam(team.id)}
                  aria-pressed={routing.teamIds.includes(team.id)}
                  className={chipClass(routing.teamIds.includes(team.id))}
                >
                  {team.name}
                </button>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-1.5 border-t border-line-soft pt-3">
            <div className="flex items-baseline justify-between gap-2">
              <span className="field-label">Individual FAs</span>
              <span className="text-[11px] text-faint">
                {routing.advisorIds.length === 0
                  ? 'all of the above'
                  : `${routing.advisorIds.length} named`}
              </span>
            </div>

            <div className="flex max-h-40 flex-col gap-2 overflow-y-auto">
              {activeTeams.map((team) => (
                <div key={team.id} className="flex flex-col gap-1">
                  <span className="text-[11px] text-faint">{team.name}</span>
                  <div className="flex flex-wrap gap-1.5">
                    {ADVISORS.filter((a) => a.teamId === team.id).map((advisor) => (
                      <button
                        key={advisor.id}
                        type="button"
                        onClick={() => toggleAdvisor(advisor.id)}
                        aria-pressed={routing.advisorIds.includes(advisor.id)}
                        className={chipClass(routing.advisorIds.includes(advisor.id))}
                      >
                        {advisor.name}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
