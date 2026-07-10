# US Stock Read-only Client Plan

## Current State

This phase is a skeleton step before any live Kiwoom API connection. The Python
trading engine can classify US stock TRs, build read-only request shapes, and
map fixture responses into internal models. It cannot send HTTP requests, open
WebSocket connections, or place orders.

## Read-only Scope

Allowed read-only TRs:

- Condition search: `usa20280`, `usa20281`, `usa20290`, `usa20291`.
- Realtime market data: `FE`, `FT`.
- Account and PnL: `ust21110`, `ust21120`, `ust21150`, `ust21510`,
  `ust21630`, `ust21650`.

Blocked order-related TRs:

- REST order: `ust20000`, `ust20001`, `ust20002`, `ust20003`.
- Realtime order confirmation: `F4`.

## Safety Policy

- `liveProvider=false` is the default and blocks execution before any transport
  layer could be used.
- The skeleton does not import `httpx`, `requests`, or `websockets`.
- Request builders may produce headers and body shapes, but they do not send
  them.
- Order-related TRs raise `UsOrderBlockedError`.
- App keys, secret keys, OAuth tokens, account numbers, and raw live responses
  must stay out of code, tests, documents, and commits.

## Conditions Before Real Read-only Calls

Before enabling real read-only API calls, the project needs:

1. Documented execution policy for US read-only mode.
2. Explicit `liveProvider=true` configuration, defaulting to false.
3. Server-side credential loading through environment variables or keyring.
4. Safe token redaction in logs and exceptions.
5. Fixture tests updated from official response schemas, without account values.
6. Order execution still disabled by policy and tests.

## Still Not Implemented

- Live US REST transport.
- Live US WebSocket connection.
- US stock order execution.
- Shared live order path.
- Dashboard integration for US provider status.
