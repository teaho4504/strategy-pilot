from __future__ import annotations

from typing import Any

from trading_engine.providers.kiwoom_us.safety import assert_us_order_blocked, assert_us_read_only
from trading_engine.providers.kiwoom_us.schemas import UsKiwoomRequest, UsRealtimeRegistration, UsRealtimeSymbol
from trading_engine.providers.kiwoom_us.tr_codes import UsTrCategory, get_us_tr_spec


def build_readonly_request(tr_id: str, body: dict[str, Any] | None = None) -> UsKiwoomRequest:
    spec = get_us_tr_spec(tr_id)
    assert_us_read_only(spec)
    if spec.stream:
        raise ValueError(f"Use websocket/condition builders for streaming TR: {tr_id}")
    return UsKiwoomRequest(tr_id=spec.tr_id, endpoint=spec.endpoint, method=spec.method, body=body or {}, read_only=True)


def build_daily_account_return_request(from_date: str, to_date: str) -> UsKiwoomRequest:
    body = {
        "from": _yyyymmdd("from", from_date),
        "to": _yyyymmdd("to", to_date),
    }
    return build_readonly_request("usa21670", body)


def build_orderable_quantity_request(exchange: str, symbol: str, unit_price: str) -> UsKiwoomRequest:
    body = {
        "stex_tp": exchange if exchange in {"NA", "ND", "NY"} else "",
        "stk_cd": _safe_symbol(symbol),
        "uv": _positive_numeric_text("uv", unit_price),
    }
    return build_readonly_request("ust31490", body)


def build_stock_info_request(exchange: str, symbol: str) -> UsKiwoomRequest:
    body = {
        "stex_tp": exchange if exchange in {"NA", "ND", "NY"} else "",
        "stk_cd": _safe_symbol(symbol),
    }
    return build_readonly_request("usa10100", body)


def build_condition_list_request() -> UsKiwoomRequest:
    spec = get_us_tr_spec("usa20280")
    return UsKiwoomRequest(spec.tr_id, spec.endpoint, spec.method, {"trnm": "GCNSRLST"}, stream=True, read_only=True)


def build_condition_search_request(seq: str, *, realtime: bool = False, cont_yn: str | None = None, next_key: str | None = None) -> UsKiwoomRequest:
    tr_id = "usa20290" if realtime else "usa20281"
    spec = get_us_tr_spec(tr_id)
    body: dict[str, Any] = {
        "trnm": "GCNSRREQ",
        "seq": seq,
        "search_type": "1" if realtime else "0",
    }
    if cont_yn:
        body["cont_yn"] = cont_yn
    if next_key:
        body["next_key"] = next_key
    return UsKiwoomRequest(spec.tr_id, spec.endpoint, spec.method, body, stream=True, read_only=True)


def build_condition_clear_request(seq: str) -> UsKiwoomRequest:
    spec = get_us_tr_spec("usa20291")
    return UsKiwoomRequest(spec.tr_id, spec.endpoint, spec.method, {"trnm": "GCNSRCLR", "seq": seq}, stream=True, read_only=True)


def build_realtime_registration(tr_id: str, symbols: list[UsRealtimeSymbol]) -> UsRealtimeRegistration:
    spec = get_us_tr_spec(tr_id)
    assert_us_read_only(spec)
    if spec.category != UsTrCategory.REALTIME:
        raise ValueError(f"TR is not a realtime quote/orderbook stream: {tr_id}")
    return UsRealtimeRegistration(tr_id=spec.tr_id, symbols=symbols)


def build_us_order_request_blocked(tr_id: str, *_: object, **__: object) -> None:
    assert_us_order_blocked(tr_id)


def _yyyymmdd(name: str, value: str) -> str:
    cleaned = str(value).strip()
    if len(cleaned) != 8 or not cleaned.isdigit():
        raise ValueError(f"{name} must be YYYYMMDD")
    return cleaned


def _safe_symbol(value: str) -> str:
    cleaned = "".join(ch for ch in str(value).upper().strip() if ch.isalnum() or ch in {".", "-"})
    if not cleaned:
        raise ValueError("symbol is required")
    return cleaned[:12]


def _positive_numeric_text(name: str, value: str) -> str:
    cleaned = str(value).strip()
    try:
        parsed = float(cleaned)
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be positive")
    return cleaned
