# MyWealth CRM — project reference

This is the single reference document for this project. It exists so anyone
picking the code up can do so without re-deriving decisions already made.
When it disagrees with the code, the code wins — update this file, don't
work around it.

**Repo:** https://github.com/Stevenraynaldi/Capstone-CRM

## What this is

A CRM prototype for financial advisors / relationship managers (Singapore
market) covering contacts, tasks, pipeline tracking, campaigns, and a PULSE AI
assistant, styled to match a production reference called "MyWealth". Contacts,
campaign records/state and chat sessions/messages use FastAPI/PostgreSQL. Tasks
and pipeline cards remain React state and reset on refresh.

Originally scaffolded in Google AI Studio as "Pulse CRM" with a working
Gemini/Express backend, then rebuilt twice (see History below) into its
current form.

## Run it

Use the [shared team setup guide](../README.md#team-setup-and-development-workflow).
After bootstrapping and configuring the backend key, run from the repository root
in the team's macOS/Linux/WSL Bash environment:

```bash
make provision
make dev
```

`make dev` starts FastAPI :4000, FastMCP :8001 and Vite :3000 together. Open
http://localhost:3000 and demonstrate MCP features through the existing CRM/PULSE
interface. Do not create a separate feature demo application.

For frontend-only work with the shared backend already running, use
`make frontend-dev` from the repository root. Vite proxies `/api` to
`http://localhost:4000`. For a separately hosted backend, set `VITE_API_BASE_URL`
in `.env.local`; provider credentials belong only in the backend and must never
use the `VITE_` prefix.

| Script | Does |
| --- | --- |
| `npm run dev` | Vite dev server, port 3000 |
| `npm run build` | Production build to `dist/` |
| `npm run preview` | Serve the production build |
| `npm run lint` | `tsc --noEmit` type check |

## Stack

React 19 + TypeScript + Vite 6 + Tailwind v4 (CSS-first `@theme`, no config
file) + `motion` (Framer Motion) + `lucide-react` + `xlsx` (SheetJS, lazy-loaded
on demand for the upload wizard only — keeps it out of the main bundle).

## File layout

```
src/
  App.tsx              browser CRM state + tab routing (no router library)
  types.ts             domain model
  data/seed.ts         fixed prototype date only; no CRM records
  services/ai.ts       simulated CRM meeting/campaign AI helpers
  services/chatApi.ts  typed client for the persisted PULSE chat API
  services/campaignApi.ts typed client for persisted campaign records/state
  services/contactApi.ts typed client for scoped mock_client CRM records
  lib/format.ts        date, phone, due-in, empty-value formatting
  lib/targeting.ts     campaign criteria matching — RULES, not AI
  lib/directory.ts     channel -> FA team -> FA routing (who RECEIVES a campaign)
  lib/email.ts         campaign email composition (preview and send share it)
                        + who a campaign has already reached
  lib/leads.ts         lead-list import rules (name + email or mobile)
  lib/spreadsheet.ts   Excel/CSV parsing (SheetJS, dynamic import), the
                        mapped-column cell reader, and the CSV templates
  ui/                  Button.tsx, Chip.tsx, Modal.tsx — shared primitives
  components/          one file per screen + its modals (see Modules below)
docs/
  test-runbook.html    interactive QA runbook — open it in a browser
```

There is no router and no state management library. `App.tsx` holds every
`useState` and passes handlers down as props; `activeTab` (a string) plus
`selectedContactId` / `selectedCampaignId` drive all navigation. `session`
gates the whole app — when it is null you get the sign-in screen instead.

## Domain model (`src/types.ts`)

```
ContactLabel    'Prospect' | 'Client'                    — exactly two, no more
ContactStatus   'lead' | 'contact'                        — absent means contact
ContactSource   'own' | 'transferred' | 'canvassed' | 'referral' — absent means 'own'
Policy          provider, type, since                     — a policy the contact already holds
Gender          'male' | 'female'
NumericRange    min?, max?                                — either end may be open
PipelineStage   'opportunities' | 'activities' | 'closed'
ClosedOutcome   'won' | 'lost'                            — only set once stage is 'closed'
TaskType        'CRM' | 'Compliance' | 'Campaign' | 'Manual'
Role            'marketing' | 'advisor'                   — picked at sign-in
AgeGroup        'under35' | '35to44' | '45to54' | '55to64' | '65plus'
CashBand        'under50k' | '50kTo250k' | '250kTo1m' | 'above1m'

Contact         id, name, email, countryCode, phone, dob?, nric?, label?,
                bookmarked?, needsAttention?, notes?, meetings?, profile?,
                policies?, lastContacted?, source?, transferredFrom?,
                transferredOn?, introduced?
ContactProfile  the Contact Info tab fields (address, employment, etc.) — all optional
MeetingSummary  id, date, title, description, tasks[]      — one per timeline entry
PipelineItem    id, caseId, contactId, contactName, contactLabel?, stage,
                closedOutcome?, startDate, dueDate, description?, archived?
Task            id, contactId, contactName, title, description, type,
                startDate, dueDate, status, campaignId?
Session         name, email, role
CampaignCriteria
                ageGroups[], ageRange?, genders[], cashBands[], cashRange?
AdvisorTeam     id, name, channel                         — a branch/agency/firm
Advisor         id, name, email, teamId
CampaignOrigin  'marketing' | 'advisor'
CampaignAudienceSource
                'contacts' | 'leads'                      — never both
LeadStats       uploaded, added, removed
Campaign        id, name, description, clientMessage, bannerDataUrl?,
                origin, audienceSource, channel?, teamIds[],
                advisorIds[], createdByAdvisorId?, criteria,
                includeIds[], excludeIds[], leadIds[], leadStats,
                createdBy, createdAt,
                actions (contactId -> 'pipeline' | 'task' | 'dismissed'),
                emailLog[]
CampaignEmail   id, sentAt, subject, fromName, fromEmail, recipientIds[],
                signOff                                   — one mass-send
```

**`status` is deliberately not a third `ContactLabel`.** `label` says what kind
of relationship this is (Prospect vs Client); `status` says whether the record
is in the book at all. Merging them would silently change the meaning of every
`label === 'Prospect'` count, and would put a "Lead" option in the Contacts
filter and the pipeline case editor that could never match anything.

Routing narrows downward and empty means "all": `channel` alone reaches every
advisor in it, `teamIds` narrows to named teams, `advisorIds` narrows again to
named people. `createdByAdvisorId` is what keeps an advisor's private campaign
visible only to its author.

`channel` is optional because advisor-created campaigns have no channel at all —
they are not routed anywhere. `origin` is an explicit field rather than being
inferred from a missing `channel`, so the meaning does not depend on a hole in
the data.

`emailLog` is separate from `actions` on purpose: emailing a client and putting
them in the pipeline are not mutually exclusive, so a single per-contact action
field could not express both.

`Contact.gender` and `Contact.cashAmount` are the campaign targeting attributes.
They sit on `Contact` rather than inside `ContactProfile` because only about
half of contacts carry a profile at all, and targeting needs to work regardless.
Cash availability is **investable cash, not income** — `profile.annualIncome`
is a display string and is deliberately not the same field. Cash is stored as
an **amount**, not a band; the band is derived by `cashBandOf()`, so band
filters and custom-amount filters read one number and cannot disagree. Both are optional:
a handful of seed records leave them blank on purpose (see Conventions).

Phone is **always** `countryCode` + `phone` as two fields, never one string —
this was a deliberate change from the original single-string phone. Format
for display with `formatPhone()` from `lib/format.ts`.

**`ContactSource` is a historical fact, not an editable status.** It is set
once — by the Add Contact form (`'own'`), by the Upload Contacts wizard's
Origin step (`'own'` / `'transferred'` / a redirect to Campaigns for
`'canvassed'`), or by seed data — and never edited afterwards, unlike
`ContactLabel` which the advisor changes freely. Only `'transferred'` carries
follow-up state: `transferredFrom` / `transferredOn` / `introduced`, the last
of which starts `false` and flips permanently once the advisor confirms they
have actually spoken to the client. A transferred contact holds real policies
and real history from day one — `introduced` tracks the relationship, not the
paperwork. `SourceChip` in `ui/Chip.tsx` renders nothing for `'own'`
deliberately: tagging most of the book "Own contact" would be noise.

## Modules

- **Sign-in / roles** — The app opens on a sign-in screen that picks a **role**,
  not an identity: *Financial Advisor* or *Marketing*. There is no auth, no
  password field, and the screen says so. The role decides the sidebar:
  advisors get Home / Contacts / Tasks / Pipeline / Campaigns / Settings,
  Marketing gets Campaigns / Settings only — it has no book of business, so
  showing it someone else's clients would be wrong. Signing out drops the
  session but **keeps all data**, which is what makes the marketing → advisor
  handoff demonstrable in one sitting.
- **Home** — summary cards (open tasks, active deals, total contacts), five
  most urgent tasks, active pipeline cases. No AI content — the original "AI
  Portfolio Segmentation Lab" was cut (it was fully scripted `setTimeout`
  theater with no real logic behind it).
- **Contacts** — searchable/sortable registry (name, email, label columns
  sort; contact number does not). Bulk-select checkboxes. Summary cards read
  live from the list. **Add Contact** modal: Name/Email/Phone required,
  DOB/NRIC optional, new contacts default to `Prospect` and `source: 'own'`.
  **Upload Contacts** wizard: 4 steps (**Origin** → Upload → Match → Complete),
  imports Excel or CSV. The new Origin step asks where the list came from
  before anything else: *My own contacts* and *Transferred from another
  advisor* proceed to upload (transferred additionally asks for the previous
  advisor and transfer date, and imported rows default to `Client` rather than
  `Prospect`); *Roadshow or canvassing* explains why that doesn't belong in
  the contact book and redirects to Campaigns' lead-list flow instead — this
  is the same "leads stay out of contacts until promoted" rule the Campaigns
  module enforces, applied at the front door. Import runs every row through
  `lib/dedupe.ts` (`findDuplicate`/`partitionIncoming`) against the existing
  book and against the rest of the file — NRIC first, then email, then
  phone — and the completion screen reports skipped-for-missing-fields and
  already-a-duplicate as two separate counts, since they mean different
  things. Detail view has two tabs: **Engagement Timeline** and **Contact
  Info** (no AI Insight tab — removed, see History). A contact transferred
  from another advisor and not yet marked introduced shows a banner on their
  detail page with a one-click **Mark as introduced**; Contact Info also
  lists any **Policies Held**.
- **Meeting summaries** — reached via "New Meeting Summary" on a contact's
  timeline. Four stages: input (date + file drop + notes) → simulated
  progress bar → editable AI review (title, summary, 5 generated tasks with
  checkboxes) → save. Checked tasks become real rows in the Tasks module;
  unchecked ones are discarded. Editing an *existing* summary (via "Edit
  Summary") does not regenerate tasks — only the generate flow does that.
- **Tasks** — To-Do/Done tabs with live counts, search (title + description +
  contact), multi-select Task Type and Contact filters, 10-per-page
  pagination. Add/Edit modal enforces due date ≥ start date.
- **Pipeline** — Kanban board, stages `Opportunities → Activities → Closed`.
  **Drag-and-drop** between columns (native HTML5 DnD, no library). Dropping
  onto Closed always opens a **Won / Lost** prompt first; cancelling leaves
  the card in its original column — this is the single most important
  behavior to protect if this screen is touched again. Case detail modal,
  contact picker for adding new cases, and an Archive tab (archive/restore).
- **Campaigns (Marketing)** — List of everything sent, with reach and
  advisor-response counts. Clicking a campaign opens a **read-only detail view**
  built for the person who sent it: advisors reached, clients identified, take-up
  rate, dismissals, a stacked bar splitting the audience into *taken up /
  emailed-awaiting / dismissed / not contacted* (four mutually exclusive buckets
  that always sum to the audience), the recipient roster grouped by team, and
  the email send log. It shows **no client names** — Marketing sets the criteria,
  the advisor owns the relationship. Advisors are named, because knowing which
  of them has not touched a campaign is the point of sending it. **New Campaign** opens a full-page builder: name,
  internal description, client-facing messaging, banner upload, the three
  targeting criteria, and a channel. A live **Estimated audience** panel
  recomputes on every criteria change against loaded mock clients, warns
  when nothing matches, and separately reports how many contacts were excluded
  for incomplete profiles. The banner is a data URL persisted with the synthetic
  campaign, capped at 1MB; there is no separate file storage.
- **Distribution routing** — Marketing sends down a three-level hierarchy:
  **Channel → FA Team → FA**. Each level narrows the one above and leaving a
  level untouched means all of it, so a whole-channel send is one click and a
  three-named-advisor send is still possible. Resolution lives in
  `lib/directory.ts`; the builder resolves the final adviser IDs and the backend
  stores/enforces those assignments, so an inaccessible campaign never reaches
  the component.
  Teams are modelled the way each channel is actually organised — bancassurance
  by branch, tied agency by group, partnership by partner firm. In the builder,
  channel is the decision and everything under it is an exception: the team and
  advisor controls stay **collapsed** behind a "Narrow" toggle, since picking a
  channel already includes everyone in it. They auto-open when a campaign is
  already narrowed, so a saved exception is never hidden from whoever edits it.
- **Campaigns (Advisor)** — Inbox of campaigns received from Marketing **plus
  the advisor's own**. Advisors can create a campaign with **New Campaign**: the
  same builder, minus the Channel section entirely (not disabled — absent), with
  its own copy and a *Create campaign* button. A personal campaign goes nowhere;
  it sits in that advisor's list, matches their book, and feeds the same AI
  ranking and mass-email flow. Own campaigns carry a purple **Your campaign**
  chip, read "Created by you · not sent to anyone", and label the description
  field *Your notes* rather than *Campaign brief*. **Marketing never sees them**
  — the backend returns only marketing-origin campaigns. The detail view shows
  the campaign's banner, brief, messaging, and criteria, then **Identified
  clients**: the matched audience, ordered by AI, each row expandable to a
  "why this client" rationale (with the raw score) and a personalised draft
  message. Per client the advisor can **Add to pipeline**, **Create task**
  (a `Campaign`-type task carrying the draft message as its description), or
  dismiss. Below it, **Incomplete profiles** lists the contacts held out of
  the audience and exactly which field each is missing.
- **Lead campaigns** — **Marketing and advisors both** can build a campaign
  whose audience is an uploaded roadshow or canvassing list instead of the book.
  A Marketing lead list is routed like any other campaign; the receiving
  advisors are the ones who promote or discard the names, since Marketing has no
  book to promote them into. The builder swaps
  the criteria and audience sections for an upload panel (drop file → auto-match
  columns → preview). Import needs **a name plus an email or a mobile** — looser
  than the Contacts wizard, because canvassing capture is messy; failing rows
  are counted and reported. Every row becomes a `status: 'lead'` contact,
  **invisible outside the campaign module**. The detail view shows a plain
  name/email/mobile table with **Add to contacts** or **Remove**, and no AI
  ranking — a lead has no age band, cash band, label or meeting history, so
  priority and rationale would be blank or identical for every row.
  **Add to contacts** promotes in place (keeps its id, gains the Prospect
  label, appears in Contacts from then on); **Remove** deletes the record
  outright. `leadStats` survives either way, so the campaign always reports
  *uploaded / pending / added / removed* even after the people are gone.
  Lead campaigns can be mass-emailed like any other.
- **Hybrid audiences** — Advisor contact campaigns layer hand-picked overrides
  on the criteria: `includeIds` pulls in someone the rules missed, `excludeIds`
  drops a match. The criteria half stays a **live query**; the overrides always
  win. The audience panel shows the arithmetic ("2 from criteria · +1 added ·
  −1 removed"). Marketing has no book of business to pick from, so it gets
  criteria only.
- **Mass email** — **Email clients** on the campaign detail opens a three-stage
  flow: *review* (sender, editable subject, per-recipient checkboxes, and a full
  body preview rendered as any chosen recipient receives it) → *confirm* (a
  plain summary of exactly what is about to go out) → *receipt*. The body is
  greeting + the campaign's client messaging **verbatim** + the advisor's sign-off;
  the AI-personalised drafts on the table are for one-to-one follow-up, not the
  mass send. Recipients missing a usable email are excluded and named. Anyone
  already emailed, or dismissed, is deselected by default but can still be
  picked for a deliberate resend. Sends are recorded on `emailLog`, surfaced as
  "Emailed" chips per row and as counts on both the advisor inbox and
  Marketing's cards. The log persists with the campaign in PostgreSQL. **Nothing
  is transmitted** — there is no mail transport, and the confirm and receipt
  screens both say so.
- **Email sign-off** — set from the **Email sign-off** button on the advisor's
  campaign inbox, or inline from the send flow. It belongs to the advisor, not
  to a campaign: one template, reused by every send. Supports
  `{{advisor_name}}`, `{{advisor_email}}`, and `{{client_name}}` tokens, with a
  live preview and a reset-to-default.
- **Settings** — static placeholder, four inert cards. Explicitly not wired up.

## The AI seam (`src/services/ai.ts`)

Three CRM workflow features are described as AI-powered. These remain simulated
inside `services/ai.ts`.

| Function | Real | Faked |
|---|---|---|
| `suggestColumnMapping` | Spreadsheet parsing (SheetJS reads your actual file); the column-matching heuristic runs against real headers | — |
| `analyseMeeting` | Progress reporting, task/date shaping | Reading file *contents* (files are listed by name only); the summary and task text is a fixed template |
| `rankCampaignAudience` | The score — a real weighted formula over real contact fields (cash band, label, attention flag, bookmark, meeting history) | The rationale sentence and draft message, both templated |

**Campaign audience selection is not in this file and is not AI.** It is a
rules engine in `lib/targeting.ts`. That split was deliberate: who gets marketed
to has to be reproducible and explainable — an advisor asking "why was this
client targeted" gets the same answer every time — so rules decide *who*, and
the model only decides *emphasis*. `rankCampaignAudience` cannot add or remove
a client from the list it is handed; it reorders and annotates.

To make any of them real: replace the exported function with a call to a
server-side route. Their input/output shapes are the contract the UI depends
on — keep those stable and nothing else needs to change.

The floating **PULSE assistant** is separate and real: `components/ChatPanel.tsx`
uses `services/chatApi.ts` to load adviser sessions and history and send queries
through `/api/chat/...`. Successful exchanges are persisted by PostgreSQL. The
panel cancels stale list/history/provider requests when its adviser or session
context changes, exposes retryable storage/network errors, and labels generated
responses with a verification/no-auto-send notice. The browser never holds the
model-provider key.

## Conventions / gotchas

- **Dates.** Anchored to a fixed "today", `TODAY_ISO = '2026-08-26'` in
  `src/data/seed.ts`, so copy like "710 days overdue" stays stable across
  reloads. Always format with `toISODate()` / the helpers in `lib/format.ts`
  — **never `toISOString()`**, which shifts the date back a day for anyone
  east of UTC (this was a real bug, caught and fixed once already).
- **Colour.** Orange = primary CTA + active nav state. Blue = links and
  secondary actions. Semantic colors (success/danger/purple/pink) are
  separate from the accent. All tokens defined in `src/index.css` under
  `@theme` (Tailwind v4 CSS-first config).
- **Shared class strings** live as Tailwind v4 `@utility` rules in
  `src/index.css` — `input-field` (every text input, select and textarea),
  `field-label`, `table-head`, `cell`. Reach for one of those before
  re-declaring a class string in a component.
- **Selectable lists live with their type.** `TASK_TYPES` and
  `CONTACT_LABELS` in `src/types.ts`, `CONTACT_FIELDS` in `services/ai.ts`.
  Every picker and filter reads the same array, so a new task type or label
  is one edit rather than a hunt through the components.
- **Empty values.** Always render through `display()` / `EMPTY` from
  `lib/format.ts`, which maps blanks and `\N`-style import artifacts to an
  en dash (`–`). Never let a raw null-artifact reach the UI.
- **Task dates.** Due date must never precede start date. Enforced in both
  the manual Add/Edit Task modal and the generated-task editor. (The
  original reference screenshots showed a task starting *after* its own due
  date — treated as a bug in the source material, not reproduced.)
- **Contact data comes from PostgreSQL.** `mock_client` is the only CRM contact
  dataset. The demo adviser receives 12 of the 14 synthetic rows; the other
  adviser and tenant rows are excluded by the API query. The same DOB, gender,
  cash and contact IDs drive both `lib/targeting.ts` and MCP recommendations.
- **Some records are incomplete on purpose.** The checked-in mock clients include
  missing DOB, cash and gender values so the campaign incomplete-profile path is
  exercised without the frontend inventing replacements.
- **Custom ranges OR with their bands.** Age and cash each accept a custom
  range alongside their bands, and a contact matches that dimension on *either*.
  This is the same OR rule that already applies between bands, so the semantics
  did not need a new explanation: OR within a dimension, AND across them. A
  dimension filters when it has bands selected **or** a range set.
- **Demographic is gender.** It was six lifestyle segments (Young Professional,
  Pre-Retiree, and so on); it is now simply Male/Female. The AI draft opener
  that used to key off segment now keys off **age**, because life stage is what
  changes the financial argument and gender is not a reason to write to someone
  differently.
- **Unknowns are excluded, not guessed.** A contact missing a field a campaign
  filters on is never treated as a match *or* a rejection: it goes to
  `incomplete` and is surfaced separately, so a data gap reads as a prompt to
  the advisor rather than a silent omission.
- **Routing filters the inbox, not the audience.** Channel/team/advisor decides
  *which advisors see a campaign*. It does not decide *which clients are in it* —
  that is still criteria over the book (`lib/targeting.ts`). Keep the two apart:
  they are different questions with different answers.
- **Contact ownership is enforced in SQL.** The contact API requires an adviser
  scope and filters by both tenant and `fa_id` before returning records.
- **Seeded campaigns route to the demo advisor on purpose.** Both land in
  Bancassurance, one channel-wide and one narrowed to Marina Bay Branch, because
  routing that silently emptied the demo inbox would read as a bug rather than a
  feature. If you reseed, keep `DEMO_ADVISOR` inside the seeded channel.
- **The lead boundary is one line.** `activeContacts` in `App.tsx` filters out
  `status: 'lead'` and is what Home, Contacts, Tasks, Pipeline and the campaign
  builder receive — never the raw `contacts` array. `resolveAudience()` applies
  the same filter internally for criteria matching, so a lead can never surface
  in a contact campaign's audience or its incomplete-profiles list. Only the
  advisor's campaign inbox and campaign detail get the unfiltered array, because
  they are the only screens that must see leads. Add a new consumer of
  `contacts` and this is the decision to get right.
- **Email preview and send are composed by one function.** `composeEmailBody()`
  in `lib/email.ts` builds the body for both the confirmation preview and the
  recorded send. Compose them separately and the advisor can approve one thing
  while another gets logged — keep the single source.
- **No chained `setTimeout` in front of content.** `rankCampaignAudience` is
  async but has no simulated latency, deliberately. A backgrounded tab throttles
  chained timers to roughly one tick per second, so a progress walk that gates
  the results leaves the advisor staring at "Prioritising…" indefinitely — hit
  live during testing. Same root cause as the AnimatePresence bug below. The
  meeting flow still has a progress walk (pre-existing, and there the wait is
  the point), but do not add that pattern to anything that merely displays data
  already in memory.
- **AnimatePresence gotcha.** The top-level view switcher in `App.tsx`
  deliberately does *not* use `<AnimatePresence mode="wait">` — that mode
  blocks the incoming view until the outgoing exit animation completes,
  which never fires while the tab is backgrounded (requestAnimationFrame is
  paused), leaving the app stuck on the previous screen. Found live during
  testing. Don't reintroduce it here without solving that first.
- **Bundle size.** `xlsx` (SheetJS) is ~330KB and only needed by the upload
  wizard, so it's a dynamic `import()` in `lib/spreadsheet.ts`, not a
  top-level import. Keep it that way.

## Explicitly not built / known gaps

- **Edit Contact** button on the contact detail header is inert (no modal
  wired up yet). Add Contact's modal exists and could be reused for this.
- **Settings** is a static placeholder with no logic.
- The old contact-level AI Insight tab and the Product Catalogue were removed
  (see History). The repository-level PULSE assistant is implemented as a
  floating adviser-only panel instead. The Campaigns module was removed
  in the MyWealth rebuild and then rebuilt from scratch to a new spec; the
  original version is not coming back.
- **Tasks and pipeline cards do not survive a refresh.** Contacts, campaign
  definitions, lead triage, adviser actions and simulated email receipts do.
- **Advisor campaigns cannot be edited or deleted** once created, and neither
  can Marketing's. Nothing in the module edits an existing campaign yet.
- **Leads cannot be edited, and more cannot be added to an existing lead
  campaign.** The upload happens once, in the builder; its resulting lead rows
  persist with the campaign.
- **Removing a lead is unrecoverable** and there is no undo anywhere in the app.
  Only the counter survives; the names of removed leads are not kept.
- **No duplicate detection on lead-list import**, by explicit decision — a
  roadshow lead who is already a client is imported again as a separate lead
  record. This is specific to Campaigns' lead lists (`lib/leads.ts`); the
  regular Contacts upload wizard *does* dedupe, via `lib/dedupe.ts` (see
  Contacts above). Wiring the same check into lead imports is a natural
  follow-up, not attempted here to keep the two upload paths' scope apart.
- **The campaign-detail email modal is still a simulation.** It persists a
  `CampaignEmail` against the campaign and does nothing more; its confirm and
  receipt screens state this plainly. The separate PULSE chat workflow uses
  backend MCP preview/confirmation tools, defaults to simulated delivery, and
  records successful recipients as campaign contact events. No frontend changes
  are required for that conversational flow.

## Testing

A self-contained interactive QA runbook lives at
[`docs/test-runbook.html`](docs/test-runbook.html) — open it straight from
disk in a browser, no build step. 77 test cases across 7 modules with pass/fail/blocked
tracking, notes, localStorage persistence, and Markdown export. Expected
values in it (710 days overdue, 18 task pages, "2 imported / 1 skipped",
etc.) are **verified against the running app** and double as regression
anchors — if a case's expected value stops matching, something changed.

The runbook file is pure ASCII with `\uXXXX`/CSS escapes for every
non-ASCII character (em dashes, arrows, icons) — served without a declared
charset it gets misread as windows-1252 and every special character
corrupts. Don't "clean up" those escapes back into literal Unicode.

## History — how we got here (compressed)

1. **Baseline** (`65c5507`) — AI Studio-generated "Pulse CRM". Had a working
   Express + Gemini backend (`/api/chat`, meeting-gap-analysis via
   `@google/genai`), a Campaigns module, an AI Insight chat tab on contacts,
   and a Product Catalogue. API key was exposed client-side in one service
   (`recommendationService.ts` read `process.env.GEMINI_API_KEY` in browser
   code) — a real problem, since fixed by removing that code path entirely.

2. **Rebuild as MyWealth** (`8dd15f0`) — Restyled to match a production
   reference ("MyWealth": navy headings, sentence case, 8px radii, orange
   primary/blue secondary, tighter enterprise tables) instead of the
   original AI-Studio look (heavy orange, `font-black uppercase`, 32–40px
   modal radii). Removed Campaigns, the AI Insight tab, the Product
   Catalogue, and the *entire* Gemini/Express layer — app became a pure
   Vite SPA, zero-config. Reseeded to 75 contacts / 180 tasks at production
   scale with a deterministic PRNG. Fixed the `toISOString()` timezone bug
   and an `AnimatePresence mode="wait"` stuck-view bug, both found via live
   browser testing during the rebuild.

3. **Feature additions** (`ab4f146`) — Per new requirements: contact labels
   cut from four (Prospect/Client/Warm lead/VIP) down to two; Add Contact
   modal built (Name/DOB/NRIC/Email/Phone, phone split into country code +
   number); three-step Upload Contacts wizard with real spreadsheet parsing;
   the meeting-summary flow rebuilt as a four-stage guided experience
   (input → progress → editable review → save) replacing a plain form,
   producing 5 tasks instead of the reference's 4; pipeline gained
   drag-and-drop plus the Closed-needs-Won/Lost gate. All new "AI" behavior
   was deliberately kept simulated behind `services/ai.ts` rather than
   reviving a backend — a conscious choice, not an oversight.

4. **QA runbook** (`79c6a15`) — Interactive HTML test plan covering
   everything above, built because screenshots of the running app couldn't
   be captured in that session (browser pane wasn't compositing frames);
   hand-drawn UI maps substitute for real screenshots in the runbook.

5. **Campaigns + roles** — Marketing authors a campaign (name, description,
   client messaging, banner, three targeting criteria, channel); advisors
   receive it alongside the clients from their book who match, and can push a
   client into the pipeline or raise a `Campaign` task carrying the drafted
   message. Four decisions shaped it: rules select the audience while AI only
   ranks and writes; role is picked at a new sign-in screen rather than
   splitting the app in two; channel is stored but does not route; and the
   targeting attributes had to be invented, because the book had no
   cash-availability field at all and only 36 of 75 contacts carried a profile.
   Found and fixed during live testing: chained `setTimeout` progress gating
   stalls indefinitely in a backgrounded tab.

6. **Campaign mass email** — A review → confirm → receipt flow on the campaign
   detail: sender is the signed-in advisor, recipients are the identified
   clients (selectable, with no-email cases excluded and already-emailed ones
   deselected by default), body is marketing's client messaging verbatim, and
   the sign-off comes from a token-based template the advisor sets once and
   reuses. Sends are logged on the campaign and surfaced to both roles. Nothing
   is transmitted, and the UI says so at both the confirm and receipt stages.

7. **Advisor-authored campaigns** — Advisors can now create their own campaign
   from the same builder with the Channel section removed entirely. It is
   private: it is not routed anywhere, Marketing's list and counters filter it
   out, and it is distinguished throughout by a *Your campaign* chip. Everything
   downstream — criteria matching, AI ranking, mass email — works identically to
   a received campaign. `Campaign.origin` was added as an explicit field rather
   than inferring authorship from a missing `channel`.

8. **Lead lists and hybrid audiences** — Advisors can build a campaign from an
   uploaded canvassing list. Those names become contacts tagged
   `status: 'lead'`, held out of the book until promoted with **Add to
   contacts** or deleted with **Remove**, with `leadStats` preserving the
   outcome either way. Separately, advisor contact campaigns gained hand-picked
   include/exclude overrides on top of the live criteria query. `status` was
   added as its own field rather than a third `ContactLabel`, and the
   hidden-by-default rule was concentrated into a single `activeContacts`
   derivation plus a filter inside `resolveAudience()`.

9. **Distribution hierarchy and Marketing lead lists** — Channel gained two
   levels beneath it (FA Team, then individual FA), backed by a real roster in
   `lib/directory.ts`, and the advisor's inbox is now filtered by that routing
   rather than showing everything. The sign-in screen carries an advisor
   identity so there is someone to route *to*. Marketing also gained the lead
   upload advisors already had, routed the same way — the receiving advisors
   promote or discard the names. Contacts still have no owning advisor, so
   routing decides who sees a campaign, not whose clients are in it.

10. **Reconciliation with a parallel branch** — For a stretch, `master` also
    carried a second, chat-based campaign implementation (an "AI Companion"
    panel over `services/actions.ts`, its own `Campaign`/`CampaignMember`
    shape) built independently on the same base as everything above. A
    careless merge of the two briefly left `master` non-compiling — duplicate
    declarations, mismatched imports, two incompatible `Campaign` types in one
    file. This history is the result of reconciling them by hand: this
    module's targeting/routing/lead/email system was kept as-is (Priority and
    Suggested outreach columns were also dropped from the identified-clients
    table in the same pass, having become dead weight next to the targeting
    match column), and `CompanionPanel.tsx` / `services/actions.ts` /
    the companion's `Campaign` type were removed entirely. What *was* ported
    over, because it was genuinely independent of the chat panel: contact
    provenance (`ContactSource`, the transferred/not-yet-introduced banner),
    policy holdings, and real duplicate detection on contact import
    (`lib/dedupe.ts`) — see Contacts above. The seed data for all of that
    runs as its own PRNG pass (`enrichProvenance`, seed `20260915`) for the
    same reason `enrichTargeting` does: the companion's original version drew
    from the *shared* `rand()` stream used for label/bookmark/profile
    generation, which would have reshuffled the entire 75-contact book and
    broken the QA runbook's anchored numbers had it been ported as-is.

## Open threads / natural next steps

The QA runbook does **not** yet cover campaigns, roles, the sign-in screen, or
the mass-email flow, lead lists, or hybrid audiences — that is the most obvious
gap now. Beyond it, in rough priority order: wire up
**Edit Contact** (and let it edit the new targeting fields, which are currently
read-only outside the seed); decide whether channel should actually route, which
needs an advisor roster and `advisorId` on contacts; decide whether **Settings**
needs real functionality or stays a placeholder; decide whether real screenshots
should replace the runbook's hand-drawn UI maps; decide whether/when the AI seam
should become a real backend integration.

## Licence

MIT — see [`LICENSE`](LICENSE).

Every contact is synthetic and checked into the local PostgreSQL seed/migration
SQL. There is no real client data here. CRM contact IDs and matching attributes
are shared with MCP, but raw records are not placed into model context by default.


## PULSE campaign recommendations

On an adviser campaign detail screen, open PULSE and use **Ask for recommended
clients**. The selected campaign ID is included in chat requests; the backend
retrieves the criteria and the MCP tool returns explained synthetic matches.
Switching campaign remounts the panel and aborts pending requests.

Campaign definitions and contacts come from the same scoped PostgreSQL rows used
by the MCP tools. Newly created active campaigns are available to PULSE, and
recommendation IDs map directly to the CRM contact rows shown in the frontend.

See [backend prototype documentation](../backend/docs/campaign_recommendations.md)
for the expected matches, assumptions and manual verification. Chat requires the
shared backend, database and provider setup through `make provision` / `make dev`.
Matching also has automated backend tests; no standalone tool demo script is
required. Focused chat rendering checks are available as described below.

Assistant answers render Markdown headings, emphasis, lists and tables. Client
recommendation and missing-profile tables display as compact cards in the chat
panel, including saved answers. Recognized `<br>` tags become line breaks; arbitrary
HTML and embedded images are disabled. User messages continue to display as text.

Run the focused rendering checks with `npm run test:chat`, followed by
`npm run lint` and `npm run build`. The rendering checks cover preserved campaign
content, normal tables/lists, untrusted markup, links and literal code. There is
still no complete frontend component or end-to-end test suite.
