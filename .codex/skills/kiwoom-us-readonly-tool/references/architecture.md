# Architecture and safety boundary

## Runtime

- Frontend: Vite + React + TypeScript in repository root `src/`.
- Backend: separate FastAPI process in `backend/`.
- Local development: Vite proxies `/api` to `127.0.0.1:8000`.
- Production frontend: Vercel-compatible static Vite build.
- Backend hosting: separate server; never place Kiwoom secrets in Vercel frontend variables.

## Allowed

- OAuth token issuance on the backend.
- Read-only price, ranking, chart, condition-search, account, balance, fill-history, and PnL requests.
- Read-only WebSocket quote and condition observation.
- Strategy calculation, diagnostics, cataloging, and backtesting without order submission.

## Blocked

- Buy, sell, amend, cancel, liquidation, and exchange-request network calls.
- Browser-direct Kiwoom requests.
- Secrets in frontend bundles, URLs, logs, generated fixtures, or catalog output.
