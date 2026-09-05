# US Stock Kiwoom TR Inventory

## Sources

- Google Sheet: `kiwoom_auto_trading_roadmap`, tab `05_API_TR관리`, range `A1:G20`.
- Local PDF: `키움 REST API 문서.pdf`.

The sheet was used as the project priority source. The PDF was used to confirm
endpoint paths, request body keys, and whether each TR is REST or WebSocket.

## Phase 3 Read-only Account TRs

| TR | Purpose | Endpoint | Status |
| --- | --- | --- | --- |
| `ust21110` | Overseas stock cash | `/api/us/acnt` | read-only builder |
| `ust21120` | Currency cash and securities valuation | `/api/us/acnt` | read-only builder |
| `ust21150` | Daily US stock order/fill history | `/api/us/acnt` | read-only builder |
| `ust21510` | Today US stock order/fill check | `/api/us/acnt` | read-only builder |
| `ust21630` | Today realized PnL | `/api/us/acnt` | read-only builder |
| `ust21650` | Period return status | `/api/us/acnt` | read-only builder |

## Phase 4 Realtime TRs

| TR | Purpose | Endpoint | Status |
| --- | --- | --- | --- |
| `FE` | US stock realtime last price | `/api/us/websocket` | REG packet builder |
| `FT` | US stock 10-level order book | `/api/us/websocket` | REG packet builder |

## Phase 5 Condition Search TRs

| TR | Purpose | Endpoint | Status |
| --- | --- | --- | --- |
| `usa20280` | Condition-search list | `/api/us/websocket` | request builder |
| `usa20281` | Normal condition search | `/api/us/websocket` | request builder |
| `usa20290` | Realtime condition search | `/api/us/websocket` | request builder |
| `usa20291` | Realtime condition clear | `/api/us/websocket` | request builder |

## Explicitly Blocked Order TRs

| TR | Purpose | Endpoint | Status |
| --- | --- | --- | --- |
| `ust20000` | US stock buy order | `/api/us/ordr` | blocked |
| `ust20001` | US stock sell order | `/api/us/ordr` | blocked |
| `ust20002` | US stock amend order | `/api/us/ordr` | blocked |
| `ust20003` | US stock cancel order | `/api/us/ordr` | blocked |
| `F4` | US stock realtime order check | `/api/us/websocket` | blocked before live order architecture |
| `F5` | US stock realtime fill | `/api/us/websocket` | mapper only; live registration blocked |

Order TRs are inventoried so they cannot be accidentally treated as read-only
TRs. They are not connected to executable HTTP or WebSocket code.

## Read-only Client Skeleton

`backend/trading_engine/providers/kiwoom_us/rest_client.py` currently builds
request shapes only. It does not import `httpx`, `requests`, or `websockets`,
and `execute_readonly_tr()` is blocked while `liveProvider=false`.

The skeleton allows these categories:

- Condition-search request packets: `usa20280`, `usa20281`, `usa20290`,
  `usa20291`.
- Realtime read-only registration packets: `FE`, `FT`.
- Account and PnL read-only REST requests: `ust21110`, `ust21120`,
  `ust21150`, `ust21510`, `ust21630`, `ust21650`.

The skeleton blocks these categories:

- Order REST TRs: `ust20000`, `ust20001`, `ust20002`, `ust20003`.
- Order-related realtime channels: `F4`, `F5`.

To move beyond skeleton mode, a separate task must explicitly approve
`liveProvider=true`, define credential loading from server-side env/keyring, and
keep order execution disabled unless a later order-risk architecture is
approved.
