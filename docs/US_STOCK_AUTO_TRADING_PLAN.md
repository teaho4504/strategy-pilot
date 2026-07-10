# US Stock Auto Trading Plan

## Status

US stock automation is planned only. There is no implemented US stock live data
connection, order routing, or strategy worker.

## Why Kiwoom REST GitHub Samples Matter

The official Kiwoom REST API GitHub repository separates documentation, client
helpers, realtime helpers, and examples. That shape is useful for the current
Mac/Python/AWS direction because it lets `strategy-pilot` keep a server-side
worker boundary instead of placing broker logic in the browser.

For now, only the structural lesson is used:

- Credentials stay outside frontend code.
- REST and WebSocket client boundaries are separate.
- Realtime subscriptions are packet-based and need fixture tests before live
  use.
- Order examples are explicitly excluded.

## Planned Sequence

1. Complete Korean stock paper engine observation.
2. Add Kiwoom REST/WebSocket provider fixtures without live calls.
3. Confirm official US stock API availability and account constraints.
4. Add US stock read-only schemas.
5. Add paper-only strategy simulation.
6. Review risk limits, market hours, FX handling, and tax/reporting needs.
7. Consider live order design only after separate safety approval.

## Current TR Implementation Skeleton

The project now has a local Python skeleton for US stock TR classification and
request construction under `backend/trading_engine/providers/kiwoom_us/`.

Implemented as non-network builders:

- `ust21110`, `ust21120`, `ust21150`, `ust21510`, `ust21630`, `ust21650`
- `usa20280`, `usa20281`, `usa20290`, `usa20291`
- `FE`, `FT`

Blocked as order-related:

- `ust20000`, `ust20001`, `ust20002`, `ust20003`
- `F4`

The builders do not use credentials, do not open sockets, and do not call
Kiwoom. They only normalize the TR inventory and fixture-test request shapes.

## Read-only Client Skeleton

The next local skeleton layer adds:

- `KiwoomUsRestClientSkeleton` for request shape construction only.
- Response mappers for condition search, account balance, and PnL fixtures.
- Safety helpers that separate read-only TRs from blocked order TRs.

This is still not a live provider. The client has no HTTP transport and
`liveProvider=false` blocks execution before any external call could occur.

## Explicitly Blocked

- Browser-direct Kiwoom API calls.
- Service-role or broker secrets in frontend code.
- Live US stock order placement.
- Shared order path between Korean stock and US stock without a separate risk
  review.
