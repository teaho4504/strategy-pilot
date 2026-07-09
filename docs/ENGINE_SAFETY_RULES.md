# Engine Safety Rules

## Current Scope

The trading engine is still paper-only. It is allowed to ingest mock events,
generate strategy signals, run risk checks, create paper fills, and write a
local paper journal.

It must not:

- Call Kiwoom live REST APIs.
- Open Kiwoom live WebSocket connections.
- Place, amend, or cancel orders.
- Add FastAPI order endpoints.
- Commit local SQLite files, secrets, tokens, or account identifiers.

## File And Data Safety

Ignored local artifacts:

```text
.env
.env.local
backend/.env
deploy/backend/.env
*.sqlite3
backend/data/*.sqlite3
```

`backend/data/.gitkeep` may be committed to keep the data directory available,
but actual DB files must remain local runtime artifacts.

## DB Path Rule

The engine supports `TRADING_ENGINE_DB_PATH`.

Default:

```text
backend/data/trading_engine.sqlite3
```

Tests must use temporary paths. Production or long-running paper workers should
set an explicit path instead of relying on the current working directory.

## Time Rule

The engine records enough time context for multi-market journaling:

- UTC event time.
- KST display time.
- US market date.
- US session classification skeleton:
  - `premarket`
  - `regular`
  - `afterhours`
  - `closed`

US holiday calendars and early-close handling are future work.

## Entry Risk Blocks

New entries must be blocked when any of the following is true:

- Kill Switch is enabled.
- Strategy is paused.
- Daily loss limit has been reached.
- Entry amount exceeds per-symbol max.
- Open position count is at or above max positions.
- Daily entry count is at or above max entries.
- Same-symbol re-entry cooldown is active.

## Order Safety

The Kiwoom REST provider skeleton is fail-closed:

- `live_provider_enabled=false` by default.
- `order_enabled=false` by default.
- REST calls are blocked before transport use when live provider is disabled.
- WebSocket connect is blocked when live provider is disabled.
- Order helper methods raise `RuntimeError`.
- Order TR codes may exist only as documentation constants.

Actual order execution requires a separate architecture review, risk approval,
audit log design, and explicit implementation request.
