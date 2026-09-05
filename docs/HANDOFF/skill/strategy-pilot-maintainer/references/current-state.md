# Current State

## Current Windows verification

Verified on 2026-09-05 KST from the portable Windows workspace:

- The workspace has no Git metadata; use the verified transfer archive as the source overlay and restore Git history separately.
- The saved kiwoomcli real profile creates a backend-only read-only session without exposing credentials to the browser.
- Official usa06011 chart requests return 1-minute, 5-minute, and 60-minute scopes.
- Observed usa06011 timestamps with hours above 23 are parsed as Kiwoom US business-date plus extended KST hours; parsing failures and stale candles fail closed.
- The liquidity dashboard separates browser-to-FastAPI WebSocket health from the broker FE/FT observation state.
- Advisory BUY_WATCH or SELL_WATCH is eligible only while the US session is active, FE/FT is connected and no older than 10 seconds, and all three official chart timeframes are present.
- Off-hours, stale, reconnecting, missing, or degraded evidence forces WATCH; executionAuthorized remains false.
- Latest verification: 385 backend/trading-engine tests and 22 frontend tests passed; production build passed.

Last documentation audit: 2026-08-08  
Repository: `strategy-pilot`  
Audited local branch: `feature/kiwoom-us-tr-skeleton-local`  
Audited HEAD: `a6689d2`

## Important qualification

The audited worktree contains a large amount of uncommitted and untracked implementation work. The remote branch and `a6689d2` do not contain the complete current application. A new machine must restore the safe worktree overlay described in `new-device-setup.md`; cloning Git alone is insufficient.

“Implemented” below means code and automated tests exist. It does not automatically mean production broker behavior has been fully verified.

## Feature status

| Area | Status | What exists | Remaining risk |
|---|---|---|---|
| Vite dashboard shell | Implemented | Mobile-first React routes for Home, Quotes, Strategies, Builder, Analytics, Settings | UX and performance need continued observation on mobile |
| Dashboard authentication | Implemented | PIN-protected CLI profile listing, backend-issued temporary session, session restore/logout | Depends on Kiwoom token endpoint availability |
| Secret handling | Implemented with local dependency | Browser never receives App Key/Secret; CLI profile reads macOS Keychain | Keychain must be configured separately on each Mac |
| Token issuance | Implemented, currently externally blocked at last check | Official `/oauth2/token`, timeout, safe errors, redirect downgrade protection | Last observed response was HTTPS 302 to an HTTP start page; do not bypass |
| US account read-only data | Implemented | Cash, valuation, holdings, realized P/L, period return, daily return, fills | Production response variants still need ongoing mapper audits |
| US rankings | Implemented | Realtime rank, change rate, volume, price-spike endpoints | Data depends on a valid broker session and market availability |
| US chart backend | Implemented | Minute/day/week/month request and mapping | Chart UI intentionally not a priority; strategy calculations may use candles |
| Kiwoom condition search | Implemented | List, one-shot, realtime register, realtime clear through WebSocket | Requires Hero Global condition definitions and valid session |
| FE/FT quote stream | Implemented and previously observed | Tick/orderbook cache, reconnect/backoff, resubscribe, freshness metrics | Revalidate after migration and token/session restoration |
| F4/F5 order-state stream | Scaffolded and guarded | Mapping, monitor preflight, reconnect support | Must not connect without an existing submitted reservation; production ordering needs controlled validation |
| Strategy calculations | Implemented | 1-minute volume breakout and 5-minute trend pullback indicators/criteria | Strategy profitability is not established; backtest dataset and tuning are incomplete |
| Strategy builder | Implemented as configuration UI | Create/list builder configurations and associate Kiwoom condition sequence | Generated builders are not proof of profitability or safe live execution |
| Observation runner | Implemented | Five-second read-only candidate evaluation, snapshots, deduplicated event journal, stats | Requires session and market data; never authorizes orders by itself |
| Capital allocation | Implemented | Four-symbol/two-tranche policy, reservations, restart persistence | Broker cash/positions and internal state must reconcile before any live use |
| Order precheck | Implemented | Common-stock, quote, orderability, holdings/fills, policy and lock checks | Production edge cases remain; passing precheck is not a fill |
| Buy/sell order transport | Present but default blocked | `ust20000`/`ust20001` paths, safe caps and confirmations | Not considered production-complete; real execution remains disabled by default |
| Amend/cancel | Inventory/scaffolding only | `ust20002`/`ust20003` identified | No general production workflow should rely on these yet |
| Automatic exit/liquidation | Partially implemented and guarded | Take-profit/stop evaluation, sell reconciliation, liquidation planning | End-to-end production recovery and failure handling require controlled validation |
| SQLite journaling | Implemented | Realtime events, strategy decisions, risk blocks, orders/reservations/events | DB files are local runtime data and must never be committed/transferred casually |
| Analytics | Implemented from local/broker-derived records | Strategy P/L, order/event summaries | Metrics are only as complete as fill reconciliation and stored history |
| Remote/mobile access | Local tooling implemented | Loopback/LAN bind option, PIN, IP allowlist, rate limits, CORS, `caffeinate` | Public-IP exposure is not an approved deployment design |

## Last known verification

- Backend full test suite: 345 passed, one dependency deprecation warning.
- Frontend suite after token-error UX change: 11 passed.
- TypeScript check and Vite production build passed.
- Runtime order lock was present and live orders were disabled.
- The Kiwoom token endpoint was last observed returning an unsafe redirect, so broker-authenticated runtime checks could not continue.

Re-run all verification on the new machine. Do not use these historical results as proof that the migrated environment works.
