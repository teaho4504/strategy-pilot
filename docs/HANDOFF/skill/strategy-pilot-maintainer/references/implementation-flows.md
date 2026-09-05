# End-to-End Implementation Flows

## Table of contents

1. Authentication
2. Account and portfolio
3. Market rankings and candles
4. Condition search and realtime data
5. Strategy builder and observation
6. Risk, orders, and reconciliation
7. Analytics
8. Dashboard navigation

## 1. Authentication

```text
LoginScreen
  -> GET /api/auth/kiwoom/profiles with X-Dashboard-Pin
  -> backend reads safe profile metadata from kiwoomcli settings
  -> user selects a profile
  -> POST /api/auth/kiwoom/profile-login
  -> backend reads App Key/Secret from macOS Keychain
  -> TokenManager POSTs /oauth2/token server-side
  -> KiwoomSessionManager creates an opaque dashboard session
  -> AuthProvider stores only the temporary dashboard session in sessionStorage
  -> protected React Query requests attach Authorization: Bearer <dashboard-session>
```

Frontend files: `src/auth/LoginScreen.tsx`, `src/auth/AuthProvider.tsx`, `src/services/apiClient.ts`  
Backend files: `backend/app/api/auth.py`, `backend/app/services/kiwoom_cli_profile.py`, `backend/app/services/token_manager.py`, `backend/app/services/kiwoom_session.py`

The browser must never receive the broker App Key, Secret Key, or broker token. Logout revokes the backend session and clears React Query caches.

## 2. Account and portfolio

| UI | Frontend call | FastAPI | Service | Kiwoom TR |
|---|---|---|---|---|
| Home portfolio summary | account/portfolio helpers | `/api/account/portfolio` and US account routes | `account_service.py`, `us_account_service.py` | `ust21110`, `ust21120`, `ust21070` |
| Cash/orderable context | US cash | `/api/us/account/cash` | `get_cash()` | `ust21110` |
| Valuation | US valuation | `/api/us/account/valuation` | `get_valuation()` | `ust21120` |
| Holdings | US holdings | `/api/us/account/holdings` | `get_holdings()` | `ust21070` |
| Realized P/L | analytics queries | `/api/us/account/realized-pnl` | `get_realized_pnl()` | `ust21630` |
| Period/daily return | analytics queries | period/daily return routes | mapper and date normalization | `ust21650`, `usa21670` |
| Fill history | analytics/order state | `/api/us/account/order-fills` | continuation-safe merge | `ust21510` |

Backend mappers normalize broker field variants into stable schemas. Missing/no-data responses must remain explicit; they must not fall back to mock values.

## 3. Market rankings and candles

```text
Quotes page tab
  -> readonlyApiClient.usRanking(type)
  -> GET /api/market/rankings/us/{type}
  -> MarketRankingService
  -> read-only HTTP transport
  -> map result_list to MarketRankingResponse
  -> React Query renders loading/error/rows
```

Ranking contracts: `realtime` -> `usa01980`, `change-rate` -> `usa20910`, `volume` -> `usa20530`, `price-spike` -> `usa20930`.

Candle backend contracts: minute `usa06011`, day `usa06012`, week `usa06013`, month `usa06014`.

The chart backend supports strategy calculations even when the dashboard does not render a full chart UI. Candle rows must be sorted by broker timestamp and duplicate timestamps handled conservatively.

## 4. Condition search and realtime data

```text
Strategy ON / selected condition sequence
  -> usa20280 list conditions (GCNSRLST)
  -> usa20281 one-shot search when required
  -> usa20290 realtime registration (GCNSRREQ, search_type=1)
  -> candidate enter/leave events update the condition cache
  -> strategy runner evaluates each connected candidate
Strategy OFF / session change
  -> usa20291 clear registration (GCNSRCLR)
```

Relevant backend: `us_condition_service.py`, `kiwoom_websocket.py`, provider request builders.

```text
Candidate/held symbols
  -> FE tick + FT orderbook registration
  -> realtime_quote_service maps and caches events
  -> SQLite realtime_quote_events stores bounded history
  -> /api/market/us/realtime-window reports fresh/stale/missing coverage
  -> Strategies UI shows observation quality
```

Reconnect uses bounded exponential backoff and repeats login plus registration. A stale quote never becomes an order authorization.

## 5. Strategy builder and observation

```text
StrategyBuilder page
  -> fetch available Kiwoom condition sequences
  -> user composes strategy blocks/config
  -> POST /api/market/us/strategy-builders
  -> StrategyBuilderService validates and stores configuration
  -> Strategies page lists each builder and toggles it independently
  -> condition service supplies multiple candidates
  -> MarketRankingService loads candles/quotes
  -> Python strategy evaluator produces criteria and blocked reasons
  -> observation runner stores a sanitized snapshot/event
  -> Strategies page renders waiting/ready reasons and statistics
```

Implemented Python strategies:

- `US_5M_TREND_PULLBACK`: EMA/VWAP/ATR, trend, impulse, pullback, reversal, spread, time and risk criteria.
- `US_1M_VOLUME_BREAKOUT`: VWAP/EMA/ATR, recent-high breakout, relative volume, candle shape, spread, chase prevention and time criteria.

Observation mode never reserves capital, calls order precheck, submits orders, or runs automatic exit.

## 6. Risk, orders, and reconciliation

The code path exists but is fail-closed by default:

```text
entry-ready strategy decision
  -> runtime/order policy checks
  -> current session and fresh FE/FT checks
  -> capital allocator and persisted reservation checks
  -> usa10100 common-stock/reference-price check
  -> ust31490 orderable quantity check
  -> ust21070 holdings + ust21050/ust21510 unresolved-order checks
  -> runtime lock check
  -> only then ust20000 or ust20001 transport
  -> response recorded as submitted, not filled
  -> F4/F5 and REST reconciliation confirm partial/full/cancel/reject state
  -> allocation and analytics update only from confirmed state
```

Core files: `us_order_service.py`, `us_order_state_monitor.py`, `capital_allocator.py`, `allocation_store.py`, `order_recovery.py`, `sqlite_store.py`.

The current safe local launcher forces read-only/order-disabled unless its explicit live-order switch is deliberately set. The runtime lock is a separate gate and must remain closed during ordinary development.

## 7. Analytics

```text
confirmed/sanitized order and event records
  -> SQLite order/event/allocation tables
  -> /api/us/analytics/strategy-pnl and /api/us/orders
  -> Analytics page
  -> totals, successful-order count, strategy grouping, recent events
```

Analytics must not infer fills from an accepted order response. Missing reconciliation produces incomplete analytics and must be labeled accordingly.

## 8. Dashboard navigation

| Route | Navigation label | Purpose | Main interaction |
|---|---|---|---|
| `/` | Home | Account valuation, holdings and active strategy summary | Inspect; no global order switch |
| `/quotes` | Quotes | US ranking lists | Select ranking tab and symbol context |
| `/strategies` | Strategies | Strategy state, conditions, observation quality, diagnostics | Select builder; toggle strategy/observation according to policy |
| `/strategies/builder` | Builder | Create strategy configuration | Compose blocks and save |
| `/analytics` | Analytics | Realized P/L and strategy/event history | Compare strategy outcomes |
| `/settings` | Settings | Safe runtime/order configuration status | Inspect blockers and session state |
| `/orders` | Redirect only | Removed manual order screen | Redirects to `/strategies` |
