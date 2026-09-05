# Risk Guardrails

## Live-only Data

- Only Kiwoom production REST/WebSocket data may drive the dashboard and strategies.
- Missing or stale data blocks entry; it is never replaced with Mock/Paper values.
- Broker secrets, session tokens, account numbers and raw responses must not appear in frontend bundles or logs.

## Order Gates

Every live order requires all of the following:

1. A valid real-account server session.
2. Live order environment policy enabled.
3. Read-only mode disabled.
4. Runtime order lock explicitly open.
5. Auto-trade master and the individual strategy enabled.
6. Fresh quote/orderbook data and all strategy entry checks passed.
7. Risk limits, available amount, holding and open-order reconciliation passed.

Strategy creation or strategy activation alone must not bypass these gates.

## Capital Allocation

The proposed multi-position policy has a persisted safety foundation:

- Maximum four distinct open symbols.
- Maximum two filled entry tranches per symbol.
- Each symbol receives at most one quarter of the allocation-cycle capital.
- Each tranche receives at most 50% of that symbol budget.
- Pending-order notional is reserved before evaluating the next candidate.
- A pending order blocks another order for the same symbol.
- Zero orderable cash pauses new entries.
- Account identity is stored only as a one-way derived scope; raw account
  numbers and credentials are not written to allocation tables.
- A strategy ticket can be reduced by allocation limits but is never enlarged.
- Broker acceptance does not count as a fill. `ust21510` must confirm the exact
  buy order number and full quantity before a tranche is marked filled.
- Order submission failure releases the reservation. Unknown submitted-order
  state remains reserved and blocks another order rather than risking a
  duplicate.
- `ust21050` releases an unfilled reservation only when the matching original
  order number has explicit canceled quantity or rejection status. A missing
  open-order row never authorizes a new order.
- `ust31490` must provide `min_ord_alowq`, `min_ord_alowa`, and USD currency.
  Other margin buckets or KRW values are not substituted into allocation
  capital.
- The production request shape for `ust31490` is fixed to `stex_tp`, `stk_cd`,
  and `uv`. A read-only production check confirmed this contract without
  submitting an order.
- F4/F5 mapping deliberately drops broker account field `9201` and every
  unknown field value. Only an unknown field ID may be retained for schema
  diagnostics.
- F4/F5 recovery is idempotent per allocation cycle. Partial fills remain
  pending, full fills become filled, and confirmed cancellation/rejection
  releases an unfilled reservation. A partial fill followed by confirmed
  cancellation remains a filled tranche.
- The recovery event table stores only a hashed event identity and minimal
  order-state fields. It does not store raw payloads, credentials, tokens, or
  account numbers.
- The F4/F5 monitor is a separate connection from FE/FT. It is OFF by default
  and requires a dedicated enable flag plus confirmation phrase.
- The F4/F5 registration packet contains only submitted symbols, exchanges,
  and channel identifiers. It contains no account number or token.
- The dashboard monitor diagnostic returns only an aggregate symbol count and
  sanitized error classes. It does not return monitored symbol names, account
  identifiers, access tokens or raw broker payloads.
- Unexpected F4/F5 login responses stop registration. Reconnect attempts use
  a bounded 1, 2, 4, 8 second progression capped at 30 seconds, preventing a
  tight reconnect loop during broker or network outages.
- F4/F5 preflight requires the runtime order lock and reports only aggregate
  submitted-order and eligible-symbol counts. Running preflight cannot connect
  to Kiwoom or submit, amend, cancel or liquidate an order.
- Login recovery can start F4/F5 observation only when the dedicated monitor
  flags are valid and persisted submitted reservations exist. Monitor recovery
  failure cannot bypass order gates or fabricate order state.
- Dashboard logout revokes the server-side Kiwoom session and stops the
  F4/F5 monitor. Local token and query-cache cleanup still completes if the
  backend logout request cannot be delivered.
- `ust21050` and `ust21510` continuation headers are preserved and followed
  for at most 20 pages. A missing or repeated continuation key, or an exceeded
  page limit, is treated as incomplete broker state and never as proof that an
  order disappeared.
- Exact duplicate rows at continuation boundaries are counted once. This
  deliberately favors an unresolved reservation over an early full-fill or
  cancellation conclusion.
- Submitted-order REST reconciliation is rate-limited by
  `KIWOOM_US_ORDER_RECONCILE_INTERVAL_SECONDS` (default five seconds).
  `KIWOOM_US_ORDER_CONFIRMATION_TIMEOUT_SECONDS` (default 30 seconds) changes
  the displayed blocker to a timeout warning but never releases the
  reservation. Candidate scanning and additional buys remain blocked until
  fill, cancellation, or rejection is positively confirmed.
- Submission and reconciliation timing survives backend restart in SQLite.
  Only predefined result codes and an attempt count are stored; raw broker
  responses, account values, credentials, and tokens are excluded.
- Terminal REST reconciliation is atomic. A canceled remainder never converts
  a partial fill into the original requested quantity; only the confirmed
  filled quantity is retained as the position tranche.
- The order-state shape audit is read-only and limited to `ust21050`,
  `ust21510`, `ust21070`, and `ust31490`. Its output contains field names and
  booleans only, never broker row values or credentials.
- The live `ust21510` request is pinned to the production-verified
  `stex_tp=ND/NY/NA` and `stk_cd` fields. Tests reject a regression to the
  incompatible legacy `000030/stk_code` request shape.
- The account-shape audit is limited to `ust21110`, `ust21120`, `ust21630`,
  `ust21650`, and `usa21670`. It emits contract booleans and field names only;
  broker values and identifiers never enter its output.
- FE/FT reconnect uses bounded exponential backoff and replays the complete
  read-only subscription after a new successful login. Connection and
  heartbeat state never authorize an order by themselves.
- A cached realtime price is valid for order monitoring for at most ten
  seconds. Older prices are ignored and replaced with a fresh read-only REST
  quote; unavailable fresh data keeps order progression blocked.
- A missing or invalid persisted timestamp fails closed as pending state. It
  does not release reserved capital or authorize another order.
- Allocation slots close only after the automatic sell order's full quantity
  is confirmed through `ust21510`. Submission acceptance, missing rows, and
  partial sell fills do not close a slot.
- The close operation targets the persisted allocation-reservation ID. Legacy
  rows may fall back only to an exact buy order number, symbol, and exchange
  match; an ambiguous or non-filled reservation remains open.
- If the monitor is explicitly enabled and a submitted order exists, loss of
  its connection blocks additional automated entries with
  `ORDER_STATE_MONITOR_UNAVAILABLE`. A failed REST cross-check blocks them with
  `ORDER_STATE_RECONCILIATION_FAILED`.
- Observation mode is separate from live auto-trading. Enabling observation
  first disables the live runtime, stops order-state monitoring, and writes the
  runtime lock. Its runner path only builds entry plans and cannot call order
  precheck, capital allocation, `ust20000`, `ust20001`, or automatic exit.
- Observation snapshots are process-memory diagnostics only. They exclude
  account identifiers, credentials, access tokens, order numbers, raw broker
  payloads, quantities, and monetary account values.
- Persisted observation-change events contain only strategy ID, public market
  symbol/exchange, safe blocker codes, and failed criterion keys. They never
  persist broker responses, prices, quantities, account values, or secrets.
- Read-only observation runs with both the order feature flag disabled and the
  runtime lock present. Even if an observation result is entry-ready, the
  runner has no branch to precheck or submit an order in this mode.
- Observation statistics are derived only from sanitized, deduplicated event
  rows. The response excludes credentials, account values, raw broker payloads,
  prices, quantities, and order identifiers.
- Observation auto-start is accepted only when the runner resolves to
  `observe` mode. A live-mode runner never converts the observation auto-start
  flag into an enabled observation session.
- F4/F5 monitoring never connects speculatively. A submitted reservation with
  an order number is required before the monitor can move from `no_target` to
  ready or blocked state.
- Realtime quality metrics are observational only. Missing, stale, or delayed
  FE/FT data must block confidence in a strategy signal; the metrics never
  authorize an order or relax an entry criterion.
- Token issuance never follows an HTTP redirect. In particular, an HTTPS token
  request redirected to an HTTP page fails closed as
  `TOKEN_ENDPOINT_REDIRECT`; redirect URLs and bodies are not exposed to the
  dashboard. A valid broker session requires a direct successful JSON token
  response from the configured official HTTPS endpoint.

Allocation-cycle state and pending reservations survive restart, and the
current entry precheck uses them conservatively. Multiple confirmed positions
may coexist within the four-symbol allocation limit, but only one order may be
submitted per runner tick. Any unconfirmed submitted reservation blocks the
next entry globally. F4/F5 payload mapping, offline replay, and a
default-disabled monitor are implemented; production event ordering and
delayed broker-state propagation still require controlled verification.

Condition-search selection also does not authorize an order. A strategy uses
only symbols returned by its selected Hero Global condition sequence, while the
chart, realtime quote, account, risk, runtime-lock, and order-policy gates remain
mandatory.

The strategy ON/OFF control owns condition-search registration and cleanup only.
ON may register `usa20290`, and OFF may clear it with `usa20291`; neither action
opens the runtime order lock or bypasses any order gate.

Premarket entry adds these mandatory checks:

- `KIWOOM_US_PREMARKET_ENTRY_ENABLED=true`
- ET time is 04:00 through 09:29 on a weekday
- FT best bid and ask are present and no older than 10 seconds
- spread is 0.15% or less
- buy order is `ust20000` limit (`trde_tp=00`) at the current best ask

Premarket market orders are not generated.

## Failure Behavior

- WebSocket disconnect, stale quotes, unknown fill state, account query failure or risk state uncertainty blocks new entries.
- Duplicate orders are prohibited while order state is uncertain.
- An accepted exit order remains pending until `ust21510` confirms the matching
  sell order number and filled quantity; it is not immediately marked complete.
- Exit failures are logged and retried within configured limits; unresolved positions remain visible as warnings.
- Emergency lock blocks new entries and can cancel pending buys according to server policy.

## Verification Boundary

Automated tests use isolated fake transports only. Test fixtures are not importable runtime market/account fallbacks and never contain real credentials or account data.
