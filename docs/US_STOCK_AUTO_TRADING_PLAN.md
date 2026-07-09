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

## Explicitly Blocked

- Browser-direct Kiwoom API calls.
- Service-role or broker secrets in frontend code.
- Live US stock order placement.
- Shared order path between Korean stock and US stock without a separate risk
  review.
