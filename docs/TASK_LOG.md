# Task Log

## 2026-07-04: Architecture Baseline Correction

### Corrected Facts

- Repository: `teaho4504/strategy-pilot`
- Production branch: `main`
- Actual production frontend baseline is Vite root application.
- `main` package.json is Vite-based.
- `main` has no Next.js `apps/web` structure.
- Vercel is understood to deploy the Vite root frontend.

### Corrected Assumption

Previous Next.js / `apps/web` / App Router assumptions were not aligned with `origin/main`.

Current temporary architecture baseline:

```text
Vercel
  -> Vite React Dashboard

AWS or equivalent backend host
  -> FastAPI read-only backend
  -> Kiwoom REST Account APIs

Future
  -> Realtime Gateway
  -> Strategy Worker
  -> Risk Manager
  -> Order Worker
```

### Existing Branch Analysis Summary

Reusable candidate branch:

```text
feature/backend-account-integration
```

Use only selected read-only backend files from that branch. Full branch merge is prohibited.

Reusable candidates:

- `backend/app/core/config.py`
- `backend/app/services/token_manager.py`
- `backend/app/services/kiwoom_client.py`
- `backend/app/api/health.py`
- `backend/app/api/account.py`
- `backend/app/api/kiwoom.py`
- `backend/app/schemas/*`
- `backend/app/services/account_service.py`
- `backend/app/services/balance_service.py`
- `backend/app/services/performance_service.py`
- `backend/app/services/market_service.py`
- `backend/.env.example`
- `backend/requirements.txt`
- `backend/README.md`

Excluded from Phase 1:

- `vercel.json`
- `deploy/aws/lightsail/*`
- `backend/Dockerfile`
- `backend/app/api/orders.py`
- `docs/VERCEL.md` hardcoded IP content
- full `README.md` overwrite
- broad frontend UI changes
- `src/App.tsx` broad changes
- `vite.config.ts` changes

### Phase 1 Status

The documentation baseline prepared the next implementation step.

## 2026-07-04: FastAPI Read-only Backend Foundation Started

### Facts

- Work is on `feature/fastapi-readonly-account`.
- A new `backend/` FastAPI application has been added from the harness baseline.
- The implementation is intentionally read-only and does not include order endpoints.
- Default mode remains `KIWOOM_MODE=mock`.

### Implemented So Far

- `/api/health`
- `/api/kiwoom/status`
- `/api/accounts`
- `/api/account/cash`
- `/api/account/portfolio`
- `/api/account/performance`
- `/api/account/holdings`
- `/api/market/watchlist`
- Backend-only Kiwoom token manager structure.
- Backend-only Kiwoom read-only TR client structure.

### Phase 1 TR Scope

- `au10001`: OAuth token issue.
- `ka00001`: account lookup.
- `kt00001`: cash lookup.
- `kt00004`: account valuation lookup.
- `kt00005`: holdings lookup.
- `ka10085`: account performance lookup.

`ka01690`, order TRs, fill query TRs, realtime WebSocket TRs, quote/order-book/chart TRs, US stock APIs, condition-search APIs, Worker, Docker, AWS deployment, Vercel settings, and frontend UI work remain excluded.

### Still Excluded

- Frontend adapter migration.
- Vercel proxy changes.
- Docker or AWS deployment files.
- WebSocket realtime gateway.
- Strategy, risk, or order workers.
- Order placement, amendment, or cancellation APIs.

## 2026-07-04: Local Live Read-only Verification Prepared

### Added

- `backend/scripts/verify_live_readonly.py` for manual local verification.
- Explicit live verification guard: `KIWOOM_LIVE_VERIFY_CONFIRM=I_UNDERSTAND_READ_ONLY`.
- Mapper validation errors for missing expected response fields.
- Tests for blocked live verification, secret-safe output, mapper validation, and continuation handling.

### Verification Policy

- The script runs only in live/read-only/order-disabled mode.
- The script prints schema keys, success/failure, and error type only.
- It does not print live response values, account numbers, balances, stock names, stock codes, app keys, secrets, or tokens.
- It stops on the first TR failure.

## 2026-07-05: au10001 Token Handling Safety Fix Prepared

### Reason

- Local live read-only verification surfaced that the `au10001` token response may use Kiwoom's documented `token` field rather than only an `access_token` field.
- The live verification failure printer also needed to avoid masking the original failure with a secondary exception.

### Changes

- Treat `token` as the primary `au10001` access token field.
- Keep `access_token` only as a compatibility fallback.
- Handle Kiwoom `return_code != 0` token responses as safe backend errors without logging raw response bodies.
- Print verification failures as minimal fields: TR ID, status, error type, HTTP status when available, and return code when available.

### Boundaries

- No actual Kiwoom API call was made for this fix.
- No order, WebSocket, Worker, AWS, Vercel, or frontend code was added.

## 2026-07-05: au10001 Request Contract Diagnostics Prepared

### Reason

- Live read-only verification received a Kiwoom `return_code=3` for `au10001`, which indicates an API ID contract problem.
- The local environment and guard checks were already passing, so the next fix focused on request construction and safe diagnostics rather than credentials or live retries.

### Changes

- Centralized the token API ID as `au10001` and the token path as `/oauth2/token`.
- Validate token request path before issuing the token HTTP request. The earlier `api-id` token header assumption was later superseded by the official OAuth example.
- Treat blank `KIWOOM_TOKEN_URL` as unset and fall back to `KIWOOM_BASE_URL + /oauth2/token`.
- Add safe token request diagnostics that show only method, path, boolean configuration presence, and API ID match state.

### Boundaries

- No actual Kiwoom API call was made for this diagnostic fix.
- No raw request body, raw response body, app key, secret key, token, or account number is logged.

## 2026-07-05: au10001 Wire Request Diagnostics Prepared

### Reason

- `return_code=3` persisted after IP allowlist changes and after confirming the configured token path and API ID.
- The next diagnostic needed to verify the exact request structure passed to `httpx`, not just high-level settings.

### Changes

- Build the OAuth request in one place before passing it to `httpx.AsyncClient.post`.
- Initially tested `api-id: au10001` with `Content-Type: application/json;charset=UTF-8` in the token request headers; this was later superseded by the official OAuth example, which omits `api-id`.
- Validate token request body keys as `grant_type`, `appkey`, and `secretkey`.
- Print safe wire diagnostics: URL path, wire API ID, header names, body key names, and boolean presence/match checks.
- Print sanitized `return_msg` when available without raw JSON or credential values.

### Authorization Header Decision

- The token issuance request still does not send an `Authorization` header.
- No empty Bearer token is added by guesswork; this requires official Kiwoom confirmation before changing.

### Boundaries

- No actual Kiwoom API call was made for this fix.
- No frontend, AWS, Vercel, Docker, order, WebSocket, or Worker code was changed.

## 2026-07-05: au10001 OAuth Header Contract Corrected

### Reason

- The official Kiwoom OAuth access-token Python example shows `au10001` token issuance without an `api-id` header.
- The previous diagnostic request included `api-id: au10001`, which likely caused Kiwoom `return_code=3` for a token request.

### Changes

- Token issuance now sends only `Content-Type: application/json;charset=UTF-8` as the OAuth request header.
- Token issuance explicitly rejects `api-id` and `Authorization` headers.
- Token issuance still validates body keys as `grant_type`, `appkey`, and `secretkey`.
- Regular account TR calls continue to send `api-id`, `Authorization: Bearer {token}`, `cont-yn`, and `next-key`.

### Boundaries

- No actual Kiwoom API call was made for this fix.
- No frontend, AWS, Vercel, Docker, order, WebSocket, or Worker code was changed.

## 2026-07-05: Phase 1 Live Read-only Validation Passed And Mapper Refinement Started

### Facts

- Local live read-only verification passed from `au10001` through `ka10085`.
- The verification output included only schema key names and safe status fields.
- No token, account number, cash balance, holding name, holding symbol, or raw JSON response was stored in the repository.

### Mapper Refinement

- `kt00004` portfolio mapping now accepts live amount suffix fallbacks such as `tdy_lspft_amt` and `lspft_amt`.
- Kiwoom client mock responses were adjusted toward Kiwoom-like read-only TR schema keys.
- Regression tests now cover live-style mapper fallbacks, numeric string parsing, empty holdings lists, and secret-safe validation errors.

### Boundaries

- No actual Kiwoom API call was made during mapper refinement.
- No API response contract breaking change was introduced.
- No frontend, AWS, Vercel, Docker, order, WebSocket, or Worker code was changed.

## 2026-07-09: Kiwoom REST Provider Skeleton Started

### Reference

- Official reference repository: `Kiwoom-Securities/Kiwoom-REST-API`.
- The repository was used only to understand structure and protocol boundaries:
  CLI/keyring-first credentials, regular TR headers, separated OAuth handling,
  WebSocket LOGIN and REG/REMOVE packet shape, and the existence of order
  examples that must not be executed.
- No official repository code was copied into this project.

### Added

- `backend/trading_engine/providers/kiwoom_rest/` skeleton package.
- Read-only REST client skeleton with live provider disabled by default.
- WebSocket skeleton with connect blocked by default.
- Payload adapter functions for quote, order book, and condition payloads.
- Safety helpers for order blocking and secret redaction.

### Boundaries

- No actual HTTP or WebSocket call is made.
- No Kiwoom key, token, account number, or `.env` value is added.
- No order endpoint or executable order method is added.
- Official order samples remain excluded until a separate live-order safety
  architecture is approved.

## 2026-07-10: Trading Engine Safety Phase

### Added

- Ignore rules for local SQLite runtime artifacts.
- `TRADING_ENGINE_DB_PATH` verification for configurable paper DB location.
- KST display time and US market date/session fields for paper fill journals.
- US market session helper skeleton: premarket, regular, afterhours, closed.
- Risk Manager regression tests for:
  - Kill Switch block.
  - Daily max loss block.
  - Same-symbol cooldown block.
  - Max open positions block.
  - Per-symbol entry amount block.

### Boundaries

- No live Kiwoom REST call was made.
- No live WebSocket connection was opened.
- No order endpoint or order execution path was added.
- `backend/data/*.sqlite3` and `pnpm-lock.yaml` remain excluded from this work.

## 2026-07-10: US Stock TR Skeleton From Sheet And PDF

### Sources

- Google Sheet `kiwoom_auto_trading_roadmap`, tab `05_API_TR관리`.
- Local Kiwoom REST API PDF.

### Added

- US stock TR inventory under `backend/trading_engine/providers/kiwoom_us/`.
- Read-only request builders for account/PnL TRs.
- WebSocket request builders for condition search and realtime quote/order book
  registration packets.
- Fixture adapters for US quote and condition payloads.
- Tests ensuring order TRs remain blocked and no network call is made.

### Boundaries

- No live Kiwoom API call was made.
- No app key, secret, token, account number, or `.env` value was added.
- US order TRs are inventoried but remain blocked.
- No order endpoint was added.

## 2026-07-10: US Stock Read-only Client Skeleton

### Added

- `KiwoomUsRestClientSkeleton` for US read-only TR request shape creation.
- `UsReadOnlyTrRequest`, `UsReadOnlyTrResponse`, `UsAccountBalance`,
  `UsProfitLoss`, and condition-search result models.
- Fixture response mappers with `UsMappingError` on missing required fields.
- Safety helpers for read-only allowlist, blocked order TRs, and realtime
  channel checks.
- Tests covering:
  - Read-only TR allowlist.
  - Blocked order TRs and blocked `F4`.
  - `FE` and `FT` realtime channel allowance.
  - `liveProvider=false` execution block.
  - Absence of `httpx`, `requests`, and `websockets` imports in the skeleton.
  - Fixture response mapping and safe validation errors.

### Boundaries

- No live Kiwoom REST call was made.
- No live WebSocket connection was opened.
- No transport layer was added.
- No app key, secret, token, account number, or `.env` value was added.
- US order TRs remain blocked by `UsOrderBlockedError`.

## 2026-07-11: US Credential Policy And Transport Interface

### Added

- US Kiwoom credential policy document.
- `KiwoomUsCredentialConfig` skeleton with:
  - `read_only=True` default.
  - `order_enabled=False` default.
  - env mapping helper.
  - keyring placeholder that raises `MissingCredentialError`.
  - redacted summary only.
- Read-only transport protocol and fake transport.
- `KiwoomUsRestClientSkeleton` transport injection path.
- Safety helpers for:
  - `order_enabled` blocking.
  - `liveProvider` policy.
  - credential-like payload detection.

### Tests

- Credential defaults and policy checks.
- Missing credential errors.
- Secret-like payload blocking.
- Fake transport response flow.
- `liveProvider=false` fake transport pre-call block.
- Absence of `httpx`, `requests`, and `websockets` imports in this layer.

### Boundaries

- No real Kiwoom REST call was made.
- No real WebSocket connection was opened.
- No real credential value was added.
- No order endpoint or executable order TR path was added.
- Order TRs and `F4` remain blocked.

## 2026-07-11: US Fake Transport Integration Tests

### Added

- Local fake-transport integration tests for:
  - Credential policy mapping.
  - Read-only request creation.
  - Fake response return.
  - Account balance mapper conversion.
  - PnL mapper conversion.
  - Condition search mapper conversion.
  - Order policy block.
  - `liveProvider=false` pre-transport block.
  - Network client import absence.

### Boundaries

- No live Kiwoom REST call was made.
- No live WebSocket connection was opened.
- No real app key, secret, token, account number, or `.env` value was added.
- No order endpoint or order execution path was added.
- The next step is a documented read-only smoke-test plan, not a live call.

## 2026-07-11: US Read-only Smoke Test Plan

### Added

- `US_READONLY_SMOKE_CONFIRM` confirmation phrase.
- Smoke-test step inventory for:
  - `ust21110`
  - `ust21120`
  - `ust21630`
  - `ust21650`
- Environment guard validator requiring:
  - `KIWOOM_US_READ_ONLY=true`
  - `KIWOOM_US_ENABLE_ORDER=false`
  - `KIWOOM_US_LIVE_PROVIDER=true`
  - `KIWOOM_US_SMOKE_CONFIRM=I_UNDERSTAND_US_READ_ONLY_ONLY`
- Safe smoke result summary that exposes schema keys only.
- Smoke-test plan document.

### Boundaries

- No live Kiwoom REST call was made.
- No live WebSocket connection was opened.
- No real transport was added.
- No order endpoint or executable order TR path was added.
- The next implementation step is a pre-check script skeleton that exits before
  any network transport.

## 2026-07-11: US Read-only Precheck Script Skeleton

### Added

- `backend/scripts/verify_us_readonly_precheck.py`.
- Local-only guard checks for:
  - smoke confirmation phrase.
  - `read_only=true`.
  - `order_enabled=false`.
  - `liveProvider=true`.
  - app credential presence as configured booleans only.
  - order TR blocking.
  - safe output example using schema keys only.

### Boundaries

- The script does not call Kiwoom.
- The script does not import or use HTTP/WebSocket clients.
- The script does not print real credentials or account values.
- The script exits before any transport layer.

## 2026-07-11: US Read-only Fake Smoke Runner

### Added

- `backend/scripts/run_us_readonly_smoke.py`.
- Default runner behavior blocks because live transport is not implemented.
- `--fake` mode runs through the smoke TR order using `FakeKiwoomUsTransport`.
- Safe output remains limited to TR ID, return code, return message, and schema
  key names.

### Boundaries

- No real Kiwoom REST call was made.
- No real WebSocket connection was opened.
- No real app key, secret, token, or account number was printed.
- No order endpoint or order execution path was added.

## 2026-07-11: US HTTP Read-only Transport Model

### Added

- `backend/trading_engine/providers/kiwoom_us/http_transport.py`.
- `PreparedUsHttpRequest` model for URL, method, headers, body, and timeout.
- `KiwoomUsHttpReadOnlyTransport` with injected sender support only.
- Tests for:
  - missing sender blocking.
  - missing token blocking before sender execution.
  - read-only wire request shape creation.
  - non-zero Kiwoom return code handling.
  - no direct `httpx`, `requests`, or `websockets` import.

### Boundaries

- No concrete HTTP sender was implemented.
- No real Kiwoom REST call was made.
- No real WebSocket connection was opened.
- No order endpoint or order execution path was added.
- The model can prove request construction and response mapping locally, but
  live calls still require a separately reviewed sender implementation and
  explicit read-only smoke-test approval.

## 2026-07-11: US Pre-live Smoke Gates And HTTP Sender

### Added

- Extra pre-live HTTP sender gates:
  - `KIWOOM_US_HTTP_SENDER_ENABLED=true`.
  - `KIWOOM_US_HTTP_SENDER_CONFIRM=I_UNDERSTAND_US_READ_ONLY_HTTP_SENDER`.
  - `KIWOOM_US_ACCESS_TOKEN` presence.
- `KiwoomUsUrllibHttpSender` concrete sender using Python stdlib `urllib`.
- `run_us_readonly_smoke.py --live-http` path guarded by:
  - base smoke confirmation.
  - read-only mode.
  - order disabled.
  - live provider enabled.
  - extra HTTP sender confirmation.
  - token presence.

### Boundaries

- No live Kiwoom smoke test was executed.
- No real app key, secret, token, or account number was written or printed.
- No order endpoint or order execution path was added.
- Tests use fake opener objects only, so no real HTTP/WebSocket call is made.

## 2026-07-11: US Daily Account Return TR

### Added

- `usa21670` as a US read-only PnL/account TR.
- Request helper for `from`/`to` date fields in `YYYYMMDD` format.
- Response schema and mapper for `result_list` rows:
  - `base_dt`.
  - `stk_evlta`.
  - `pl_amt`.
  - `dvid_amt`.
  - `cmsn_tax`.
  - `acum_pl_amt`.
  - `pymn_amt`.
  - `dast`.
  - `dly_amt`.
  - `sell_amt`.
  - `buy_amt`.
  - `prft_rt`.
  - `frgn_stk_outq_amt`.
  - `frgn_stk_inq_amt`.
  - `ina_amt`.
  - `exrt`.

### Boundaries

- Official Kiwoom Postman collection confirms `usa21670` as `POST /api/us/acnt`.
- No live Kiwoom request was executed.
- Raw response values remain out of logs and documents.
- The TR is read-only and has no order execution path.

## 2026-07-11: Kiwoom CLI Profile Credential Loader

### Added

- `kiwoomcli` profile/keyring credential source for US read-only smoke tooling.
- Profile selection through:
  - `KIWOOM_US_CREDENTIAL_SOURCE=kiwoomcli`.
  - `KIWOOM_US_PROFILE` or `KIWOOM_PROFILE`.
- Local profile settings, OS keyring credentials, and token-cache metadata are
  read without printing app key, secret, token, account number, or raw cache
  contents.
- Python 3.9-compatible UTC handling for local test runtime.

### Boundaries

- No live Kiwoom REST call was executed.
- No WebSocket connection was opened.
- No order endpoint or order execution path was added.
- Credential output remains limited to configured/not-configured booleans.

## 2026-07-11: US Single-TR Smoke Guard

### Added

- `run_us_readonly_smoke.py --tr <TR>` option.
- Single-TR smoke selection limited to the approved read-only smoke plan.
- Order TRs such as `ust20000` are rejected before transport execution.
- Safe selected-TR output so the operator can confirm only one TR will run.

### Boundaries

- No live Kiwoom REST call was executed.
- No WebSocket connection was opened.
- No order endpoint or order execution path was added.

## 2026-07-11: US Read-only Live HTTP Smoke ust21110

### Result

- Executed one real Kiwoom US read-only HTTP smoke TR:
  - `ust21110`.
- Output was limited to:
  - TR ID.
  - return code.
  - return message.
  - schema key names.
- Safe result:
  - return code `0`.
  - return message indicates lookup completed.
  - schema keys included `ch_uncla`, `etc_loana`, `krw_entra`, and
    `result_list`.

### Boundaries

- No raw response JSON was saved.
- No account number, token, cash balance, holding name, or holding symbol was
  printed.
- No order TR was executed.
- No WebSocket connection was opened.
- No order endpoint or order execution path was added.

## 2026-07-11: US Read-only Live HTTP Smoke Expansion

### Result

- Executed additional real Kiwoom US read-only HTTP smoke TRs with safe output:
  - `ust21120`: success.
  - `ust21650`: success.
  - `usa21670`: success.
- `usa21670` was corrected to use the live-required request body fields:
  - `from`.
  - `to`.
- `usa21670` response mapper still accepts both documented/observed result
  list spellings and row key variants:
  - `result_list`.
  - `result_lsit`.
  - `wo_*` row keys.
  - non-prefixed row keys.
- `ust21630` reached Kiwoom but returned a safe no-data response for the tested
  account/date context.

### Boundaries

- No raw response JSON was saved.
- No account number, token, cash balance, holding name, or holding symbol was
  printed.
- No order TR was executed.
- No WebSocket connection was opened.
- No order endpoint or order execution path was added.

## 2026-07-12: US Read-only Backdata FastAPI Endpoints

### Added

- Protected FastAPI endpoints for US stock read-only backdata:
  - `GET /api/us/account/cash`
  - `GET /api/us/account/valuation`
  - `GET /api/us/account/realized-pnl`
  - `GET /api/us/account/period-return`
  - `GET /api/us/account/daily-returns`
- `UsAccountService` bridge from FastAPI to the existing Kiwoom US read-only
  provider.
- Mock-mode responses by default.
- Live-mode guard behavior that refuses to fall back to mock data when required
  US read-only credentials or token are missing.
- Pydantic response schemas for generic US read-only TR summaries and daily
  account return rows.

### Boundaries

- No order endpoint was added.
- No WebSocket endpoint was added.
- No frontend dashboard wiring was added in this step.
- No Kiwoom live call was executed by the automated tests.
- Actual credential values remain outside Git.

## 2026-07-16: US One-share Order MVP Guardrails

### Added

- Runtime order lock concept for the local US order MVP.
- Order dashboard emergency lock panel.
- Fixed pre-order checklist for removing the runtime lock.
- One-share candidate selection flow from US quote/chart view to order precheck.
- Unified one-share candidate API based on read-only US ranking TRs:
  - `usa20910`.
  - `usa20930`.
  - `usa20530`.
  - `usa01980`.
- Precheck panel showing:
  - symbol and exchange.
  - side and trade type.
  - quantity and maximum quantity.
  - estimated order notional and maximum notional.
  - `ust31490` orderable quantity and amount.
  - server-side block reasons.

### Current Runtime State

- The runtime order lock is expected to remain active before any real order
  test.
- The live order path is not automatically triggered by quote, chart, ranking,
  condition search, or paper auto-trade logic.
- Dashboard navigation can prefill order inputs, but final submission still
  requires server gates, precheck, confirmation text, final dialog, and lock
  removal.

### Boundaries

- No actual order was submitted in this task.
- No order amend/cancel endpoint was added.
- No app key, secret key, token, account number, raw response, balance, or
  holding value was recorded.
- Runtime lock removal remains a manual, time-limited operator action.

## 2026-07-21: US Strategy Core And Backtest Foundation

### Added

- Python strategy core for:
  - `US_5M_TREND_PULLBACK`.
  - `US_1M_VOLUME_BREAKOUT`.
- Indicator helpers for EMA, VWAP, ATR, spread, RVOL, trade value, and quote
  freshness.
- ET session handling with DST via `America/New_York`.
- Candle normalization by timestamp with duplicate candle merge.
- Condition candidate manager requiring `usa20280` list load before `usa20290`
  realtime registration.
- Risk-based order quantity calculation with default dry-run-safe settings.
- SQLite `us_strategy_decisions` table for condition/signal audit.
- Local backtest harness that reuses the same strategy decision functions.

### Verification Scope

- No Kiwoom HTTP call was executed.
- No WebSocket connection was opened.
- No live order was submitted.
- No key, token, account number, raw response, or order secret was added.
- Live order remains disabled by default.

## 2026-07-22: Official US Order Contract Alignment

### Corrected

- Compared the local order path with the official Kiwoom GitHub Postman
  collection.
- Corrected `ust31490` to use `stk_code` instead of `stk_cd`.
- Corrected `ust20000`/`ust20001` wire bodies to use the documented
  `stk_code`, `ord_qty`, `ord_uv`, and `trde_tp` fields.
- Corrected `ust21510` follow-up requests to use its documented account-query
  contract. A later PDF contract review superseded the earlier `ust21070`
  assumption.
- Kept response mapping compatible with both `stk_code` and older fixture
  field names.

### Verification Scope

- Contract and regression tests only.
- No Kiwoom HTTP order was sent.
- No backend restart or runtime lock change was performed.

## 2026-07-22: Condition Search And Pullback Entry Reconciliation

### Implemented

- Reconciled stale armed buy records against sellable holdings from
  `ust21070`, while preserving records when the holdings lookup fails.
- Made the five-minute three-bearish/one-bullish reversal pattern mandatory.
- Made the one-minute two-bearish/maximum-one-percent pullback pattern
  mandatory.
- Connected strategy candidate selection to the ordered condition-search flow
  `usa20280 -> usa20281 -> usa20290`, followed by `usa20291` cleanup.
- Kept the existing strategy-to-precheck-to-`ust20000` execution boundary and
  added regression coverage for the condition and reconciliation gates.

### Verification Scope

- Python compile verification passed.
- Backend and trading-engine test suite: 239 passed.
- No actual Kiwoom HTTP or WebSocket request was made.
- No live order was submitted.
- The backend was restarted with automated trading OFF and the runtime order
  lock reapplied; live account revalidation remains an explicit operator step.

## 2026-07-22: Pullback Data-path Stabilization

### Implemented

- Coalesced concurrent pullback-plan requests behind one backend load with a
  two-second cache to reduce duplicate Kiwoom ranking, condition, and chart
  requests.
- Sorted minute-chart rows by `cntr_tm` and safely merged duplicate timestamps.
- Excluded the current unfinished one-minute or five-minute candle from entry
  pattern evaluation.
- Changed strategy UI wording from a failure presentation to a normal entry
  waiting state while retaining all mandatory entry gates.

### Verification Scope

- Backend and trading-engine tests: 242 passed.
- Frontend tests: 9 passed.
- Python compile, TypeScript check, Vite build, and diff validation passed.
- Backend restarted with automated trading OFF.
- The runtime order lock remains unlocked from the prior explicit operator
  request; automated trading still requires a new authenticated session and an
  explicit ON action.
- No live order was submitted during this work.

## 2026-07-22: Official ust21070 Holdings Contract Correction

### Corrected

- Verified the `ust21070` contract against pages 718-720 of the supplied
  Kiwoom REST API PDF.
- Replaced the invalid request body `stex_tp=000030, stk_code=...` with the
  documented optional `stex_tp=ND/NY/NA` and `stk_cd` fields.
- The default all-holdings request now sends empty `stex_tp` and `stk_cd`
  values as shown in the official request example.

### Safety

- This is a read-only holdings-query correction.
- No order TR or order guard was changed.

## 2026-07-22: US Premarket Candidate Monitoring

### Implemented

- Kept `usa20290` condition-search registration open in a backend monitor and
  deferred `usa20291` cleanup until monitor shutdown or session replacement.
- Applied realtime condition include/delete events to the in-memory candidate
  set instead of treating registration as a one-response request.
- Added a premarket fallback from empty `usa20910` results to read-only
  `usa01980` and `usa20530` rankings.
- Added explicit ET strategy-session criteria. Premarket candidates can be
  displayed and monitored, but one-minute and five-minute entry readiness
  remains blocked until their regular-session windows.

### Verification Scope

- Backend and trading-engine tests: 246 passed.
- No live order was submitted during implementation or tests.

## 2026-07-22: AI Strategy Library

- Added `AI 고유동성 5분봉 눌림목` as a third independent strategy entry.
- Converted the recommendation into editable universe, signal, order, exit,
  and risk blocks backed by the documented Kiwoom market-data TRs.
- Changed the strategy list to one strategy per row with three-item paging so
  future generated strategies can accumulate without expanding one panel.
- The AI strategy uses live-data criteria and defaults OFF.

## 2026-07-22: AI Strategy Live-Pipeline Promotion

- Removed the dedicated `AI_STRATEGY_VALIDATION_REQUIRED` blocker.
- Kept the AI strategy OFF by default; an authenticated operator must enable it.
- Kept shared runtime, order policy, quantity, notional, account precheck, and
  entry-signal gates unchanged.
- Changed missing same-time RVOL history from a permanent critical blocker to
  an explicit advisory unavailable criterion. No synthetic RVOL is used.
- No live order was submitted while making or testing this change.

## 2026-07-22: US Daily Change-Rate Ranking

- Replaced the generic price-spike dashboard tab with the official `usa20910`
  current-day change-rate ranking.
- Added deterministic descending change-rate sorting and rank normalization.
- Strategy cards now show the actual safe empty-candidate reason instead of a
  single generic waiting message.
- No live order was submitted during implementation or verification.

## 2026-07-22: Strategy-Builder Pipeline Consolidation

- Removed the standalone surge-candidate dashboard card and its dedicated API,
  response models, evaluator helpers, client method, and tests.
- Retained the canonical automated-entry flow: `usa20910` ranking, Kiwoom
  `usa20280/usa20281/usa20290` condition membership, `usa06011` strategy
  candles, FE/FT realtime checks, `ust31490` precheck, and guarded order TRs.
- No strategy condition, order safeguard, or live-order transport was bypassed.
# 2026-07-24 - Runtime Mock/Paper removal

- Removed frontend Mock adapters, Mock data source, Paper summary/timeline UI, Paper analytics tab, and Mock watchlist request.
- Removed backend Mock account/token/watchlist responses, Mock realtime routes, Paper event API/store, Paper runner mode, and legacy Paper broker engine.
- Strategy builder now stores `executionMode=live`; actual orders remain controlled by the existing server order policy, runtime lock, session, strategy, and risk checks.
- Removed local `paper_fills` and `paper_auto_trade_events` tables and added cleanup for existing databases.
- Runtime defaults to `KIWOOM_MODE=live`; missing sessions or API failures return explicit errors without fabricated fallback data.
- Verification: Python compileall passed, backend/trading engine pytest 234 passed, frontend TypeScript passed, Vitest 9 passed, Vite build passed.
- No Kiwoom order request or live market/account API request was made during this cleanup.

# 2026-07-24 - US Premarket Entry Policy

- Extended the existing one-minute and five-minute strategy pipeline to the 04:00-09:29 ET premarket window behind `KIWOOM_US_PREMARKET_ENTRY_ENABLED`.
- Premarket entry reuses the guarded `ust20000` path but creates only a limit ticket (`trde_tp=00`) from a fresh FT best ask.
- Missing/stale orderbook data or a spread above 0.15% keeps the strategy waiting and prevents ticket submission.
- Regular-session market-order behavior was not changed.
- No live Kiwoom request or order was sent during implementation.

# 2026-07-25 - Strategy-specific US Condition Search

- Added saved Hero Global condition sequence/name fields to strategy-builder
  configurations with a non-destructive SQLite column migration.
- Connected each strategy to its own official US condition-search flow:
  `usa20280` list, `usa20281` initial result, `usa20290` realtime registration,
  and `usa20291` cleanup.
- Changed candidate evaluation so each strategy receives only the symbols from
  its selected condition sequence instead of sharing one global result.
- Added a condition selector to the strategy builder and displayed the selected
  condition name and membership state on strategy cards.
- The API exposes only condition names, sequence identifiers, and safe mapped
  matches; it does not expose broker credentials, tokens, account values, or raw
  WebSocket payloads.
- No Kiwoom API request or order was sent during implementation or tests.

# 2026-07-25 - Strategy Toggle / Condition Monitor Link

- Connected each strategy ON action to its selected Kiwoom US condition
  monitor and exposed connection, selected formula, match count, and safe error
  state on the strategy card.
- Connected OFF to condition cleanup while preserving a shared monitor until
  the last enabled strategy using the same condition is disabled.
- Kept live-order configuration, runtime lock, account precheck, strategy
  signal, and risk gates independent from condition-search activation.
- Automated verification used fake condition responses only. No Kiwoom API or
  order request was sent.

# 2026-07-27 - Kiwoom Session Expiration Recovery

- Diagnosed quote, US market summary, and account endpoint failures as an
  expired Kiwoom access token rather than a frontend or CORS failure.
- Corrected `expires_dt` parsing from Kiwoom local KST to UTC and prevented an
  expired request-context session from being reused by background services.
- Recreated the local dashboard session from the stored macOS Keychain CLI
  profile and verified the Home market summary and Quotes ranking data.
- Verification: backend/trading-engine pytest 244 passed. Read-only market and
  account requests were used for recovery; no order request was submitted.

# 2026-07-30 - Capital Reservation And Open-order Reconciliation

- Added persistent allocation cycles and buy reservations scoped by hashed
  account identity and US market date.
- Added conservative allocation limits for four symbols and two tranches
  without enabling concurrent live entries.
- Added exact buy-order fill reconciliation through `ust21510`.
- Added official `ust21050` open-order reconciliation. Explicit cancellation
  releases an unfilled reservation, while missing broker rows remain blocked as
  uncertain.
- Required documented `ust31490` no-margin quantity, amount, and USD currency
  fields before buy precheck can pass.
- Verification: backend/trading-engine pytest 276 passed and compileall passed.
- No Kiwoom API request, WebSocket connection, order submission, server
  restart, commit, or push was performed.

# 2026-07-30 - Read-only Order-state Contract Validation

- Added a confirmation-gated read-only audit for `ust21050` and `ust31490`.
- A controlled production read-only check confirmed that `ust31490` requires
  `stex_tp`, `stk_cd`, and `uv`. This supersedes the earlier assumption that
  the symbol field was `stk_code`.
- Confirmed the required `min_ord_alowq`, `min_ord_alowa`, and `crnc_code=USD`
  response shape without printing their values.
- Confirmed `ust21050` safely reports the no-data state when no open order
  exists.
- No token, account number, balance, raw response, or order was printed or
  submitted.

# 2026-07-30 - F4/F5 Recovery Mapper Foundation

- Added the official F4 order-confirmation and F5 fill channels to the provider
  inventory as blocked order-related streams.
- Added a network-free mapper for order number, symbol, side, status, quantity,
  price, fill, holding, time, and currency fields.
- Explicitly drops account number field `9201` and unknown field values.
- F4/F5 live registration remains blocked; no WebSocket connection or order
  request is enabled by this mapper.
- Verification: compileall and diff validation passed; backend/trading-engine
  pytest reported 288 passed.

# 2026-07-30 - F4/F5 Restart Recovery Replay

- Added persistent partial-fill quantity and last broker status to allocation
  reservations, including migration of an existing SQLite allocation schema.
- Added an idempotent event ledger keyed by a hash of safe F4/F5 event fields.
- Added offline replay rules:
  - F5 partial fill remains submitted and blocks duplicate entry.
  - F5 complete fill marks the tranche filled.
  - Confirmed F4 cancellation/rejection releases an unfilled reservation.
  - Partial fill followed by confirmed cancellation remains filled.
  - Unmatched and sell-side events cannot mutate a buy reservation.
- Verified restart, duplicate replay, partial fill, full fill, cancellation,
  rejection, unmatched order, sell-side event, and account-data exclusion with
  temporary SQLite databases.
- Verification: compileall and diff validation passed; backend/trading-engine
  pytest reported 295 passed.
- This phase does not register F4/F5, open a WebSocket, restart the server, or
  submit an order.

# 2026-07-30 - Controlled F4/F5 Monitor Wiring

- Added a separate F4/F5 order-state monitor for submitted allocation
  reservations.
- Kept the monitor OFF by default and required a dedicated enable flag and
  confirmation phrase before a connection can start.
- Registration packets contain only symbol, exchange, F4, and F5 fields.
- Parsed events are applied to the idempotent allocation recovery ledger and
  then trigger the existing `ust21510`/`ust21050` REST reconciliation callback.
- A configured but disconnected monitor blocks additional auto-entry attempts
  while submitted reservations exist.
- A failed REST reconciliation callback also blocks new entries until the
  broker state can be checked again.
- Added fake-WebSocket tests for login, registration, PING, account-field
  stripping, fill application, REST callback wiring, and sanitized connection
  failure status.
- Verification: compileall and diff validation passed; backend/trading-engine
  pytest reported 304 passed.
- No production WebSocket connection, server restart, or order request was
  performed.

# 2026-07-30 - F4/F5 Monitor Diagnostics

- Added an authenticated read-only diagnostic endpoint for the F4/F5
  order-state monitor.
- Added the monitor state to the Strategy dashboard with five-second refresh.
- The response exposes only connection state, aggregate monitored-symbol
  count, channel IDs, safe error classes, and update counters.
- Monitored symbols, account identifiers, access tokens, and raw broker
  payloads are not returned.
- This change does not enable the monitor or submit an order.

# 2026-07-30 - F4/F5 Reconnect Hardening

- Required an explicit successful LOGIN response before F4/F5 registration.
- Added bounded exponential reconnect delays from one second up to 30 seconds.
- Added last connection, heartbeat, reconnect count and next retry diagnostics.
- Added tests for malformed login responses, delay bounds and recovery after
  consecutive connection failures.
- The monitor remains disabled by default and no production WebSocket or order
  request was made.

# 2026-07-30 - F4/F5 Observation Preflight

- Added an authenticated local-only preflight for controlled F4/F5 observation.
- It verifies monitor configuration, valid live session, runtime order lock,
  and submitted reservation presence.
- The Strategy dashboard refreshes preflight status every five seconds.
- The response contains counts and reason codes only; symbols, order numbers,
  account identifiers and credentials are excluded.
- Preflight does not start a WebSocket or call an order endpoint.

# 2026-07-30 - Kiwoom Session and Monitor Lifecycle

- Kiwoom login now resumes the default-disabled F4/F5 monitor only when its
  explicit configuration and persisted submitted-order prerequisites pass.
- Optional monitor recovery failure no longer prevents account login.
- Added an authenticated logout endpoint that revokes the backend Kiwoom
  session and stops the order-state monitor.
- Frontend logout notifies the backend first and always clears its local token
  and React Query cache afterward, including backend-offline failures.
- Added backend and frontend coverage for authentication, session revocation,
  monitor stop, login recovery, and logout notification.

# 2026-07-30 - Order-state Continuation Safety

- Preserved Kiwoom `cont-yn` and `next-key` response headers in the US
  read-only HTTP transport without placing them in response data.
- Added bounded continuation retrieval for `ust21050` and `ust21510`.
- Merged exact duplicate rows conservatively across page boundaries.
- Repeated keys, missing keys, and continuation beyond 20 pages now fail
  closed so submitted reservations remain unresolved.
- Added network-free tests for response-header capture, request-header
  forwarding, page merging, duplicate handling, and repeated-key rejection.

# 2026-07-30 - Delayed Broker-state Fail-closed Handling

- Added a configurable five-second minimum interval for `ust21050` and
  `ust21510` submitted-order reconciliation.
- A submitted reservation now blocks all additional auto-entry candidate
  evaluation until its fill, cancellation, or rejection is confirmed.
- After a configurable 30-second uncertainty window, the blocker changes from
  pending confirmation to confirmation timeout while the reservation remains
  intact.
- F4/F5 events can force an immediate REST cross-check without waiting for the
  normal interval.
- Added tests for rate limiting, timeout behavior, reservation retention, and
  candidate-scan suppression.

# 2026-07-30 - Restart-safe Order Confirmation State

- Persisted submitted time, last reconciliation time, safe reconciliation
  result code, and attempt count on allocation reservations.
- Replaced process-memory throttling and timeout tracking with SQLite-backed
  state so a backend restart cannot reset the confirmation window.
- Existing submitted reservations are migrated conservatively using their last
  update time; invalid legacy timestamps remain blocked as pending.
- Added restart and migration coverage without storing raw broker payloads,
  credentials, tokens, or account numbers.

# 2026-07-31 - Restart Recovery Integration Coverage

- Combined persisted confirmation metadata with the existing read-only
  `ust21510` and `ust21050` recovery flow.
- Verified that a partial fill followed by confirmed remainder cancellation
  survives a store restart and becomes one filled tranche.
- Verified that a confirmed unfilled rejection after restart releases reserved
  capital and allows the allocation layer to evaluate the next symbol.
- All scenarios use local fixtures only and make no broker HTTP, WebSocket, or
  order request.

# 2026-07-31 - Confirmed Sell Allocation Release

- Added a persistent allocation-reservation link to automatic buy-attempt
  records, including migration for existing local SQLite databases.
- Added the terminal `filled -> closed` allocation transition.
- A linked allocation closes only after `ust21510` confirms the full automatic
  sell quantity. Partial and unresolved exits retain the position slot.
- Added restart coverage proving that one closed symbol releases its slot while
  another filled symbol remains active.
- No broker request or live order was executed during this change.

# 2026-07-31 - Sequential Multi-symbol Entry

- Removed the legacy `OPEN_ARMED_BUY_EXISTS` global entry blocker.
- Existing positions continue automatic exit monitoring while new candidates
  can proceed to allocation evaluation.
- Preserved one submitted order per runner tick and global blocking while any
  submitted reservation is awaiting broker confirmation.
- The persisted allocator remains authoritative for maximum four symbols,
  maximum two tranches per symbol, reserved cash, and zero-cash pausing.
- Added coverage for a second symbol receiving position slot two while the
  first symbol remains under exit monitoring.
- No broker request or live order was executed during this change.

# 2026-07-31 - Atomic Partial-fill Recovery

- Combined terminal REST reconciliation metadata and reservation status into
  one SQLite transaction.
- A partially filled buy followed by confirmed remainder cancellation now
  stores the actual filled quantity instead of the original requested
  quantity.
- Added conservative support for a terminal cancellation row with zero
  remaining quantity even when a separate canceled-quantity field is absent.
- Added restart coverage for actual partial quantity, broker status, tranche
  retention, and zero pending symbols.
- No broker HTTP, WebSocket, or order request was made.

# 2026-07-31 - Order-state Read-only Audit Expansion

- Expanded the shape-only audit from `ust21050` and `ust31490` to include
  `ust21510` fills and `ust21070` holdings.
- Audit output includes only TR IDs, response schema keys, row-presence flags,
  and required-field checks. It excludes symbols, order numbers, quantities,
  prices, account identifiers, tokens, and credentials.
- Added a network-free test proving the audit invokes only the four read-only
  TRs and never calls an `ust20000`-series order TR.
- The live F4/F5 observation was not started because the restarted dashboard
  currently has no valid Kiwoom session or submitted reservation.

# 2026-07-31 - Production Order-state Contract Verification

- Restored a backend Kiwoom session from the current local CLI profile without
  printing or persisting its credentials.
- Confirmed the F4/F5 monitor preflight is configured and the runtime order
  lock is present. Observation remained disconnected because there was no
  submitted reservation to observe.
- Corrected `ust21510` to the production-verified `stex_tp=ND/NY/NA` and
  `stk_cd` request shape. The downloaded current API specification agrees with
  this shape; an older Postman example uses incompatible legacy field names.
- Completed a production read-only shape audit for `ust21050`, `ust21510`,
  `ust21070`, and `ust31490`. No `ust20000`-series order TR, order endpoint, or
  order WebSocket connection was invoked.
- Audit output remained schema-only and excluded symbols, account values,
  order identifiers, tokens, and credentials.

# 2026-07-31 - Production Account Mapper Audit

- Added a CLI-profile-aware, read-only account response audit for `ust21110`,
  `ust21120`, `ust21630`, `ust21650`, and `usa21670`.
- The audit reports only field names, list shape, and contract booleans. It
  excludes all cash, valuation, profit/loss, symbol, account, and credential
  values.
- Production responses for cash, valuation, period return, and daily account
  return matched the current specification. Same-day realized profit/loss
  returned the documented no-data state.
- No order TR, order endpoint, or WebSocket connection was invoked.

# 2026-07-31 - FE/FT Reconnect and Stale-price Safety

- Added sanitized FE/FT connected, heartbeat, reconnect-count, and next-retry
  state to the backend quote monitor.
- Replaced the fixed reconnect delay with bounded exponential backoff capped at
  30 seconds. A reconnect repeats Kiwoom login and the complete FE/FT symbol
  registration.
- Tightened quote-stream login validation so an unexpected login envelope
  fails closed before registration.
- Automatic exit evaluation no longer consumes a realtime price older than ten
  seconds. It falls back to the read-only `usa10100` quote path.
- Added network-free tests for reconnect, resubscribe, bounded delay, and stale
  realtime price rejection. No order request was made.
- Restarted the local backend on the updated code, restored the current CLI
  profile session, and completed a controlled production FE/FT observation.
  The monitor connected with 20 registered symbols, a heartbeat was observed,
  and no reconnect or stream error was reported. The runtime order lock stayed
  present throughout.

# 2026-07-31 - Locked Auto-trade Observation Mode

- Separated continuous strategy-candidate evaluation from live order runtime
  enablement.
- Added authenticated observation enable/disable endpoints and exposed the
  state in the strategy dashboard as `후보 감시`.
- The observation runner evaluates candidate plans only. It does not execute
  order precheck, allocation reservation, automatic exit, or order transport.
- Added tests proving the runtime lock remains present and live entry/exit
  stages are not called in observation mode.
- Full verification passed with 338 backend tests and 10 frontend tests. No
  live order request was made.
- Added the latest observation action, strategy, safe symbol/exchange label,
  blocker codes, and timestamp to runtime diagnostics. The strategy dashboard
  now presents this snapshot as the most recent candidate evaluation.
- Added deduplicated observation-change journaling to the existing auto-trade
  event list. The dashboard can now show candidate-condition changes without
  writing an event on every runner interval.
- Added a read-only runner mode and restarted the local dashboard with order
  execution disabled. Production read-only data observation continued while
  the order feature flag, read-only policy, and runtime lock all blocked order
  submission.
- Fixed a macOS process-shutdown race in the local start script that could
  abort restart when a stale PID disappeared during its working-directory
  check.
- Added a read-only strategy observation summary API and dashboard panel.
  Strategy totals count deduplicated condition-state changes, split ready and
  waiting changes, count unique candidates, and show the top failed criteria.
  No order path or broker payload is used by this summary.
- Added opt-in read-only observation restoration after backend restart. The
  local start script enables it by default while keeping live orders disabled;
  the backend environment example remains fail-closed with the flag set to
  false.
- Sequenced local startup so the frontend is launched only after the backend
  health endpoint responds. This removes transient proxy connection failures
  during restart without adding retry traffic to application queries.
- Clarified F4/F5 preflight state across the API and strategy dashboard. No
  submitted reservation is now presented as a normal `no_target` state rather
  than a monitor error, and no WebSocket connection is attempted.
- Added FE/FT observation-quality aggregation and a strategy dashboard panel.
  It reports market session, condition-candidate count, fresh coverage,
  missing/stale symbols, and sanitized receive-delay statistics without making
  any additional broker request.

# 2026-08-01 - Token Endpoint Redirect Diagnosis

- Confirmed the saved real Kiwoom CLI profile and macOS Keychain credentials
  are present without printing or persisting any credential value.
- The official token endpoint currently responds with HTTP 302 and redirects
  from the HTTPS token path to an HTTP start page instead of returning token
  JSON. The application does not follow this security downgrade.
- Token issuance now reports the safe diagnostic code
  `TOKEN_ENDPOINT_REDIRECT` before attempting to parse the redirect body.
- The local dashboard, backend health check, PIN-protected profile listing,
  read-only observation runner, and runtime order lock were verified after
  restart. Broker-authenticated reads remain unavailable until the official
  token endpoint returns a normal token response.
- No order TR, order endpoint, WebSocket order channel, credential value, or
  token value was used or exposed during diagnosis.
# 2026-08-12 - Live-order Readiness Audit Batch 1

- Measured the authenticated runtime order checklist: 1 of 9 gates currently
  passes (valid live CLI session); the remaining eight gates stay intentionally
  closed.
- Fixed the standalone read-only precheck to use kwcli's official
  `platformdirs` config/cache locations on Windows, matching the dashboard
  session loader.
- Allowed a valid CLI profile with OS-keyring App Key/Secret and no reusable
  token cache to pass the no-network credential precheck; token issuance still
  occurs only in the backend session flow.
- Completed a production read-only shape audit for `ust21050`, `ust21510`,
  `ust21070`, and `ust31490`. No order TR or order WebSocket connection was
  used.
- Full backend verification passed with 355 tests. Read-only mode, the disabled
  order flag, and the runtime order lock remained active.

# 2026-08-12 - Live-order Readiness Audit Batch 2

- Pinned the local safe runtime to the `NVDA` allowlist, a maximum quantity of
  one share, and a maximum notional of USD 500. The startup script continues
  to force read-only mode, disabled orders, a disabled auto-trade runner, and a
  disabled F4/F5 monitor.
- Runtime readiness increased from 1/9 to 4/9 because the symbol, quantity,
  and notional policy gates now pass. The five mutation-enabling gates remain
  closed.
- Ran an authenticated one-share NVDA buy precheck with the runtime lock still
  present. `ust31490` returned a valid USD response but reported insufficient
  orderable quantity and amount at the verification reference price.
- The final `ust20000` step remained blocked, and the order-history count was
  unchanged before and after precheck. Ten focused safety tests passed.

# 2026-08-12 - 50 Percent Cash Allocation Policy

- Added `KIWOOM_US_CAPITAL_USAGE_PCT=50` to the local safe runtime. This caps
  managed capital at half of the broker-reported orderable amount and preserves
  the other half as a cash reserve.
- The authenticated precheck now reports the usage percentage, managed amount,
  and reserve amount and blocks requests exceeding the managed half.
- Automatic allocation consumes the managed amount rather than the full
  broker orderable amount. Orders, the runner, and F4/F5 monitoring remain
  disabled by the local startup policy.
- Live read-only verification reported USD 0.52 as the symbol-specific
  orderable amount at the test reference price: USD 0.26 managed and USD 0.26
  reserved. One NVDA share was therefore not affordable.
- Order history was unchanged. All 355 backend and 16 frontend tests passed.

# 2026-08-12 - Cash Split Dashboard and Shared Quote Subscription

- Added a dashboard cash split showing the configured managed percentage and
  the preserved cash reserve using live read-only account data.
- Extended the FE/FT quote monitor with a bounded union subscription. Selected
  symbols and holdings are prioritized while strategy candidates preserve the
  existing subscription set, with the existing 20-symbol maximum retained.
- The authenticated realtime-window adapter accepts sanitized symbol/exchange
  pairs and starts only the read-only `FE` and `FT` channels. It never registers
  F4/F5 or calls an order endpoint.
- Production verification subscribed NVDA successfully: monitor running and
  connected, one fresh symbol, zero missing/stale symbols, and no stream error.
- All 357 backend and 16 frontend tests passed. Read-only mode, disabled
  orders, and the runtime order lock remained active.

# 2026-08-12 - Session Recovery and Realtime UI Verification

- Restored the saved real CLI profile after a full backend/frontend restart;
  direct OAuth token issuance and authenticated read-only account requests
  completed successfully without following a redirect.
- Verified the selected NVDA quote transitions from the REST fallback state to
  the FE/FT WebSocket stream after login. The observed stream was fresh with
  zero receive delay and no stale or missing selected-symbol data.
- Fixed double masking of the already-sanitized CLI account label. The header
  now preserves `****-1574 [위탁종합]` instead of masking the final Korean
  label characters a second time.
- Added regression coverage for pre-masked CLI labels and raw numeric account
  identifiers. Five focused session/realtime tests and fifteen order-blocking
  safety tests passed.
- No order TR, F4/F5 order channel, order endpoint, credential value, token, or
  raw account number was used or exposed. Read-only mode and the runtime order
  lock remained active.

# 2026-08-12 - Cost and FX-aware Backtest Runner

- Fixed the single-candidate backtester to preserve the original entry time,
  so its 30-minute time exit no longer moves forward on every candle.
- Split backtest costs into execution impact (spread plus slippage), broker
  commission, FX conversion cost, and total cost. Summaries now expose gross
  and net PnL in USD and optional net PnL in KRW using an explicitly supplied
  historical FX rate.
- Added `backend/scripts/run_us_strategy_backtest.py` for strict, local-only
  JSON input. It validates timezone-aware OHLCV rows, public symbol/exchange
  fields, candidate context, non-negative cost assumptions, and a positive FX
  rate before running the shared strategy decision code.
- No fabricated historical dataset or profitability claim was added. A real
  dataset with at least 61 prior candles per candidate event is still required
  before producing a strategy performance report or walk-forward result.
- Twelve focused strategy/backtest tests and fifteen order-blocking safety
  tests passed. No broker request, order endpoint, credential, token, account
  number, or runtime order unlock was used.

# 2026-08-13 - Read-only Minute-chart Dataset Collection

- Connected the existing bounded continuation reader to `usa06011` historical
  minute-chart collection without changing the normal one-page dashboard chart
  path or any order-state query.
- Added a local dataset collector that exports only normalized ET OHLCV candles
  and date/KRW-per-USD pairs. Account valuation, PnL, account identifiers,
  credentials, and tokens are never written to the dataset.
- Added explicit partial-coverage metadata. A page-limited research export is
  retained with `continuationComplete=false` instead of being mistaken for a
  complete history; normal completeness-sensitive call sites still fail closed.
- Live read-only NVDA verification collected three continuation pages and 300
  one-minute candles for one US trading date. The account daily-return TR had
  no FX row for that date, so the dataset correctly records the missing FX date
  rather than substituting a fabricated or current rate.
- Added optional strict `date,krwPerUsd` CSV import for an authoritative
  historical FX source, plus an explicit single-rate option for controlled
  assumptions. The two inputs are mutually exclusive.
- Seventeen collector/backtest tests and fifteen order-blocking safety tests
  passed. No order TR, order endpoint, or order WebSocket channel was used.

# 2026-08-13 - Official FX Enrichment and Look-ahead Removal

- Added an HTTPS-only downloader for the Federal Reserve H.10/FRED `DEXKOUS`
  daily series. Its unit is KRW per USD and the normalized local CSV contains
  only `date,krwPerUsd`.
- Downloaded five official observations for the requested August 2026 window.
  The NVDA dataset's August 12 candle date used the latest observation known on
  or before that date, with the original source date and carry-forward days
  recorded. A future observation is never backfilled into an earlier trade date.
- Added a local FX enricher so an already collected chart dataset can receive
  official FX data without issuing another Kiwoom token or chart request.
- Rebuilt mutable backtest candidate fields at every candle boundary using only
  the known window: last price, session open/high, cumulative volume, trade
  value, quote timestamp, and proportional spread. A regression fixture that
  previously entered using future 3.2%/2.1M-volume values now correctly produces
  zero trades.
- The existing 300-candle NVDA dataset now has one covered FX date and zero
  missing FX dates. It remains explicitly partial because continuation pages
  exist beyond the configured three-page research sample.
- No order TR, order endpoint, F4/F5 channel, credential, token, account value,
  or runtime unlock was used.

# 2026-08-13 - Resume-safe Batch Collection and Walk-forward Gate

- Added a manifest-driven multi-symbol/multi-period dataset batch collector.
  Valid existing outputs are skipped, failures are recorded by safe exception
  class, and remaining items continue. A Kiwoom session is created lazily only
  when an uncached item actually needs collection.
- Added an expanding-window walk-forward report with chronological sorting,
  strictly earlier training windows, four default out-of-sample folds, and a
  mandatory 500-trade evidence threshold.
- Below 500 trades the report returns `insufficient_sample`, the exact trade
  shortfall, and `profitabilityClaimAllowed=false`; aggregate OOS profitability
  fields remain null rather than presenting an underpowered result.
- Verified the current NVDA dataset is safely skipped by a resumed batch without
  opening a new broker session. Its current completed-trade evidence is zero, so
  the walk-forward report records a 500-trade shortfall and makes no profitability
  claim.
- Twenty-three focused backtest/batch tests passed before integration, followed
  by the full regression suite. No order TR, order endpoint, F4/F5 channel, or
  runtime unlock was used.
