# Project Context

## Current Baseline

- Repository: `teaho4504/strategy-pilot`
- Frontend: Vite + React root application
- Production deployment assumption: Vercel serves the root Vite frontend from `main`
- Current backend work: separate FastAPI read-only account foundation on `feature/fastapi-readonly-account`

## Phase 1 Backend Scope

The FastAPI backend is limited to read-only account data for dashboard use.

Allowed Kiwoom TRs:

- `au10001`: OAuth access token issue, backend only.
- `ka00001`: account lookup.
- `kt00001`: cash lookup.
- `kt00004`: account valuation lookup.
- `kt00005`: holdings lookup.
- `ka10085`: account performance lookup.

Excluded:

- Orders, amendment, cancellation, and live trading.
- WebSocket realtime ingestion.
- Workers.
- Docker or AWS deployment files.
- Vercel settings.
- Frontend UI changes.

## Security Position

- Default mode is `KIWOOM_MODE=mock`.
- Read-only mode defaults to `KIWOOM_READ_ONLY=true`.
- Order enablement defaults to `KIWOOM_ENABLE_ORDER=false`.
- Kiwoom credentials must stay in backend-only environment variables.
- Status APIs must not return tokens, app keys, secret keys, account numbers, or masked forms of those values.
