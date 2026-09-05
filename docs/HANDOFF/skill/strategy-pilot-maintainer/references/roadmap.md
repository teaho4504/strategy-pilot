# Roadmap and Improvement Process

## Guiding rule

Advance by evidence, not by UI appearance. Each phase must produce a reproducible command, automated tests, and a clearly stated live-verification boundary.

## Phase 0: Make the current work reproducible

Priority: critical.

1. Export the current dirty worktree without secrets using the bundled script.
2. Restore it on a second machine and run all tests.
3. Review the current worktree changes and separate them into intentional commits:
   - documentation
   - frontend/auth/UI
   - backend read-only APIs
   - realtime and conditions
   - strategies/backtesting
   - risk/order recovery
4. Ensure ignore rules cover `.env`, databases, caches, logs, `dist`, dependencies and backup files.
5. Only then use Git as the authoritative transfer mechanism.

Exit criterion: a clean clone plus documented local configuration reproduces the same tests and dashboard.

## Phase 1: Restore stable broker authentication

1. Recheck `/oauth2/token` without printing values.
2. Require direct HTTPS JSON success; reject redirects and HTML.
3. Restore a CLI-profile dashboard session.
4. Verify read-only account and ranking calls.
5. Record only safe status, HTTP code and Kiwoom result code.

Exit criterion: repeated session creation and read-only calls succeed without credential leakage.

## Phase 2: Validate live read-only observation

1. Register condition list/search/realtime in required order.
2. Confirm multiple candidates enter/leave correctly.
3. Register FE/FT for candidates and holdings.
4. Measure freshness, missing symbols, reconnect and resubscribe behavior.
5. Confirm the observation runner produces explainable decisions without any order call.

Exit criterion: a full market session can run in observation mode with bounded errors, no leaks and no order transport.

## Phase 3: Establish strategy evidence

1. Build a reproducible historical candle dataset pipeline.
2. Run 1-minute and 5-minute logic through the same pure Python evaluators used live.
3. Include fees, spread, slippage, partial fill and missed-limit assumptions.
4. Split results by strategy, month, symbol, ET time, RVOL and spread.
5. Add walk-forward/out-of-sample tests.

Exit criterion: strategy metrics are reproducible and not concentrated in one symbol/month. Existing code does not yet satisfy this evidence standard.

## Phase 4: Finish order-state safety before live orders

1. Validate F4/F5 event mapping offline with recorded sanitized envelopes.
2. Validate REST reconciliation for pending, partial, full, canceled and rejected orders.
3. Prove restart recovery cannot duplicate an order.
4. Prove stale data, unknown state and disconnect block new entries.
5. Prove exit retries and end-of-day liquidation remain observable and bounded.
6. Add an operator runbook and rollback procedure.

Exit criterion: state-machine tests cover every terminal and uncertain state, and internal state matches broker state after restart.

## Phase 5: Controlled production validation

This phase requires explicit user approval at execution time.

1. Keep one-share and strict notional limits.
2. Enable only one reviewed strategy and one account.
3. Observe first; execute only during a controlled window.
4. Verify submission, fill, position, exit and analytics independently.
5. Re-lock immediately after the test and audit logs.

Passing one trade does not authorize unattended production trading.

## Phase 6: Secure remote operation

1. Prefer Tailscale or a VPN; do not expose Vite/FastAPI directly to the internet.
2. Bind backend to loopback behind an authenticated TLS reverse proxy.
3. Add durable operator identity, short sessions, rate limits and audit trails.
4. Store secrets in OS keyring or a cloud secret manager.
5. Add monitoring for process death, stale data, broker disconnect and order uncertainty.

## Ongoing improvement loop

```text
Observe -> save sanitized evidence -> reproduce -> add failing test
-> implement smallest fix -> run full verification -> update docs
-> re-observe under read-only policy
```

Never tune by silently weakening safety criteria just to increase order count.
