# Strategy Pilot Backend

FastAPI backend for read-only Kiwoom account and watchlist queries.

This backend is intentionally limited to account/market lookup. It does not implement order, amend, cancel, or automated trading APIs.

## Safety Rules

- Default mode is `KIWOOM_MODE=mock`.
- Kiwoom live calls are blocked unless `KIWOOM_MODE=live` is explicitly set.
- Keep `KIWOOM_APP_KEY`, `KIWOOM_SECRET_KEY`, access tokens, and full account numbers in `backend/.env` only.
- Do not put Kiwoom credentials in `VITE_*` variables.
- `.env` and `backend/.env` are ignored by Git.

## Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
npm install
npm run dev
```

Vite proxies `/api/*` to `http://localhost:8000`.

## Environment

```text
KIWOOM_MODE=mock
KIWOOM_APP_KEY=
KIWOOM_SECRET_KEY=
KIWOOM_ACCOUNT_NO=
KIWOOM_WATCHLIST=005930,000660,035420
```

Use `KIWOOM_MODE=live` only after credentials and Kiwoom API access/IP settings are ready.

## APIs

| Method | Path | Source TR |
| --- | --- | --- |
| GET | `/api/health` | backend runtime state |
| GET | `/api/accounts` | `ka00001` account number lookup |
| GET | `/api/account/portfolio` | `kt00004` + `ka10085` |
| GET | `/api/account/performance` | `ka10085` with server-side continuation |
| GET | `/api/account/cash` | `kt00001` |
| GET | `/api/account/holdings` | `kt00005` + `ka10085` |
| GET | `/api/market/watchlist` | `ka10001` REST polling |

## Official Kiwoom REST API Notes

Checked against the official Kiwoom REST API guide on `https://openapi.kiwoom.com`:

- Account category `jobTpCode=08` documents `ka00001`, `ka10085`, `kt00001`, `kt00004`, `kt00005`.
- Stock info category documents `ka10001` for code-based basic stock info including `cur_prc` and `flu_rt`.
- Common request headers include `authorization`, `cont-yn`, `next-key`, and `api-id`.
- `ka00001`, `ka10085`, `kt00001`, `kt00004`, and `kt00005` use `/api/dostk/acnt`.
- `ka10001` uses `/api/dostk/stkinfo`.

Where the official lookup TR does not provide dashboard-ready data directly, the mapper leaves conservative TODOs in code. For example, intraday equity curves require persisted snapshots because the account snapshot TRs return current account state, not a historical curve.

## Smoke Tests

Mock mode:

```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/accounts
curl http://localhost:8000/api/account/portfolio
curl http://localhost:8000/api/account/cash
curl http://localhost:8000/api/account/holdings
curl http://localhost:8000/api/account/performance
curl http://localhost:8000/api/market/watchlist
```

Live mode account lookup test:

```bash
KIWOOM_MODE=live uvicorn app.main:app --reload --port 8000
curl http://localhost:8000/api/accounts
```

The frontend should show errors if the backend is down or Kiwoom live credentials are invalid. It should not silently fall back to mock data on API failure.
