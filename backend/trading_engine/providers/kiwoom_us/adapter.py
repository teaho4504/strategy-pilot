from __future__ import annotations

from typing import Any

from trading_engine.domain.enums import ConditionEventType
from trading_engine.domain.events import ConditionEvent, MarketDataEvent
from trading_engine.providers.kiwoom_rest.adapter import adapt_orderbook_payload
from trading_engine.providers.kiwoom_rest.schemas import OrderBook
from trading_engine.providers.kiwoom_us.request_builder import (
    build_daily_account_return_request as _build_daily_account_return_request,
    build_condition_search_request,
    build_readonly_request,
    build_realtime_registration,
)
from trading_engine.providers.kiwoom_us.response_mapper import map_account_balance_response, map_condition_search_response
from trading_engine.providers.kiwoom_us.schemas import UsAccountBalance, UsConditionSearchResult, UsKiwoomRequest, UsRealtimeRegistration, UsRealtimeSymbol


def adapt_us_quote_payload(payload: dict[str, Any]) -> MarketDataEvent:
    values = _values(payload)
    symbol = _text(payload, values, "symbol", "jmcode", "item", "9001")
    return MarketDataEvent(
        symbol=symbol,
        last_price=_int(values, "10", "last_price", "cur_prc"),
        change_rate=_float(values, "12", "change_rate", "flu_rt", default=0.0),
        trade_volume=_int(values, "15", "trade_volume", "cntr_qty", default=0),
        cumulative_volume=_int(values, "13", "cumulative_volume", "acc_trdvol", default=0),
        bid=_int(values, "27", "bid", "bid_prc", default=0),
        ask=_int(values, "28", "ask", "ask_prc", default=0),
    )


def adapt_us_orderbook_payload(payload: dict[str, Any]) -> OrderBook:
    values = _values(payload)
    symbol = _text(payload, values, "symbol", "jmcode", "item", "9001")
    normalized = {"symbol": symbol}
    normalized.update(values)
    return adapt_orderbook_payload(normalized)


def adapt_us_condition_payload(payload: dict[str, Any]) -> ConditionEvent:
    values = _values(payload)
    event_value = _text(payload, values, "event_type", "event", "type", default="entered").lower()
    event_type = ConditionEventType.EXITED if event_value in {"exit", "exited", "out", "d"} else ConditionEventType.ENTERED
    return ConditionEvent(
        event_type=event_type,
        condition_id=_text(payload, values, "condition_id", "seq", default="unknown"),
        condition_name=_text(payload, values, "condition_name", "name", default="US condition"),
        symbol=_text(payload, values, "symbol", "jmcode", "stk_cd", "item"),
        symbol_name=_text(payload, values, "symbol_name", "stk_nm", "name", default=""),
        source="kiwoom_us",
        metadata={"schema_keys": sorted(payload.keys())},
    )


def build_account_balance_request(tr_id: str = "ust21110") -> UsKiwoomRequest:
    return build_readonly_request(tr_id)


def build_profit_loss_request(tr_id: str = "ust21630", body: dict[str, Any] | None = None) -> UsKiwoomRequest:
    return build_readonly_request(tr_id, body)


def build_daily_account_return_request(from_date: str, to_date: str) -> UsKiwoomRequest:
    return _build_daily_account_return_request(from_date, to_date)


def build_realtime_price_subscription(symbols: list[UsRealtimeSymbol]) -> UsRealtimeRegistration:
    return build_realtime_registration("FE", symbols)


def map_us_condition_search_response(raw: dict[str, Any]) -> UsConditionSearchResult:
    return map_condition_search_response(raw)


def map_us_account_balance_response(raw: dict[str, Any], tr_id: str = "ust21110") -> UsAccountBalance:
    return map_account_balance_response(tr_id, raw)


def _values(payload: dict[str, Any]) -> dict[str, Any]:
    raw = payload.get("values")
    return raw if isinstance(raw, dict) else {}


def _text(payload: dict[str, Any], values: dict[str, Any], *keys: str, default: str | None = None) -> str:
    for source in (payload, values):
        for key in keys:
            value = source.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
    if default is not None:
        return default
    raise ValueError(f"required text field missing: one of {keys}")


def _int(values: dict[str, Any], *keys: str, default: int | None = None) -> int:
    for key in keys:
        value = values.get(key)
        if value is not None and str(value).strip():
            normalized = str(value).replace(",", "").replace("+", "").strip()
            try:
                return int(normalized)
            except ValueError:
                return int(float(normalized))
    if default is not None:
        return default
    raise ValueError(f"required integer field missing: one of {keys}")


def _float(values: dict[str, Any], *keys: str, default: float | None = None) -> float:
    for key in keys:
        value = values.get(key)
        if value is not None and str(value).strip():
            return float(str(value).replace(",", "").replace("%", "").replace("+", "").strip())
    if default is not None:
        return default
    raise ValueError(f"required float field missing: one of {keys}")
