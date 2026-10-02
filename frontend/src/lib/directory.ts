import { Advisor, AdvisorTeam, Campaign } from '../types';

/**
 * ============================================================================
 * DISTRIBUTION DIRECTORY
 * ============================================================================
 * Who receives a campaign, as opposed to which clients it targets. Three
 * levels, narrowing downward:
 *
 *   Channel  ->  FA Team (a branch, agency group, or partner firm)  ->  FA
 *
 * Narrowing is optional at each level and empty means "all of them". A campaign
 * with a channel and nothing else reaches every advisor in that channel; adding
 * teams narrows it to those teams; adding advisors narrows it again to named
 * people. That way Marketing can send broadly without ticking 40 boxes, and
 * precisely when it matters.
 *
 * This is separate from lib/targeting.ts on purpose: targeting decides which
 * *clients* are in a campaign's audience, this decides which *advisors* ever
 * see the campaign at all. The two never mix.
 */

export const CHANNELS: { code: string; name: string }[] = [
  { code: 'BANCA-SG', name: 'Bancassurance — Singapore' },
  { code: 'TIED-AGENCY', name: 'Tied Agency Force' },
  { code: 'PARTNERSHIP', name: 'Partnership — IFA Firms' },
  { code: 'DIRECT-DIGITAL', name: 'Direct / Digital' },
  { code: 'PRIORITY-HNW', name: 'Priority & High Net Worth' },
];

export function channelName(code: string): string {
  return CHANNELS.find((c) => c.code === code)?.name ?? code;
}

/* -------------------------------------------------------------------------- */
/* Teams and advisors                                                         */
/* -------------------------------------------------------------------------- */

/**
 * Team names follow how each channel is actually organised: bancassurance by
 * branch, tied agency by group, partnership by firm.
 */
const TEAM_SEED: { channel: string; names: string[] }[] = [
  { channel: 'BANCA-SG', names: ['Marina Bay Branch', 'Orchard Branch', 'Jurong Branch'] },
  { channel: 'TIED-AGENCY', names: ['Agency Group Alpha', 'Agency Group Bravo'] },
  {
    channel: 'PARTNERSHIP',
    names: [
      'Meridian Advisory',
      'Anchor Wealth Partners',
      'Straits Financial Group',
      'Keppel Advisory Partners',
    ],
  },
  { channel: 'DIRECT-DIGITAL', names: ['Digital Desk'] },
  { channel: 'PRIORITY-HNW', names: ['Priority Team North', 'Priority Team South'] },
];

/** Four per team, drawn in order so the roster is identical on every load. */
const ADVISOR_NAMES = [
  'Amirah Rashid', 'Colin Teo', 'Divya Menon', 'Ethan Lau',
  'Farhan Idris', 'Germaine Sim', 'Harpreet Singh', 'Isabel Fong',
  'Jayden Ho', 'Kalyani Raman', 'Lionel Chua', 'Mei Ling Poh',
  'Nabil Osman', 'Olivia Tan', 'Pravin Kumar', 'Qi Hui Loh',
  'Rashid Bakar', 'Sofia Marican', 'Terrence Yap', 'Uma Devi',
  'Victor Chiam', 'Wan Ting Ang', 'Xavier Lim', 'Yusra Halim',
  'Zachary Neo', 'Adeline Kwok', 'Bryan Seah', 'Chandra Pillai',
  'Delphine Ng', 'Emmanuel Boey', 'Fiona Cheah', 'Gopal Nathan',
  'Hafiz Roslan', 'Irene Mak', 'Joel Tng', 'Kavitha Suresh',
  'Lena Oh', 'Marcus Fu', 'Noorain Salleh', 'Owen Chia',
  'Patricia Lai', 'Qamar Aziz', 'Rebecca Soh', 'Samuel Ede',
];

function slug(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}

function emailFor(name: string): string {
  return `${slug(name).replace(/-/g, '.')}@mywealth.com.sg`;
}

function buildDirectory(): { teams: AdvisorTeam[]; advisors: Advisor[] } {
  const teams: AdvisorTeam[] = [];
  const advisors: Advisor[] = [];
  let cursor = 0;

  for (const group of TEAM_SEED) {
    for (const teamName of group.names) {
      const team: AdvisorTeam = {
        id: slug(teamName),
        name: teamName,
        channel: group.channel,
      };
      teams.push(team);

      for (let i = 0; i < 4; i++) {
        const name = ADVISOR_NAMES[cursor % ADVISOR_NAMES.length];
        cursor++;
        advisors.push({
          id: `adv-${slug(name)}`,
          name,
          email: emailFor(name),
          teamId: team.id,
        });
      }
    }
  }

  return { teams, advisors };
}

const built = buildDirectory();

export const TEAMS: AdvisorTeam[] = built.teams;

/**
 * The signed-in advisor. Placed on a Marina Bay team so the seeded campaigns,
 * which route to Bancassurance, actually land in their inbox — routing that
 * silently hides the demo data would read as a bug.
 */
export const DEMO_ADVISOR: Advisor = {
  id: 'adv-steven-raynaldi',
  name: 'Steven Raynaldi',
  email: 'steven.raynaldi@mywealth.com.sg',
  teamId: 'marina-bay-branch',
};

export const ADVISORS: Advisor[] = [DEMO_ADVISOR, ...built.advisors];

export function teamById(id: string): AdvisorTeam | undefined {
  return TEAMS.find((t) => t.id === id);
}

export function teamsForChannel(channel: string): AdvisorTeam[] {
  return TEAMS.filter((t) => t.channel === channel);
}

function advisorsForTeams(teamIds: string[]): Advisor[] {
  return ADVISORS.filter((a) => teamIds.includes(a.teamId));
}

/* -------------------------------------------------------------------------- */
/* Resolution                                                                 */
/* -------------------------------------------------------------------------- */

export type RoutingSpec = Pick<Campaign, 'channel' | 'teamIds' | 'advisorIds'>;

/** The teams a campaign actually reaches: the named ones, or the whole channel. */
export function resolveTeams(routing: RoutingSpec): AdvisorTeam[] {
  if (!routing.channel) return [];
  const inChannel = teamsForChannel(routing.channel);
  if (routing.teamIds.length === 0) return inChannel;
  return inChannel.filter((t) => routing.teamIds.includes(t.id));
}

/** The advisors a campaign actually reaches, after every level of narrowing. */
export function resolveRecipients(routing: RoutingSpec): Advisor[] {
  const teams = resolveTeams(routing);
  const pool = advisorsForTeams(teams.map((t) => t.id));
  if (routing.advisorIds.length === 0) return pool;
  return pool.filter((a) => routing.advisorIds.includes(a.id));
}

/**
 * Whether one advisor sees this campaign. Advisor-authored campaigns are
 * private to their creator and never routed, so they are matched by author
 * rather than by channel.
 */
export function campaignReachesAdvisor(campaign: Campaign, advisorId: string): boolean {
  if (campaign.origin === 'advisor') return campaign.createdByAdvisorId === advisorId;
  return resolveRecipients(campaign).some((a) => a.id === advisorId);
}

/** "Bancassurance — Singapore · Marina Bay Branch · 4 advisors" */
export function describeRouting(routing: RoutingSpec): string {
  if (!routing.channel) return 'Not routed';

  const teams = resolveTeams(routing);
  const recipients = resolveRecipients(routing);

  const teamPart =
    routing.teamIds.length === 0
      ? `all ${teams.length} teams`
      : teams.map((t) => t.name).join(', ');

  const advisorPart =
    routing.advisorIds.length === 0
      ? `${recipients.length} advisor${recipients.length === 1 ? '' : 's'}`
      : `${recipients.length} named advisor${recipients.length === 1 ? '' : 's'}`;

  return `${channelName(routing.channel)} · ${teamPart} · ${advisorPart}`;
}
