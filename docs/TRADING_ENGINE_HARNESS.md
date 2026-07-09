# Trading Engine Harness

## Current State

The trading engine is a paper-mode worker foundation inside the existing
`strategy-pilot` repository. It is not a separate project and it is not a live
trading system.

Implemented:

- Mock condition-search event ingestion.
- Mock market tick ingestion.
- Strategy signal generation.
- Risk checks before paper entries.
- Paper broker fills only.
- SQLite paper journal storage.
- Kiwoom REST/WebSocket provider skeleton with live calls blocked by default.

Not implemented:

- Kiwoom live WebSocket connection.
- Kiwoom live condition-search subscription.
- Kiwoom live order book or fill ingestion.
- Live orders, amend, or cancel.
- Dashboard engine-control mutation endpoints.

## Kiwoom REST GitHub Reference

The official Kiwoom REST API GitHub repository was used only as a reference for
structure and protocol boundaries:

- CLI/keyring-first credential direction.
- `.env` as a fallback path, not the preferred local secret store.
- REST TR header structure for regular read-only TR requests.
- OAuth token issuance being separate from regular TR calls.
- WebSocket LOGIN and REG/REMOVE packet structure.
- The presence of official order examples that must not be executed by this
  project at this phase.

No official repository code was copied into `strategy-pilot`.

## Safety Defaults

```text
mode=paper
orderEnabled=false
liveProvider=false
```

The provider skeleton is designed to fail closed:

- REST read-only requests call `assert_live_allowed()` before using any
  transport.
- WebSocket `connect()` calls `assert_live_allowed()` before any transport is
  implemented.
- Order helper methods raise `RuntimeError`.
- Order TR constants are documented but not connected to a client path.
- Secret-like fields are sanitized before diagnostic output.

## Next Allowed Step

The next safe integration step is still read-only:

1. Confirm official realtime payload schemas.
2. Add fixture tests for each payload type.
3. Connect only paper-mode event ingestion.
4. Keep order execution unavailable.
