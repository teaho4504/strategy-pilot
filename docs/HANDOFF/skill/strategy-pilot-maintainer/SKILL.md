---
name: strategy-pilot-maintainer
description: Safely inspect, transfer, run, document, and extend the strategy-pilot Vite React + FastAPI + Python Kiwoom US-stock trading project. Use when continuing this repository on another machine, diagnosing dashboard/backend/session/TR flows, adding a feature across backend and frontend, validating read-only market/account integrations, or reviewing trading safety and roadmap status.
---

# Strategy Pilot Maintainer

## Start every task

1. Locate the repository and read its `AGENTS.md`.
2. Read only the references needed for the request:
   - Current implementation status: `references/current-state.md`
   - Feature flow and ownership: `references/implementation-flows.md`
   - Architecture, TR inventory, and persistence: `references/architecture-and-data.md`
   - Planned order of work: `references/roadmap.md`
   - Safety constraints: `references/safety-boundaries.md`
   - Machine migration: `references/new-device-setup.md`
3. Run `git status --short --branch` before editing. Assume the worktree may contain important uncommitted user work.
4. Never clean, reset, checkout, delete, stage, commit, or push unless explicitly requested.

## Preserve the architecture

- Keep the frontend in root `src/` using Vite, React, TypeScript, React Query, and React Router.
- Keep broker access server-side in `backend/`; never call Kiwoom directly from the browser.
- Keep strategy and risk calculations in Python modules, separate from transport and UI code.
- Keep credentials in the local OS keyring or server-only environment variables.
- Treat the current branch as experimental. Verify runtime behavior instead of trusting filenames or old documentation.

## Implement one feature end to end

For a feature that changes displayed or actionable data:

1. Confirm the official Kiwoom TR/channel and request/response contract.
2. Add or update the provider inventory and request/response mapping.
3. Implement the backend service without leaking raw credentials, tokens, account numbers, or full broker payloads.
4. Expose a typed FastAPI endpoint and schema.
5. Add the frontend API client method and TypeScript type.
6. Connect a React Query query/mutation to the appropriate page.
7. Represent loading, empty, stale, blocked, and error states explicitly.
8. Add network-free unit tests and integration-shape tests.
9. Update `docs/PLAN.md`, `docs/RISK_GUARDRAILS.md`, and `docs/TASK_LOG.md` when implementation status or safety behavior changes.

## Trading safety

- Default to read-only observation: `KIWOOM_READ_ONLY=true`, order flags false, runtime lock present.
- Never remove or bypass the runtime order lock as a convenience fix.
- Never follow an HTTPS token request redirected to HTTP.
- Do not treat order acceptance as a fill. Confirm through F4/F5 and read-only account TR reconciliation.
- Block new entries on stale quotes, disconnected WebSocket, unknown order state, insufficient cash, unresolved reservations, or failed risk checks.
- Do not execute a real broker order while validating code or documentation.
- Read `references/safety-boundaries.md` before any auth, remote access, order, liquidation, or automatic-exit change.

## Verification

Run the smallest relevant tests while iterating, then finish with:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m compileall -q backend
PYTHONPATH=backend backend/.venv/bin/python -m pytest -p no:cacheprovider backend/tests backend/trading_engine/tests
npm test -- --run
npx tsc --noEmit
npm run build
git diff --check
git status --short
git diff --cached --name-only
```

Report tests that were not run. Never claim live verification from fake transport tests.

## Transfer to another Mac

Use `scripts/export_worktree.sh <output-directory>` to create a source overlay that excludes known secrets, databases, dependencies, and generated files. Follow `references/new-device-setup.md`; do not copy the macOS Keychain or dashboard PIN file.
