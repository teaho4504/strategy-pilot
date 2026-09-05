# Architecture and Data

## Runtime map

```text
Browser (Vite React)
  | dashboard PIN -> profile selection
  | opaque backend session Bearer token
  v
FastAPI backend
  |-- auth/session boundary
  |-- account and market read-only services
  |-- condition and quote WebSocket monitors
  |-- observation/order runner
  |-- risk and recovery services
  v
Python trading_engine
  |-- Kiwoom TR inventory, request builders, mappers
  |-- strategy indicators and decisions
  |-- capital allocation and persistence
  v
SQLite local runtime journal

FastAPI -> Kiwoom HTTPS REST
FastAPI -> Kiwoom WSS (conditions, FE/FT; F4/F5 only when eligible)
```

## Technology

| Layer | Technology |
|---|---|
| Frontend | Vite 5, React 18, TypeScript, React Router, TanStack React Query, Tailwind CSS, Radix UI, Lucide icons |
| Backend | Python 3, FastAPI, Uvicorn, Pydantic, httpx, PyJWT, websockets, keyring |
| Trading logic | Python dataclasses and pure indicator/decision functions |
| Persistence | SQLite with explicit migrations and local DB path |
| Tests | pytest, Vitest, Testing Library, TypeScript compiler, Vite build |
| Local operations | Bash launcher, macOS `screen`, `caffeinate`, Keychain through `kiwoomcli` |

## Important directories

- `src/`: dashboard, auth provider, API client, types and frontend tests.
- `backend/app/api/`: FastAPI transport boundary.
- `backend/app/services/`: orchestration, session, broker calls, condition/realtime/order state.
- `backend/trading_engine/providers/kiwoom_us/`: official US TR inventory, builders, schemas, transport and mapping.
- `backend/trading_engine/strategies/`: reusable real-time/backtest strategy decisions.
- `backend/trading_engine/risk/`: capital allocation and recovery state.
- `backend/trading_engine/storage/`: SQLite schema and persistence.
- `backend/tests/`, `backend/trading_engine/tests/`: network-free contract and behavior tests.
- `docs/`: plans, guardrails, task log and this handoff bundle.

## TR inventory by purpose

| Purpose | TR/channel |
|---|---|
| Token | `au10001` semantics at `/oauth2/token` |
| Condition list/search/realtime/clear | `usa20280`, `usa20281`, `usa20290`, `usa20291` |
| Ranking | `usa01980`, `usa20510`, `usa20530`, `usa20910`, `usa20930` |
| Stock metadata | `usa10098`, `usa10099`, `usa10100` |
| Candles | `usa06010` through `usa06016` |
| Realtime tick/orderbook | `FE`, `FT` |
| Order confirmation/fill stream | `F4`, `F5` |
| Cash/valuation/holdings | `ust21110`, `ust21120`, `ust21070` |
| Open orders/fills | `ust21050`, `ust21150`, `ust21510` |
| P/L | `ust21630`, `ust21650`, `usa21670` |
| Read-only orderability | `ust31490` |
| Buy/sell/amend/cancel | `ust20000`, `ust20001`, `ust20002`, `ust20003` |

Do not infer endpoint or payload fields from the TR name. Check the current official Kiwoom specification and local contract tests before changing a request.

## State ownership

| State | Owner | Persistence |
|---|---|---|
| Broker App Key/Secret | macOS Keychain or server-only environment | Never repository/browser |
| Broker access token | backend session/token manager | Memory or CLI token store; never logs/UI |
| Dashboard session | backend session manager + browser sessionStorage | Opaque temporary token only |
| Condition candidates | condition service | Process memory plus sanitized events |
| FE/FT latest quotes | quote monitor | Memory plus SQLite event window |
| Strategy builder configs | strategy builder service | Local service storage/config path |
| Observation snapshot | auto-trade runner/order service | Memory; changed states journaled safely |
| Allocation reservations | allocation store | SQLite, survives restart |
| Order state | order service/monitor | SQLite plus broker reconciliation |
| Runtime lock | local lock file | Must survive ordinary restart behavior |
| Dashboard PIN | `~/.strategy-pilot/dashboard.pin` | Mode 600, never repository/USB archive |

## SQLite data rules

The migration includes condition events, market events, realtime quote/orderbook events, strategy signals, risk blocks and US strategy decisions. Additional order/allocation tables are created by the order/risk persistence modules.

- Use `TRADING_ENGINE_DB_PATH`; tests use temporary paths.
- Never commit `*.sqlite3` or copy production DBs as source code.
- Never store tokens, App Key, Secret Key or complete account identifiers.
- Store safe broker result codes and normalized fields, not unrestricted raw responses.
- Preserve ET timestamp and US market date for strategy decisions.

## Time and freshness

- Trading decisions use `America/New_York` through `zoneinfo`, which handles DST.
- Display/audit may include KST separately.
- FE/FT data older than the configured freshness threshold is stale.
- A stale/missing quote blocks confidence and entry; it never becomes a zero/default price.
- Candle order is normalized by event timestamp before indicators are calculated.
