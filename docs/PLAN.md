# Development Plan

## Current Phase

The current project is a Vite React frontend mock dashboard.

## Phase 1: FastAPI Read-only Account Foundation

Scope:

- FastAPI backend skeleton
- Health endpoint
- Account identifier lookup structure
- Cash response schema
- Portfolio response schema
- Holdings response schema
- Performance response schema
- Mock mode by default
- Kiwoom read-only adapter interface
- Server-side token handling plan
- Frontend HTTP adapter plan for FastAPI `/api/*`

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

Do not copy or cherry-pick in the planning phase. Actual implementation must happen in a separate task.

## Later Phases

### Phase 2: Kiwoom Read-only Validation

- Validate mock mode behavior.
- Validate missing live credential errors.
- Test read-only Kiwoom account APIs only after credentials are configured server-side.

### Phase 3: Realtime Gateway

- Server-side realtime gateway only.
- No browser-direct Kiwoom WebSocket.

### Phase 4: Strategy and Risk

- Strategy Worker and Risk Manager design.
- No live order execution until risk gates exist.

### Phase 5: Order Worker Review

- Separate future review.
- Live trading remains blocked until explicitly approved.

