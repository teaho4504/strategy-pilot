# Development Plan

## Current Phase

The current project is a Vite React frontend mock dashboard.

## Phase 1: FastAPI Read-only Account Foundation

Status: in progress.

Scope:

- FastAPI backend skeleton. Implemented.
- Health endpoint. Implemented.
- Account identifier lookup structure. Implemented as read-only backend service.
- Cash response schema. Implemented.
- Portfolio response schema. Implemented.
- Holdings response schema. Implemented.
- Performance response schema. Implemented.
- Mock mode by default. Implemented.
- Kiwoom read-only adapter interface. Implemented for selected account TRs.
- Server-side token handling plan. Implemented as backend-only token manager structure.
- Frontend HTTP adapter plan for FastAPI `/api/*`. Planned; frontend still uses the existing mock adapter.

Supported Phase 1 Kiwoom TRs:

- `au10001`: backend-only OAuth token issue.
- `ka00001`: account lookup.
- `kt00001`: cash lookup.
- `kt00004`: account valuation lookup.
- `kt00005`: holdings lookup.
- `ka10085`: account performance lookup.

Explicitly out of scope:

- Live order features
- Order placement
- Order amendment
- Order cancellation
- WebSocket
- Worker
- AWS deployment
- Docker deployment
- Vercel config changes
- UI redesign
- Package changes unrelated to backend setup
- `ka01690` daily balance performance
- order TRs
- unsettled/fill query TRs
- realtime WebSocket TRs
- quote, order book, and chart TRs

## Phase 1 Source Material

Use `feature/backend-account-integration` only as reference for selected backend read-only files.

Potential reuse list:

- `backend/app/core/config.py`
- `backend/app/services/token_manager.py`
- `backend/app/services/kiwoom_client.py`
- `backend/app/api/health.py`
- `backend/app/api/account.py`
- `backend/app/api/kiwoom.py`
- `backend/app/schemas/*`
- `backend/app/services/account_service.py`
- `backend/app/services/balance_service.py`
- `backend/app/services/performance_service.py`
- `backend/app/services/market_service.py`
- `backend/.env.example`
- `backend/requirements.txt`
- `backend/README.md`

Do not merge the branch wholesale. Phase 1 implementation should remain limited to read-only backend behavior.

## Later Phases

### Phase 2: Kiwoom Read-only Validation

- Prepare local live read-only verification. In progress on `feature/fastapi-readonly-account`.
- Validate mock mode behavior.
- Validate missing live credential errors.
- Test read-only Kiwoom account APIs only after credentials are configured server-side.
- Require explicit `KIWOOM_LIVE_VERIFY_CONFIRM=I_UNDERSTAND_READ_ONLY` before live verification.
- Print only schema keys and success/failure, never live response values.

### Phase 3: Realtime Gateway

- Server-side realtime gateway only.
- No browser-direct Kiwoom WebSocket.

### Phase 4: Strategy and Risk

- Strategy Worker and Risk Manager design.
- No live order execution until risk gates exist.

### Phase 5: Order Worker Review

- Separate future review.
- Live trading remains blocked until explicitly approved.
