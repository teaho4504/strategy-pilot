# Phase 1 Read-only Backend Summary

Current status: Phase 1 read-only backend complete, live validation passed.

This document summarizes why the Phase 1 FastAPI read-only backend was created, what it currently supports, what remains intentionally excluded, and what must happen before the project can move toward frontend integration or live trading design.

## 1. Phase 1 Goal

Phase 1 builds a FastAPI read-only backend foundation for Kiwoom domestic stock REST account data.

The goal is to safely prepare account inquiry APIs before any trading automation is considered. The backend focuses on:

- Account lookup.
- Cash and deposit inquiry.
- Account valuation.
- Holdings and execution balance inquiry.
- Account and per-symbol performance inquiry.
- A future API contract that the Vite frontend can call without exposing broker credentials.

Phase 1 does not implement order placement, order amendment, order cancellation, realtime trading, or live account automation.

## 2. Why This Order

An automated trading system must trust account state before it can safely evaluate strategy signals or order sizing. For that reason, Phase 1 prioritizes account, cash, valuation, holdings, and performance data ahead of any order path.

The implementation order also reduces security and operational risk:

- Broker app keys, secrets, tokens, and account identifiers stay outside the browser and outside Git-tracked runtime files.
- Mock mode remains the default, so local development does not accidentally call live APIs.
- Local live read-only verification comes before frontend integration, so actual Kiwoom response schemas can be validated before UI assumptions harden.
- Frontend integration comes before cloud deployment, so API contracts can be corrected while the system is still local.
- AWS deployment, realtime ingestion, paper trading, and live order review are later phases because each adds more operational and financial risk.

Live order functionality was not implemented because the project does not yet have a production risk engine, audit trail, kill-switch enforcement path, paper broker validation, or worker architecture.

## 3. Current Architecture

```text
Vercel
└─ Vite + React Dashboard
   └─ currently mock based

Local / Future AWS
└─ FastAPI Read-only Backend
   ├─ Token Manager
   ├─ Kiwoom REST Client
   ├─ Account Mapper
   └─ Read-only API

Kiwoom REST API
└─ Domestic stock account inquiry only
```

Frontend responsibilities remain limited to dashboard UI and future HTTP calls to the project-owned FastAPI API. The browser must not call Kiwoom REST directly and must not hold broker credentials.

Backend responsibilities are limited to token handling, read-only Kiwoom REST calls, account response mapping, mock mode behavior, and safe status reporting.

## 4. Implemented TRs And Roles

- `au10001`: access token issuance. Used only by the backend token manager to obtain an OAuth access token.
- `ka00001`: account identifier lookup. Supports `/api/accounts` without returning the actual account number to clients.
- `kt00001`: cash / deposit inquiry. Supports `/api/account/cash` for cash, withdrawable amount, and orderable amount mapping.
- `kt00004`: account valuation. Supports `/api/account/portfolio` for total account valuation, daily PnL, cumulative PnL, and cash ratio mapping.
- `kt00005`: holdings / execution balance. Supports `/api/account/holdings` for held symbols, quantity, average price, valuation, PnL, and weight mapping.
- `ka10085`: account performance. Supports `/api/account/performance` for account-level and per-symbol performance mapping.

These TRs were selected because they cover the current dashboard's account state requirements without introducing order or realtime execution risk.

## 5. Security And Safety Guards

- `KIWOOM_MODE=mock` is the default mode.
- `KIWOOM_READ_ONLY=true` is the required read-only default.
- `KIWOOM_ENABLE_ORDER=false` is the required order-disabled default.
- Local live verification requires `KIWOOM_LIVE_VERIFY_CONFIRM=I_UNDERSTAND_READ_ONLY`.
- `/api/kiwoom/status` must not return tokens, app keys, secret keys, account numbers, or masked forms of those values.
- Kiwoom REST calls are backend-only. The browser must not call Kiwoom directly.
- Live API failure must not silently fall back to mock data.
- No order, amendment, or cancellation API exists in Phase 1.
- Raw live responses must not be committed.

## 6. Verification Status

### Implemented And Tested

- FastAPI app import.
- `/api/health` smoke test.
- Mock mode default behavior.
- `/api/kiwoom/status` secret-safe response shape.
- Missing live credentials returning a configuration error.
- Token failure returning a backend error without leaking secrets.
- Mapper tests for `ka00001`, `kt00001`, `kt00004`, `kt00005`, and `ka10085` fixture shapes.
- Mapper regression tests for live-response field fallbacks, numeric string parsing, empty holdings lists, and secret-safe validation errors.
- Continuation query handling for `cont-yn=Y` and `next-key`.
- Local live verification guard checks.
- Local live read-only verification passed from `au10001` through `ka10085` without printing token, account number, cash balance, holdings values, or raw JSON.
- `python3 -m compileall backend/app backend/scripts`.
- Backend pytest suite.

### Prepared And Live-verified

- `au10001` token issue against actual Kiwoom infrastructure.
- `ka00001`, `kt00001`, `kt00004`, `kt00005`, and `ka10085` live read-only execution.
- Top-level live response schema key validation by the verification script.

### Mapper Refinement Completed

- Live-response key review and fixture-based mapper regression coverage are complete for the Phase 1 backend scope.
- Any future nested row-level field differences found during endpoint-level frontend integration should be handled as follow-up mapper fixes.
- Frontend adapter integration remains a separate next step against the stable backend API contract.

### Not Implemented

- Frontend adapter integration.
- Vercel backend URL connection.
- AWS backend deployment.
- Kiwoom realtime WebSocket ingestion.
- Strategy Worker.
- Risk Worker.
- Paper Trading.
- Live orders.

## 7. Explicitly Excluded

The following are not part of Phase 1:

- Frontend adapter integration.
- Vercel backend URL connection.
- AWS deployment.
- WebSocket.
- Strategy Worker.
- Risk Worker.
- Paper Trading.
- Live orders.
- Order placement, amendment, or cancellation APIs.
- `ka01690` daily balance performance.
- Order TRs, fill query TRs, realtime TRs, quote TRs, chart TRs, US stock APIs, and condition-search APIs.

## 8. Phase 1 Completion Conditions

Phase 1 should only be marked fully complete after all of the following are true:

1. Local live read-only verification runs from `au10001` through `ka10085`. Completed.
2. Actual Kiwoom response fields are validated against mapper expectations. Completed for the Phase 1 live read-only verification scope.
3. Mapper corrections from live response schemas are completed for the Phase 1 backend scope.
4. No secret leakage is confirmed in status APIs, script output, logs, and committed files.
5. Backend work is committed and pushed to the remote branch.

Frontend adapter integration is not required for backend Phase 1 completion. It should remain a separate task after live read-only validation.

## 9. Next Steps

1. Keep the backend commit pushed on `feature/fastapi-readonly-account`.
2. Create a separate frontend adapter integration task after read-only mapper refinement passes.
5. Plan AWS FastAPI deployment and Vercel API URL connection only after the backend API contract is validated.
6. Defer realtime gateway, workers, paper trading, and live order design to later risk-controlled phases.

Do not describe the current state as live trading integration complete. The accurate status is: Phase 1 read-only backend complete, live validation passed.
