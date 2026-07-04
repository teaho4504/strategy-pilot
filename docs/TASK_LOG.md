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

No FastAPI implementation has been performed in this task. This log only prepares the documentation baseline for the next implementation step.

