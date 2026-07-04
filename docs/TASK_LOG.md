# Task Log

## 2026-07-04: Architecture Baseline Correction

### Corrected Facts

- Repository: `teaho4504/strategy-pilot`
- Production branch: `main`
- Actual production frontend baseline is Vite root application.
- `main` package.json is Vite-based.
- `main` has no Next.js `apps/web` structure.
- Vercel is understood to deploy the Vite root frontend.

### Corrected Assumption

Previous Next.js / `apps/web` / App Router assumptions were not aligned with `origin/main`.

Current temporary architecture baseline:

```text
Vercel
  -> Vite React Dashboard

AWS or equivalent backend host
  -> FastAPI read-only backend
  -> Kiwoom REST Account APIs

Future
  -> Realtime Gateway
  -> Strategy Worker
  -> Risk Manager
  -> Order Worker
```

### Existing Branch Analysis Summary

Reusable candidate branch:

```text
feature/backend-account-integration
```

Use only selected read-only backend files from that branch. Full branch merge is prohibited.

Reusable candidates:

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

Excluded from Phase 1:

- `vercel.json`
- `deploy/aws/lightsail/*`
- `backend/Dockerfile`
- `backend/app/api/orders.py`
- `docs/VERCEL.md` hardcoded IP content
- full `README.md` overwrite
- broad frontend UI changes
- `src/App.tsx` broad changes
- `vite.config.ts` changes

### Phase 1 Status

The documentation baseline prepared the next implementation step.

## 2026-07-04: FastAPI Read-only Backend Foundation Started

### Facts

- Work is on `feature/fastapi-readonly-account`.
- A new `backend/` FastAPI application has been added from the harness baseline.
- The implementation is intentionally read-only and does not include order endpoints.
- Default mode remains `KIWOOM_MODE=mock`.

### Implemented So Far

- `/api/health`
- `/api/kiwoom/status`
- `/api/accounts`
- `/api/account/cash`
- `/api/account/portfolio`
- `/api/account/performance`
- `/api/account/holdings`
- `/api/market/watchlist`
- Backend-only Kiwoom token manager structure.
- Backend-only Kiwoom read-only TR client structure.

### Phase 1 TR Scope

- `au10001`: OAuth token issue.
- `ka00001`: account lookup.
- `kt00001`: cash lookup.
- `kt00004`: account valuation lookup.
- `kt00005`: holdings lookup.
- `ka10085`: account performance lookup.

`ka01690`, order TRs, fill query TRs, realtime WebSocket TRs, quote/order-book/chart TRs, US stock APIs, condition-search APIs, Worker, Docker, AWS deployment, Vercel settings, and frontend UI work remain excluded.

### Still Excluded

- Frontend adapter migration.
- Vercel proxy changes.
- Docker or AWS deployment files.
- WebSocket realtime gateway.
- Strategy, risk, or order workers.
- Order placement, amendment, or cancellation APIs.

## 2026-07-04: Local Live Read-only Verification Prepared

### Added

- `backend/scripts/verify_live_readonly.py` for manual local verification.
- Explicit live verification guard: `KIWOOM_LIVE_VERIFY_CONFIRM=I_UNDERSTAND_READ_ONLY`.
- Mapper validation errors for missing expected response fields.
- Tests for blocked live verification, secret-safe output, mapper validation, and continuation handling.

### Verification Policy

- The script runs only in live/read-only/order-disabled mode.
- The script prints schema keys, success/failure, and error type only.
- It does not print live response values, account numbers, balances, stock names, stock codes, app keys, secrets, or tokens.
- It stops on the first TR failure.
