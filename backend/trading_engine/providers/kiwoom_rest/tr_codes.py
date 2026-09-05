from __future__ import annotations

from dataclasses import dataclass


DOMESTIC_ACCOUNT_PATH = "/api/dostk/acnt"
DOMESTIC_STOCK_PATH = "/api/dostk/stkinfo"
DOMESTIC_QUOTE_PATH = "/api/dostk/mrkcond"
WEBSOCKET_PATH = "/api/dostk/websocket"


@dataclass(frozen=True)
class ReadOnlyTrCode:
    code: str
    path: str
    purpose: str


@dataclass(frozen=True)
class RealtimeTypeCode:
    code: str
    purpose: str
    order_related: bool = False


class DomesticReadOnlyTR:
    ACCOUNT_LOOKUP = ReadOnlyTrCode("ka00001", DOMESTIC_ACCOUNT_PATH, "account identifier lookup")
    CASH = ReadOnlyTrCode("kt00001", DOMESTIC_ACCOUNT_PATH, "cash/deposit read")
    ACCOUNT_VALUATION = ReadOnlyTrCode("kt00004", DOMESTIC_ACCOUNT_PATH, "portfolio valuation read")
    HOLDINGS = ReadOnlyTrCode("kt00005", DOMESTIC_ACCOUNT_PATH, "holdings/execution balance read")
    ACCOUNT_PERFORMANCE = ReadOnlyTrCode("ka10085", DOMESTIC_ACCOUNT_PATH, "account performance read")
    STOCK_INFO = ReadOnlyTrCode("ka10001", DOMESTIC_STOCK_PATH, "domestic stock info read")


class DomesticRealtimeType:
    STOCK_QUOTE = RealtimeTypeCode("0B", "domestic stock execution/quote tick")
    ORDERBOOK = RealtimeTypeCode("0D", "domestic order book")
    CONDITION = RealtimeTypeCode("0C", "condition-search result")
    ORDER_FILL = RealtimeTypeCode("00", "order/fill stream", order_related=True)
    BALANCE = RealtimeTypeCode("04", "balance stream", order_related=True)


class DomesticOrderTR:
    """Documented order TR names only.

    These constants are intentionally not wired to any client method. Order,
    amend, and cancel paths remain unavailable in this provider skeleton.
    """

    PLACE_ORDER = "kt10000"
    AMEND_ORDER = "kt10001"
    CANCEL_ORDER = "kt10002"


class UsStockTR:
    """Reserved namespace for future US stock read-only TRs."""

    TODO = "official-us-stock-tr-review-required"
