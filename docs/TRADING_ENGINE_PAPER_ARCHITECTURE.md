# Trading Engine Paper Architecture

## Current Scope

This document describes the first paper-trading worker foundation for Strategy Pilot. It is not a live trading system.

Implemented scope:

- Mock condition-search events
- Automatic watchlist candidate management
- Mock market data events
- In-memory market cache
- Strategy signal generation
- Risk checks
- Paper broker fills
- SQLite event/fill storage
- Daily journal aggregation

Explicitly not implemented:

- Kiwoom condition-search connection
- Kiwoom realtime WebSocket connection
- Kiwoom order, amend, or cancel calls
- Dashboard control endpoints for Kill Switch
- Worker deployment
- Live trading

## Data Flow

```text
MockConditionProvider
  -> ConditionMonitor
  -> WatchlistManager
  -> SQLite condition_events

MockMarketDataProvider
  -> MarketCache
  -> SimpleConditionStrategy
  -> RiskManager
  -> PaperBroker
  -> SQLite strategy_signals / risk_blocks / paper_fills
  -> JournalService daily summary
```

## Condition Search Principle

Condition-search inclusion is only a candidate discovery event. It is never an immediate buy signal.

The engine treats `condition_entered` as:

```text
symbol enters candidate watchlist
-> wait for market data
-> evaluate strategy rules
-> run risk checks
-> optionally create paper fill
```

This preserves the separation between discovery, signal generation, risk approval, and execution.

## Realtime Data Flow

The current provider is mock-only. A future Kiwoom provider must confirm the official protocol for:

- condition list retrieval
- condition include/exclude event payloads
- realtime quote subscription message shape
- quote tick payload fields
- order book payload fields
- continuation or reconnect behavior
- subscription limits per account/session
- heartbeat/ping requirements
- IP registration and token refresh behavior

No undocumented endpoint, payload, or WebSocket frame should be guessed.

## Strategy Decision Flow

The sample strategy creates only `paper_buy_candidate` signals when all conditions pass:

- the symbol is an active/candidate watch item
- no current position is open in the sample account state
- trade volume is above a safe threshold
- change rate is within a bounded range
- bid/ask spread is within a bounded range

Other outcomes are `observe` or `no_action`. The strategy does not call any order API.

## Risk Management Flow

Before any paper fill, the risk manager checks:

- Kill Switch
- strategy pause state
- daily max virtual loss
- per-symbol max virtual entry amount
- max concurrent paper positions
- re-entry cooldown
- max daily entry count

If Kill Switch is enabled, new entry signals and paper fills are blocked and the reason is recorded.

## Paper Broker

The paper broker is completely separate from Kiwoom and only mutates local paper state:

- paper buy
- paper sell
- position quantity
- average price
- realized PnL
- fees
- slippage
- fill reason
- strategy name
- condition name

It has no Kiwoom client dependency and exposes no live order path.

## Storage

The first implementation uses SQLite under `backend/data/` by default. Storage is isolated behind `SQLiteStore` so it can later be replaced by PostgreSQL without changing strategy or broker logic.

Recorded tables:

- `condition_events`
- `market_events`
- `strategy_signals`
- `risk_blocks`
- `paper_fills`

## Mock -> Paper -> Live Gates

Mock stage:

- Use mock condition and market data providers
- Use paper broker only
- Keep order enabled false

Paper stage:

- Connect official Kiwoom realtime feeds after protocol review
- Continue using PaperBroker
- Store all signals, fills, and risk decisions
- Validate daily journal accuracy

Live stage:

- Requires a separate design review
- Requires order adapter implementation
- Requires risk guardrails update
- Requires audit logging and manual approval
- Requires `KIWOOM_ENABLE_ORDER` policy review

## Why Orders Are Disabled

Orders are disabled because the project is still validating candidate discovery, market data handling, strategy rules, risk checks, and journaling. A live order path would be unsafe until the paper loop is stable and reviewed.

The current engine defaults to:

```text
mode=paper
orderEnabled=false
liveProvider=false
```

## Why Worker And FastAPI Are Separate

FastAPI remains the read-only dashboard/control API. The trading engine must run as a long-lived Python worker because realtime ingestion and strategy loops need independent lifecycle, retries, and state handling. Browser, Vercel, and Supabase must not run trading decisions.

## Execution

From the repository root:

```bash
PYTHONPATH=backend python3 -m trading_engine.engine_main
```

Test commands:

```bash
PYTHONPYCACHEPREFIX=/tmp/strategy-pilot-pycache python3 -m compileall backend/app backend/scripts backend/trading_engine
PYTHONPATH=backend backend/.venv/bin/python -m pytest -p no:cacheprovider backend/tests backend/trading_engine/tests
```

## Future FastAPI Read-only Endpoints

Possible read-only endpoints for a later task:

- `GET /api/engine/status`
- `GET /api/engine/watchlist`
- `GET /api/engine/events`
- `GET /api/engine/journal/daily`

They must remain Supabase JWT protected and must not execute orders. Kill Switch mutation endpoints are intentionally not part of this step.
