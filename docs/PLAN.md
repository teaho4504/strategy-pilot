# Strategy Pilot Plan

## Current Runtime

- Vite React dashboard and FastAPI backend are implemented.
- Kiwoom real-account session, US account TR, chart/ranking TR, condition search, realtime FE/FT, strategy evaluation, order guards, live order service, exit monitor and analytics are present.
- Premarket candidates can enter the same strategy pipeline only when `KIWOOM_US_PREMARKET_ENTRY_ENABLED=true`; entry uses a fresh FT best-ask limit order (`ust20000`, `trde_tp=00`) rather than a market order.
- Runtime Mock/Paper data, Paper API, Paper runner and Paper UI were removed.
- Strategy Builder can select a saved Hero Global US condition formula. The
  backend stores its sequence/name and keeps independent
  `usa20280 -> usa20281 -> usa20290` monitors for strategy-specific candidates;
  `usa20291` is sent when a monitor stops.
- A strategy ON action starts its selected condition monitor. OFF sends
  `usa20291` only after the last enabled strategy using that condition is
  disabled.
- API failure never falls back to fabricated account, quote, holding, fill or strategy data.
- A capital-allocation model now defines the proposed multi-entry policy:
  maximum four symbols, two filled tranches per symbol, and 50% of each
  symbol budget per tranche. It accounts for pending-order reservations and
  pauses allocation when orderable cash is depleted.
- Allocation cycles, pending reservations, submitted broker order numbers and
  filled tranche counts are persisted in SQLite by account scope and US market
  date. The entry precheck applies this model without increasing the strategy's
  original order quantity.
- A submitted reservation is changed to filled only after `ust21510` confirms
  the matching buy order number and full filled quantity. A failed order
  submission releases its reservation.
- `ust21050` now reconciles submitted buy reservations against the original
  broker order number. Explicit full cancellation or rejection releases an
  unfilled reservation; a partial fill followed by cancellation keeps the
  tranche as filled. A missing row remains reserved because absence alone does
  not prove cancellation.
- Buy precheck now requires the documented conservative `ust31490` fields:
  `min_ord_alowq`, `min_ord_alowa`, and `crnc_code=USD`. Missing, insufficient,
  or mismatched values block entry.
- A controlled production read-only shape check confirmed that the live
  `ust31490` request requires `stex_tp`, `stk_cd`, and `uv`; it also confirmed
  the required no-margin quantity, amount, and USD currency response fields.
  `ust21050` returned the documented no-data state when no open order existed.
- Official `F4` order-confirmation and `F5` fill payloads can now be mapped into
  a minimal internal order event without retaining account number field `9201`
  or unknown field values. Live F4/F5 registration remains disconnected.
- Stored F4/F5 events can be replayed into the persistent allocation state
  after restart. Partial fill quantity, terminal cancellation/rejection, and
  complete fill state are persisted, while a hashed event identity prevents
  duplicate replay from counting a fill twice.
- A separate F4/F5 order-state monitor is wired to submitted allocation
  reservations and the REST reconciliation callback. It is disabled by default
  and requires both `KIWOOM_US_ORDER_STATE_MONITOR_ENABLED=true` and the exact
  monitor confirmation phrase. A configured but disconnected monitor blocks
  additional auto-entry attempts while submitted orders exist.
- The authenticated dashboard can read a sanitized F4/F5 monitor diagnostic
  snapshot. It exposes connection state, monitored-symbol count, safe error
  class names and reconciliation counters without returning symbols, account
  identifiers or credentials.
- The monitor rejects unexpected login responses and reconnects with bounded
  exponential backoff. Connection, heartbeat, retry and reconnect counters are
  available through the same sanitized diagnostic response.
- A local-only preflight checks monitor configuration, live-session validity,
  runtime order lock and submitted reservations before any controlled F4/F5
  observation. It does not open a WebSocket or call an order endpoint.
- A successful Kiwoom login now asks the default-disabled monitor lifecycle to
  recover any persisted submitted reservations. With no submitted reservation
  or with monitoring disabled, this remains a no-network operation.
- Dashboard logout revokes the backend Kiwoom session and stops the F4/F5
  monitor before the frontend clears its local token and query cache.
- The US read-only HTTP transport now preserves Kiwoom `cont-yn` and
  `next-key` response headers. `ust21050` and `ust21510` follow continuation
  pages with a bounded loop and merge duplicate boundary rows
  conservatively.
- Submitted orders are rechecked at a configurable five-second minimum
  interval. While any broker state remains unresolved, all additional
  auto-entry candidate evaluation is paused; after 30 seconds the diagnostic
  changes to a confirmation-timeout warning without releasing the reservation.
- Submission time, last reconciliation time, safe reconciliation result code,
  and attempt count are persisted with each reservation. Restarting the
  backend therefore does not reset the timeout window or trigger an immediate
  duplicate broker query.
- REST reconciliation now commits terminal status, confirmed fill quantity,
  broker status summary, and reconciliation metadata in one SQLite
  transaction. A partially filled order whose remainder is confirmed canceled
  preserves only its actual filled quantity after restart.
- The shape-only order-state audit now checks `ust21050`, `ust21510`,
  `ust21070`, and `ust31490`. It reports only schema keys and row-presence
  flags; order numbers, symbols, quantities, prices, account identifiers, and
  credentials are excluded from output.
- A controlled production read-only audit confirmed the current `ust21510`
  request contract uses `stex_tp=ND/NY/NA` and `stk_cd`. The legacy
  `stex_tp=000030, stk_code` Postman shape is not used by the account service.
  All four audit TRs completed without invoking an order TR.
- A separate schema-only production audit confirms `ust21110`, `ust21120`,
  `ust21650`, and `usa21670` match the current account-response contracts.
  `ust21630` returned the documented no-data state for a day without realized
  profit/loss. The audit renews a local CLI-profile session when needed and
  never prints account values, symbols, credentials, or tokens.
- The FE/FT quote monitor now reports connected, heartbeat and retry state and
  reconnects with bounded 1, 2, 4, 8, 16 and 30 second delays. Every reconnect
  creates a new Kiwoom login and repeats the full symbol registration, so a
  dropped socket cannot silently remain unsubscribed.
- Realtime prices older than ten seconds are not accepted by automatic exit
  evaluation. The service requests a fresh read-only `usa10100` quote instead;
  if no current price can be established, the existing fail-closed quote
  blocker remains active.
- A controlled production FE/FT observation completed with a valid local CLI
  session: the monitor connected, registered 20 symbols, received a heartbeat,
  and reported no reconnect or stream error. The runtime order lock remained
  present and no order channel or order TR was used.
- The auto-trade runner now has an explicit observation mode. It repeatedly
  evaluates condition-search, ranking, chart, and entry-plan data while the
  runtime order lock remains present. This mode never runs order precheck,
  allocation reservation, automatic exit, or order submission.
- The latest observation result is exposed in runtime status as a bounded
  in-memory snapshot: strategy, symbol, exchange, action, timestamp, and safe
  blocker codes. The strategy dashboard uses it to explain why a candidate is
  waiting without reading raw broker payloads.
- Observation state changes are also written to the existing sanitized
  auto-trade event journal. Identical five-second ticks are deduplicated, so
  only a changed strategy, candidate, action, blocker, or failed criterion
  creates a new history row.
- The strategy dashboard aggregates those deduplicated rows by strategy. The
  counts describe state changes, ready/waiting transitions, unique public
  ticker candidates, and the most frequent failed criterion keys; they are not
  raw evaluation-tick counts or broker execution metrics.
- The runner can operate in `observe` mode while `KIWOOM_READ_ONLY=true` and
  `KIWOOM_US_ENABLE_ORDER=false`. Candidate evaluation therefore no longer
  requires an order-capable server configuration.
- Read-only observation can be restored after a backend restart with the
  explicit `KIWOOM_US_AUTOTRADE_OBSERVATION_ENABLED=true` setting. The generic
  backend default remains false; the local dashboard start script opts in to
  observation and still forces read-only/order-disabled policy by default.
- F4/F5 preflight now distinguishes `no_target` from a blocked monitor. With no
  submitted reservation it performs no WebSocket connection and reports a
  normal waiting state; session, lock, and monitor configuration become
  actionable only when an existing submitted order requires reconciliation.
- The read-only realtime window now reports observation quality for monitored
  FE/FT symbols: ten-second freshness coverage, missing/stale symbol counts,
  receive-delay counts above two seconds, average/max receive delay, and the
  current ET market session. The strategy dashboard combines this with the
  connected condition-candidate count.
- Automatic buy attempts now persist their allocation-reservation link.
  A fully confirmed `ust21510` automatic sell fill closes only that linked
  filled reservation. Partial or unconfirmed sells keep the allocation slot
  open, and legacy rows can recover by exact buy order number, symbol, and
  exchange.
- The legacy single-open-position entry gate has been removed. Confirmed
  positions may be monitored for exit while the next candidate is evaluated.
  Allocation remains sequential: at most one order is submitted per runner
  tick, every submitted order must be confirmed before another entry, and the
  persisted policy enforces four symbols and two tranches per symbol.
- Automatic exit monitoring is now scoped by source buy-order ID. Every armed
  buy is evaluated each tick, partial buy fills are aggregated by order number,
  and an accepted sell remains pending until its fill is confirmed by
  `ust21510`.

## Next Work

1. Recheck the official Kiwoom token endpoint and restore a dashboard session
   only after it returns a direct successful JSON token response. Do not bypass
   or follow an HTTPS-to-HTTP redirect.
2. Run a controlled F4/F5 read-only production observation and verify actual
   event ordering against `ust21050`, `ust21510`, and `ust21070`, including
   delayed broker-state propagation. The local dashboard must have a valid
   Kiwoom session and an existing submitted reservation before observation.
3. Complete controlled live validation with one-share limits and audit review.
4. Harden remote access before any public deployment.

## Explicit Boundary

Live-only means the application has no simulated fallback. It does not mean orders are enabled by default. Order execution remains gated by server configuration, runtime lock, authenticated live session, strategy conditions and risk controls.
