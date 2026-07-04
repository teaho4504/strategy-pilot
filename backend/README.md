# Strategy Pilot Backend

FastAPI read-only backend for account and dashboard data.

## Current status

- Implemented: mock mode HTTP APIs for account, cash, portfolio, holdings, performance, and watchlist.
- Implemented: server-side Kiwoom REST adapter structure for `au10001`, `ka00001`, `kt00001`, `kt00004`, `kt00005`, and `ka10085`.
- Not implemented: order placement, order amendment, order cancellation, WebSocket realtime ingestion, worker processes, and live trading.

Default mode is always `KIWOOM_MODE=mock`.

## Run locally

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

## Test APIs

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/kiwoom/status
curl http://127.0.0.1:8000/api/accounts
curl http://127.0.0.1:8000/api/account/cash
curl http://127.0.0.1:8000/api/account/portfolio
curl http://127.0.0.1:8000/api/account/performance
curl http://127.0.0.1:8000/api/account/holdings
curl http://127.0.0.1:8000/api/market/watchlist
```

## Local live read-only verification

Run this only after mock tests pass and only from a local backend environment.

Prerequisites:

- Create `backend/.env` from `backend/.env.example`.
- Put Kiwoom credentials only in `backend/.env`.
- Do not paste credentials into README, shell history notes, frontend code, or Git-tracked files.
- Keep orders disabled.

Required environment values:

```text
KIWOOM_MODE=live
KIWOOM_READ_ONLY=true
KIWOOM_ENABLE_ORDER=false
KIWOOM_LIVE_VERIFY_CONFIRM=I_UNDERSTAND_READ_ONLY
```

Verification command from the repository root:

```bash
PYTHONPATH=backend python3 backend/scripts/verify_live_readonly.py
```

The script loads `backend/.env` before checking the safety guard. You do not need to export these values in the shell when they are present in `backend/.env`. If you set them in a shell instead, use `export`; plain `KEY=value` assignments are not inherited by Python child processes.

Verification order:

1. `au10001`: access token issue
2. `ka00001`: account lookup
3. `kt00001`: cash lookup
4. `kt00004`: account valuation lookup
5. `kt00005`: holdings lookup
6. `ka10085`: account performance lookup

The script prints only mode, read-only/order-disabled state, success/failure, and schema key lists. It must not print tokens, app keys, secrets, account numbers, balances, stock names, or stock codes.

For `au10001`, the backend accepts Kiwoom's `token` field as the access token and keeps `access_token` only as a compatibility fallback. If Kiwoom returns `return_code` other than `0`, the verifier prints only the TR ID, error type, HTTP status when available, and return code. It does not print the raw response body.

Do not save raw live responses in Git. If temporary troubleshooting logs are absolutely necessary, keep them under `/tmp` or another Git-ignored local path and remove them after verification.

## Safety rules

- Broker credentials must only exist in `backend/.env`.
- Do not use frontend-exposed environment variables for broker credentials.
- `KIWOOM_READ_ONLY=true` and `KIWOOM_ENABLE_ORDER=false` are the required defaults.
- This backend does not expose order endpoints.
- Status APIs must not return tokens, app keys, secrets, account numbers, or masked forms of those values.
- The live verification script is blocked unless `KIWOOM_LIVE_VERIFY_CONFIRM=I_UNDERSTAND_READ_ONLY` is set.

## Supported Kiwoom read-only TRs

- `au10001`: OAuth access token, used only by the backend token manager.
- `ka00001`: account identifier lookup.
- `kt00001`: cash and withdrawable/orderable amount lookup, default `qry_tp=2`.
- `kt00004`: account valuation lookup, default `qry_tp=1`, `dmst_stex_tp=KRX`.
- `kt00005`: holdings lookup, default `dmst_stex_tp=KRX`.
- `ka10085`: account performance lookup, default `stex_tp=0`.
