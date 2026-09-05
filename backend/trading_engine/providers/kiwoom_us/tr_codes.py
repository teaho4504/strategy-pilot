from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


US_REST_BASE_URL = "https://api.kiwoom.com"
US_WS_BASE_URL = "wss://api.kiwoom.com:10000"

US_ACCOUNT_PATH = "/api/us/acnt"
US_CHART_PATH = "/api/us/chart"
US_ORDER_PATH = "/api/us/ordr"
US_RANKING_PATH = "/api/us/rkinfo"
US_STOCK_INFO_PATH = "/api/us/stkinfo"
US_WEBSOCKET_PATH = "/api/us/websocket"


class UsTrCategory(str, Enum):
    AUTH = "auth"
    CONDITION = "condition"
    REALTIME = "realtime"
    CHART = "chart"
    ACCOUNT = "account"
    PNL = "pnl"
    ORDER = "order"
    ORDER_CHECK = "order_check"


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
    "usa01980": UsTrSpec("usa01980", "미국주식 실시간 종목 조회 순위", UsTrCategory.REALTIME, US_RANKING_PATH, priority="highest"),
    "usa06010": UsTrSpec("usa06010", "미국주식 틱 차트", UsTrCategory.CHART, US_CHART_PATH, priority="high"),
    "usa06011": UsTrSpec("usa06011", "미국주식 분 차트", UsTrCategory.CHART, US_CHART_PATH, priority="highest"),
    "usa06012": UsTrSpec("usa06012", "미국주식 일 차트", UsTrCategory.CHART, US_CHART_PATH, priority="high"),
    "usa06013": UsTrSpec("usa06013", "미국주식 주 차트", UsTrCategory.CHART, US_CHART_PATH, priority="normal"),
    "usa06014": UsTrSpec("usa06014", "미국주식 월 차트", UsTrCategory.CHART, US_CHART_PATH, priority="normal"),
    "usa06015": UsTrSpec("usa06015", "미국주식 년 차트", UsTrCategory.CHART, US_CHART_PATH, priority="normal"),
    "usa06016": UsTrSpec("usa06016", "미국주식 분기 차트", UsTrCategory.CHART, US_CHART_PATH, priority="normal"),
    "usa10098": UsTrSpec("usa10098", "미국주식 거래소구분 조회", UsTrCategory.REALTIME, US_STOCK_INFO_PATH, priority="high"),
    "usa10099": UsTrSpec("usa10099", "미국주식 종목리스트", UsTrCategory.REALTIME, US_STOCK_INFO_PATH, priority="high"),
    "usa10100": UsTrSpec("usa10100", "미국주식 종목 조회", UsTrCategory.REALTIME, US_STOCK_INFO_PATH, priority="highest", notes="Use isEtf=N as common-stock gate before live US orders."),
    "usa20510": UsTrSpec("usa20510", "미국주식 기간별 등락률상위(주식/업종)", UsTrCategory.REALTIME, US_RANKING_PATH, priority="high"),
    "usa20530": UsTrSpec("usa20530", "미국주식 당일 거래량 상위(주식/업종)", UsTrCategory.REALTIME, US_RANKING_PATH, priority="high"),
    "usa20910": UsTrSpec("usa20910", "미국주식 전일대비 등락률상위(주식/업종)", UsTrCategory.REALTIME, US_RANKING_PATH, priority="high"),
    "usa20930": UsTrSpec("usa20930", "미국주식 가격급등락(주식/업종)", UsTrCategory.REALTIME, US_STOCK_INFO_PATH, priority="high"),
    "usa20280": UsTrSpec("usa20280", "미국주식 조건검색 목록조회", UsTrCategory.CONDITION, US_WEBSOCKET_PATH, stream=True, priority="high"),
    "usa20281": UsTrSpec("usa20281", "미국주식 조건검색 요청 일반", UsTrCategory.CONDITION, US_WEBSOCKET_PATH, stream=True, priority="high"),
    "usa20290": UsTrSpec("usa20290", "미국주식 조건검색 요청 실시간", UsTrCategory.CONDITION, US_WEBSOCKET_PATH, stream=True, priority="highest"),
    "usa20291": UsTrSpec("usa20291", "미국주식 조건검색 실시간 해제", UsTrCategory.CONDITION, US_WEBSOCKET_PATH, stream=True, priority="high"),
    "FE": UsTrSpec("FE", "미국주식 실시간 체결가", UsTrCategory.REALTIME, US_WEBSOCKET_PATH, stream=True, priority="highest"),
    "FT": UsTrSpec("FT", "미국주식 10호가", UsTrCategory.REALTIME, US_WEBSOCKET_PATH, stream=True, priority="highest"),
    "F4": UsTrSpec("F4", "미국주식 실시간 주문 확인", UsTrCategory.REALTIME, US_WEBSOCKET_PATH, stream=True, order_related=True, priority="deferred", notes="Order-related stream; keep disconnected before live order architecture."),
    "F5": UsTrSpec("F5", "미국주식 실시간 체결", UsTrCategory.REALTIME, US_WEBSOCKET_PATH, stream=True, order_related=True, priority="deferred", notes="Order-related stream; mapper only. Keep live registration disconnected until recovery validation."),
    "ust21110": UsTrSpec("ust21110", "해외주식 예수금", UsTrCategory.ACCOUNT, US_ACCOUNT_PATH, priority="highest"),
    "ust21050": UsTrSpec("ust21050", "미국주식 원장 미체결", UsTrCategory.ACCOUNT, US_ACCOUNT_PATH, priority="highest", notes="Read-only open-order reconciliation. Uses order number, filled quantity, canceled quantity, remaining quantity, and order status."),
    "ust21070": UsTrSpec("ust21070", "미국주식 원장잔고확인", UsTrCategory.ACCOUNT, US_ACCOUNT_PATH, priority="highest", notes="Use result_list sell_alowq/poss_qty for liquidation planning."),
    "ust21120": UsTrSpec("ust21120", "통화별 예수금 및 증권 평가금현황", UsTrCategory.ACCOUNT, US_ACCOUNT_PATH, priority="high"),
    "ust21150": UsTrSpec("ust21150", "미국주식 일별 주문체결내역", UsTrCategory.ACCOUNT, US_ACCOUNT_PATH, priority="high"),
    "ust21510": UsTrSpec("ust21510", "미국주식 당일 주문체결 확인", UsTrCategory.ACCOUNT, US_ACCOUNT_PATH, priority="high"),
    "ust21630": UsTrSpec("ust21630", "미국주식 당일 실현손익", UsTrCategory.PNL, US_ACCOUNT_PATH, priority="high"),
    "ust21650": UsTrSpec("ust21650", "미국주식 기간별 수익률 현황", UsTrCategory.PNL, US_ACCOUNT_PATH, priority="normal"),
    "usa21670": UsTrSpec("usa21670", "미국주식 일별계좌수익률현황", UsTrCategory.PNL, US_ACCOUNT_PATH, priority="high", notes="Request body requires from/to dates in YYYYMMDD."),
    "ust31490": UsTrSpec("ust31490", "미국주식 주문가능수량(종목/증거금률별)", UsTrCategory.ORDER_CHECK, US_ORDER_PATH, priority="highest", notes="Read-only orderability check. Production requires stex_tp, stk_cd, uv."),
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
