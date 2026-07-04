# Architecture Decisions

## Current Facts

Current baseline verified from `origin/main`:

- Repository: `teaho4504/strategy-pilot`
- Production branch: `main`
- Current frontend: Vite + React root application
- Current source root: `src/`
- Current build system: Vite
- Current package file: root `package.json`
- Current Vite config: `vite.config.ts`
- Current `main` has no Next.js `apps/web` structure

## Corrected Architecture Baseline

```text
Vercel
  -> Vite React Dashboard

AWS or equivalent backend host
  -> FastAPI read-only backend
  -> Kiwoom REST Account APIs

Future phases
  -> Realtime Gateway
  -> Strategy Worker
  -> Risk Manager
  -> Order Worker
```

Previous assumptions about Next.js, `apps/web`, or App Router do not match the current `strategy-pilot` `main` branch.

## Frontend Responsibilities

- Dashboard UI
- Mock dashboard state until backend is introduced
- HTTP API requests to FastAPI `/api/*`
- Future internal dashboard WebSocket client only after a server-side gateway exists

Frontend must not:

- Store Kiwoom credentials
- Call Kiwoom REST directly
- Open Kiwoom WebSocket directly
- Place, amend, or cancel orders

## Backend Responsibilities

Planned FastAPI read-only backend responsibilities:

- Health/status endpoint
- Kiwoom token handling
- Account read APIs
- Cash, holdings, portfolio, and performance response mapping
- Mock mode by default
- Future internal WebSocket gateway boundary

Backend must not include live order execution in Phase 1.

## Not Implemented

- Kiwoom realtime connection
- WebSocket gateway
- Strategy Worker
- Risk Worker
- Order Worker
- Paper Trading
- Live trading
- Live order placement, amendment, or cancellation

## Existing Backend Branch Analysis

Reusable source branch:

```text
feature/backend-account-integration
```

Selective reuse candidates:

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

Do not merge the full branch. Use it only as reference or for carefully reviewed selective file transfer in a later implementation task.

## Excluded From Phase 1

Do not bring these into Phase 1:

- `vercel.json`
- `deploy/aws/lightsail/*`
- `backend/Dockerfile`
- `backend/app/api/orders.py`
- `docs/VERCEL.md` hardcoded IP content
- Full `README.md` overwrite from backend branch
- Broad frontend UI changes
- `src/App.tsx` broad changes
- `vite.config.ts` changes

