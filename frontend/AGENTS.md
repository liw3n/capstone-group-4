# Frontend Agent Guide

## Scope and runtime

This directory is a project-owned React 19 + TypeScript frontend built with
Vite 6 and Tailwind CSS 4. It was adapted from the provided MyWealth CRM
prototype; it is no longer a gitlink or external submodule.

Use Node.js 20 LTS and npm. Run commands from `frontend/`:

```bash
npm ci
npm run dev
npm run lint
npm run build
```

The development server listens on port `3000` and proxies `/api` to the FastAPI
service on `http://localhost:4000`.

The product north star is a human-supervised FA campaign companion. UI work
should make the end-to-end campaign flow demonstrable: discover, match, explain,
draft, confirm, log/follow up, and measure. Avoid adding generic chat features
that do not advance that workflow.

## Architecture

- `src/App.tsx` owns the prototype CRM state and view selection.
- `src/components/` contains screens, modals, and the PULSE chat panel.
- `src/services/chatApi.ts` is the typed boundary to the backend chat API.
- `src/services/ai.ts` contains the CRM prototype's simulated meeting and
  campaign helpers; do not confuse these with the live PULSE chat integration.
- `src/data/seed.ts` supplies only the fixed prototype date; scoped CRM contacts
  come from PostgreSQL `mock_client` through `services/contactApi.ts`.

## Change rules

- Keep the backend base URL configurable with `VITE_API_BASE_URL`. Never put
  provider keys, database credentials, or company API credentials in Vite
  variables because they are exposed to browsers.
- Use `/api/chat/...` routes from the frontend and preserve backend support for
  both `/chat/...` and `/api/chat/...`.
- Keep API calls in service modules rather than UI components.
- Keep chat requests abortable. Adviser/session changes must not allow stale
  session lists, history, or provider responses to overwrite current state.
- Preserve actionable error handling for network, validation, storage, provider
  rate-limit, and provider-timeout failures. Never display credentials or raw
  connection strings.
- Preserve the distinction between leads and contacts and between deterministic
  audience selection and AI-generated ranking/copy.
- Show clear reasons for client eligibility and allow the adviser to remove or
  correct recommendations before outreach.
- Respect channel consent in both UI state and server requests. A disabled send
  button is not sufficient enforcement, but the UI should make exclusions and
  consent status visible.
- Require an explicit final review/confirmation before simulated or real
  communication. Never auto-send as a side effect of a chat response.
- Label seeded, generated, and simulated content clearly. Add an appropriate
  disclaimer wherever generated copy could be read as financial advice.
- Add component/service tests when a test harness is introduced. Until then,
  run both TypeScript checking and the production build for every change.
- Do not commit `node_modules/`, `dist/`, `.env` files, logs, or Vite caches.

## Environment

`VITE_API_BASE_URL` is optional. Leave it empty in local development to use the
Vite proxy. Set it to the externally reachable API origin in deployments where
the frontend and backend are served separately.

## Known gaps

- Contacts, campaign definitions, lead triage, adviser actions and simulated
  email receipts persist through FastAPI. Tasks, pipeline cards and role
  selection remain React state.
- PULSE chat, contacts and campaigns are connected to the FastAPI backend.
- Chat sessions and successful user/assistant exchanges persist in PostgreSQL;
  drafts, open/closed panel state, and optimistic messages remain browser state.
- Role selection is a prototype, not authentication or authorization.
- No automated frontend test runner is configured; `npm run lint` is currently
  a strict TypeScript check.
- Campaign sends and CRM updates are demonstrations without a server-enforced
  confirmation/audit workflow.
- The supplied GWM OpenAPI documents are not yet consumed. Integrate them
  through a server-side adapter rather than calling internal services directly
  from the browser.
