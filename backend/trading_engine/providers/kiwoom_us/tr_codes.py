from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


US_REST_BASE_URL = "https://api.kiwoom.com"
US_REST_MOCK_URL = "https://mockapi.kiwoom.com"
US_WS_BASE_URL = "wss://api.kiwoom.com:10000"
US_WS_MOCK_URL = "wss://mockapi.kiwoom.com:10000"

US_ACCOUNT_PATH = "/api/us/acnt"
US_ORDER_PATH = "/api/us/ordr"
US_WEBSOCKET_PATH = "/api/us/websocket"


class UsTrCategory(str, Enum):
    AUTH = "auth"
    CONDITION = "condition"
    REALTIME = "realtime"
    ACCOUNT = "account"
    PNL = "pnl"
    ORDER = "order"


@dataclass(frozen=True)
class UsTrSpec:
    tr_id: str
    name: str
    category: UsTrCategory
    endpoint: str
    method: str = "POST"
    read_only: bool = True
    stream: bool = False
    order_related: bool = False
    priority: str = "normal"
    notes: str = ""


US_TR_INVENTORY: dict[str, UsTrSpec] = {
    "usa20280": UsTrSpec("usa20280", "미국주식 조건검색 목록조회", UsTrCategory.CONDITION, US_WEBSOCKET_PATH, stream=True, priority="high"),
    "usa20281": UsTrSpec("usa20281", "미국주식 조건검색 요청 일반", UsTrCategory.CONDITION, US_WEBSOCKET_PATH, stream=True, priority="high"),
    "usa20290": UsTrSpec("usa20290", "미국주식 조건검색 요청 실시간", UsTrCategory.CONDITION, US_WEBSOCKET_PATH, stream=True, priority="highest"),
    "usa20291": UsTrSpec("usa20291", "미국주식 조건검색 실시간 해제", UsTrCategory.CONDITION, US_WEBSOCKET_PATH, stream=True, priority="high"),
    "FE": UsTrSpec("FE", "미국주식 실시간 체결가", UsTrCategory.REALTIME, US_WEBSOCKET_PATH, stream=True, priority="highest"),
    "FT": UsTrSpec("FT", "미국주식 10호가", UsTrCategory.REALTIME, US_WEBSOCKET_PATH, stream=True, priority="highest"),
    "F4": UsTrSpec("F4", "미국주식 실시간 주문 확인", UsTrCategory.REALTIME, US_WEBSOCKET_PATH, stream=True, order_related=True, priority="deferred", notes="Order-related stream; keep disconnected before live order architecture."),
    "ust21110": UsTrSpec("ust21110", "해외주식 예수금", UsTrCategory.ACCOUNT, US_ACCOUNT_PATH, priority="highest"),
    "ust21120": UsTrSpec("ust21120", "통화별 예수금 및 증권 평가금현황", UsTrCategory.ACCOUNT, US_ACCOUNT_PATH, priority="high"),
    "ust21150": UsTrSpec("ust21150", "미국주식 일별 주문체결내역", UsTrCategory.ACCOUNT, US_ACCOUNT_PATH, priority="high"),
    "ust21510": UsTrSpec("ust21510", "미국주식 당일 주문체결 확인", UsTrCategory.ACCOUNT, US_ACCOUNT_PATH, priority="high"),
    "ust21630": UsTrSpec("ust21630", "미국주식 당일 실현손익", UsTrCategory.PNL, US_ACCOUNT_PATH, priority="high"),
    "ust21650": UsTrSpec("ust21650", "미국주식 기간별 수익률 현황", UsTrCategory.PNL, US_ACCOUNT_PATH, priority="normal"),
    "ust20000": UsTrSpec("ust20000", "미국주식 매수 주문", UsTrCategory.ORDER, US_ORDER_PATH, read_only=False, order_related=True, priority="blocked"),
    "ust20001": UsTrSpec("ust20001", "미국주식 매도 주문", UsTrCategory.ORDER, US_ORDER_PATH, read_only=False, order_related=True, priority="blocked"),
    "ust20002": UsTrSpec("ust20002", "미국주식 정정 주문", UsTrCategory.ORDER, US_ORDER_PATH, read_only=False, order_related=True, priority="blocked"),
    "ust20003": UsTrSpec("ust20003", "미국주식 취소 주문", UsTrCategory.ORDER, US_ORDER_PATH, read_only=False, order_related=True, priority="blocked"),
}


def get_us_tr_spec(tr_id: str) -> UsTrSpec:
    try:
        return US_TR_INVENTORY[tr_id]
    except KeyError as exc:
        raise ValueError(f"Unsupported US TR ID: {tr_id}") from exc
