# US Stock Read-only Client Plan

## Current State

This phase now includes a guarded local read-only HTTP smoke path. The Python
trading engine can classify US stock TRs, build read-only request shapes, map
fixture responses into internal models, and execute approved read-only smoke
TRs through an injected HTTP sender after explicit operator confirmation. It
cannot open WebSocket connections or place orders.

## Read-only Scope

Allowed read-only TRs:

- Condition search: `usa20280`, `usa20281`, `usa20290`, `usa20291`.
- Realtime market data: `FE`, `FT`.
- Account and PnL: `ust21110`, `ust21120`, `ust21150`, `ust21510`,
  `ust21630`, `ust21650`, `usa21670`.

Blocked order-related TRs:

- REST order: `ust20000`, `ust20001`, `ust20002`, `ust20003`.
- Realtime order confirmation/fill: `F4`, `F5`.

## Safety Policy

- `liveProvider=false` is the default and blocks execution before any transport
  layer could be used.
- The skeleton does not import `httpx`, `requests`, or `websockets`.
- Request builders may produce headers and body shapes, but they do not send
  them.
- Order-related TRs raise `UsOrderBlockedError`.
- App keys, secret keys, OAuth tokens, account numbers, and raw live responses
  must stay out of code, tests, documents, and commits.
- Credential policy is defined in `docs/KIWOOM_US_CREDENTIAL_POLICY.md`.
- `order_enabled=False` and `read_only=True` are required before any transport
  can be considered.
- Fake transport is the only fully executable transport.
- `KiwoomUsHttpReadOnlyTransport` can prepare URL, header, body, timeout, and
  response mapping through an injected sender.
- `KiwoomUsUrllibHttpSender` is the concrete HTTP sender, but it is blocked by
  default and requires explicit read-only smoke-test confirmation before it can
  open a network connection.
- Local fake-transport integration tests cover credential policy, request
  creation, fake response return, and mapper conversion.
- HTTP transport model tests cover sender injection, token requirement,
  read-only request preparation, non-zero return code handling, and no direct
  network-client imports.
- `usa21670` daily account return is supported as read-only with required
  `from`/`to` `YYYYMMDD` request fields and safe `result_list` mapping. The
  live smoke check confirmed that the current operating API expects `from` and
  `to`.

## Conditions Before Additional Real Read-only Calls

Before adding more real read-only API calls, the project needs:

1. Documented execution policy for US read-only mode.
2. Explicit `liveProvider=true` configuration, defaulting to false.
3. Server-side credential loading through environment variables or keyring.
4. Safe token redaction in logs and exceptions.
5. Fixture tests updated from official response schemas, without account values.
6. Order execution still disabled by policy and tests.
7. Local fake-transport integration tests proving no network import/call.
8. HTTP sender implementation reviewed separately with no order path.
9. A smoke-test plan with exact TR order, safe output fields, and
   manual operator confirmation.

## Still Not Implemented

- Live US WebSocket connection.
- US stock order execution.
- Shared live order path.
- Dashboard integration for US provider status.

## Next Step

The current next step is expanding the read-only backdata inventory before
dashboard integration. The smoke-test plan is recorded in
`docs/US_STOCK_READONLY_SMOKE_TEST_PLAN.md` and defines:

- Which TR is called first.
- Required local/server environment variables.
- Confirmation phrase.
- Safe console output fields.
- Stop-on-first-error behavior.
- Order TR block verification before and after the smoke test.

Any live smoke execution must use the documented confirmation variables, safe
output policy, and order blocking unchanged.
