# Risk Guardrails

## Current Safety State

The current `main` branch is a Vite React frontend mock dashboard.

The following are not implemented:

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

## Excluded Risk Areas For Phase 1

- Live orders
- Order cancellation
- Order amendment
- Realtime trading decisions
- Strategy automation
- Worker orchestration
- Browser-held broker secrets

