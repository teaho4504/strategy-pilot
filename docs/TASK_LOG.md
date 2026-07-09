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

## 2026-07-05: au10001 Token Handling Safety Fix Prepared

### Reason

- Local live read-only verification surfaced that the `au10001` token response may use Kiwoom's documented `token` field rather than only an `access_token` field.
- The live verification failure printer also needed to avoid masking the original failure with a secondary exception.

### Changes

- Treat `token` as the primary `au10001` access token field.
- Keep `access_token` only as a compatibility fallback.
- Handle Kiwoom `return_code != 0` token responses as safe backend errors without logging raw response bodies.
- Print verification failures as minimal fields: TR ID, status, error type, HTTP status when available, and return code when available.

### Boundaries

- No actual Kiwoom API call was made for this fix.
- No order, WebSocket, Worker, AWS, Vercel, or frontend code was added.

## 2026-07-05: au10001 Request Contract Diagnostics Prepared

### Reason

- Live read-only verification received a Kiwoom `return_code=3` for `au10001`, which indicates an API ID contract problem.
- The local environment and guard checks were already passing, so the next fix focused on request construction and safe diagnostics rather than credentials or live retries.

### Changes

- Centralized the token API ID as `au10001` and the token path as `/oauth2/token`.
- Validate token request path before issuing the token HTTP request. The earlier `api-id` token header assumption was later superseded by the official OAuth example.
- Treat blank `KIWOOM_TOKEN_URL` as unset and fall back to `KIWOOM_BASE_URL + /oauth2/token`.
- Add safe token request diagnostics that show only method, path, boolean configuration presence, and API ID match state.

### Boundaries

- No actual Kiwoom API call was made for this diagnostic fix.
- No raw request body, raw response body, app key, secret key, token, or account number is logged.

## 2026-07-05: au10001 Wire Request Diagnostics Prepared

### Reason

- `return_code=3` persisted after IP allowlist changes and after confirming the configured token path and API ID.
- The next diagnostic needed to verify the exact request structure passed to `httpx`, not just high-level settings.

### Changes

- Build the OAuth request in one place before passing it to `httpx.AsyncClient.post`.
- Initially tested `api-id: au10001` with `Content-Type: application/json;charset=UTF-8` in the token request headers; this was later superseded by the official OAuth example, which omits `api-id`.
- Validate token request body keys as `grant_type`, `appkey`, and `secretkey`.
- Print safe wire diagnostics: URL path, wire API ID, header names, body key names, and boolean presence/match checks.
- Print sanitized `return_msg` when available without raw JSON or credential values.

### Authorization Header Decision

- The token issuance request still does not send an `Authorization` header.
- No empty Bearer token is added by guesswork; this requires official Kiwoom confirmation before changing.

### Boundaries

- No actual Kiwoom API call was made for this fix.
- No frontend, AWS, Vercel, Docker, order, WebSocket, or Worker code was changed.

## 2026-07-05: au10001 OAuth Header Contract Corrected

### Reason

- The official Kiwoom OAuth access-token Python example shows `au10001` token issuance without an `api-id` header.
- The previous diagnostic request included `api-id: au10001`, which likely caused Kiwoom `return_code=3` for a token request.

### Changes

- Token issuance now sends only `Content-Type: application/json;charset=UTF-8` as the OAuth request header.
- Token issuance explicitly rejects `api-id` and `Authorization` headers.
- Token issuance still validates body keys as `grant_type`, `appkey`, and `secretkey`.
- Regular account TR calls continue to send `api-id`, `Authorization: Bearer {token}`, `cont-yn`, and `next-key`.

### Boundaries

- No actual Kiwoom API call was made for this fix.
- No frontend, AWS, Vercel, Docker, order, WebSocket, or Worker code was changed.

## 2026-07-05: Phase 1 Live Read-only Validation Passed And Mapper Refinement Started

### Facts

- Local live read-only verification passed from `au10001` through `ka10085`.
- The verification output included only schema key names and safe status fields.
- No token, account number, cash balance, holding name, holding symbol, or raw JSON response was stored in the repository.

### Mapper Refinement

- `kt00004` portfolio mapping now accepts live amount suffix fallbacks such as `tdy_lspft_amt` and `lspft_amt`.
- Kiwoom client mock responses were adjusted toward Kiwoom-like read-only TR schema keys.
- Regression tests now cover live-style mapper fallbacks, numeric string parsing, empty holdings lists, and secret-safe validation errors.

### Boundaries

- No actual Kiwoom API call was made during mapper refinement.
- No API response contract breaking change was introduced.
- No frontend, AWS, Vercel, Docker, order, WebSocket, or Worker code was changed.

## 2026-07-09: Kiwoom REST Provider Skeleton Started

### Reference

- Official reference repository: `Kiwoom-Securities/Kiwoom-REST-API`.
- The repository was used only to understand structure and protocol boundaries:
  CLI/keyring-first credentials, regular TR headers, separated OAuth handling,
  WebSocket LOGIN and REG/REMOVE packet shape, and the existence of order
  examples that must not be executed.
- No official repository code was copied into this project.

### Added

- `backend/trading_engine/providers/kiwoom_rest/` skeleton package.
- Read-only REST client skeleton with live provider disabled by default.
- WebSocket skeleton with connect blocked by default.
- Payload adapter functions for quote, order book, and condition payloads.
- Safety helpers for order blocking and secret redaction.

### Boundaries

- No actual HTTP or WebSocket call is made.
- No Kiwoom key, token, account number, or `.env` value is added.
- No order endpoint or executable order method is added.
- Official order samples remain excluded until a separate live-order safety
  architecture is approved.
