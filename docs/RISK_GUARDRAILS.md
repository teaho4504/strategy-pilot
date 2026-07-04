# Risk Guardrails

## Current Safety State

The current `main` branch is a Vite React frontend mock dashboard.

The following are not implemented on `main`:

- FastAPI backend
- Kiwoom REST live integration
- Kiwoom realtime WebSocket integration
- WebSocket gateway
- Strategy Worker
- Risk Worker
- Order Worker
- Paper Trading
- Live trading

## Non-negotiable Rules

- Frontend must never store Kiwoom credentials.
- Frontend must never call Kiwoom REST directly.
- Frontend must never open Kiwoom WebSocket directly.
- Frontend must call only project-owned backend APIs such as FastAPI `/api/*`.
- Kiwoom token handling must happen only in the FastAPI backend.
- Live trading must remain disabled and unimplemented.
- Order placement, amendment, and cancellation must remain blocked.
- `feature/backend-account-integration` must not be merged wholesale.
- `backend/app/api/orders.py` must not be included in Phase 1.

## Phase 1 Safety Requirements

Phase 1 FastAPI work must:

- Default to mock mode.
- Keep all credentials in backend-only environment.
- Return explicit configuration errors when live mode is requested without credentials.
- Expose read-only account data contracts only.
- Avoid live order code entirely.
- Avoid returning tokens, app keys, secret keys, account numbers, or masked forms of those values from status APIs.

Current `feature/fastapi-readonly-account` backend work adds read-only FastAPI endpoints only. It does not add order endpoints, WebSocket runtime, worker runtime, Vercel config, or Docker/AWS deployment files.

## Excluded Risk Areas For Phase 1

- Live orders
- Order cancellation
- Order amendment
- Realtime trading decisions
- Strategy automation
- Worker orchestration
- Browser-held broker secrets

## Phase 1 Allowed Kiwoom TRs

- `au10001`
- `ka00001`
- `kt00001`
- `kt00004`
- `kt00005`
- `ka10085`

All order, realtime, quote, chart, condition-search, and US stock APIs remain excluded from Phase 1.

## Local Live Read-only Verification Guardrails

- Live verification is blocked unless `KIWOOM_MODE=live`, `KIWOOM_READ_ONLY=true`, `KIWOOM_ENABLE_ORDER=false`, and `KIWOOM_LIVE_VERIFY_CONFIRM=I_UNDERSTAND_READ_ONLY` are all set.
- Verification output must not include tokens, app keys, secret keys, account numbers, balances, stock names, stock codes, or masked forms of secrets.
- Raw Kiwoom responses must not be committed.
- Verification stops on the first TR failure unless a later task explicitly defines a different failure policy.
