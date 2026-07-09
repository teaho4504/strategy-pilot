from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from trading_engine.domain.enums import ConditionEventType
from trading_engine.domain.events import ConditionEvent, MarketDataEvent
from trading_engine.providers.kiwoom_rest.schemas import MarketTick, OrderBook, OrderBookLevel


def adapt_quote_payload(payload: dict[str, Any]) -> MarketDataEvent:
    tick = MarketTick(
        symbol=_text(payload, "symbol", "stk_cd", "item", "9001"),
        last_price=_int(payload, "last_price", "cur_prc", "10"),
        change_rate=_float(payload, "change_rate", "flu_rt", "12"),
        trade_volume=_int(payload, "trade_volume", "cntr_qty", "15", default=0),
        cumulative_volume=_int(payload, "cumulative_volume", "acc_trdvol", "13", default=0),
        bid=_int(payload, "bid", "bid_prc", "27", default=0),
        ask=_int(payload, "ask", "ask_prc", "28", default=0),
        timestamp=_timestamp(payload),
    )
    return MarketDataEvent(
        symbol=tick.symbol,
        last_price=tick.last_price,
        change_rate=tick.change_rate,
        trade_volume=tick.trade_volume,
        cumulative_volume=tick.cumulative_volume,
        bid=tick.bid,
        ask=tick.ask,
        timestamp=tick.timestamp,
    )


def adapt_orderbook_payload(payload: dict[str, Any]) -> OrderBook:
    symbol = _text(payload, "symbol", "stk_cd", "item", "9001")
    bids = _levels(payload, "bids", "bid")
    asks = _levels(payload, "asks", "ask")
    return OrderBook(symbol=symbol, bids=bids, asks=asks, timestamp=_timestamp(payload))


def adapt_condition_payload(payload: dict[str, Any]) -> ConditionEvent:
    event_value = _text(payload, "event_type", "type", "event", default="entered").lower()
    event_type = ConditionEventType.EXITED if event_value in {"exit", "exited", "out", "D"} else ConditionEventType.ENTERED
    return ConditionEvent(
        event_type=event_type,
        condition_id=_text(payload, "condition_id", "cond_id", "seq", default="unknown"),
        condition_name=_text(payload, "condition_name", "cond_name", "name", default="Kiwoom condition"),
        symbol=_text(payload, "symbol", "stk_cd", "item", "9001"),
        symbol_name=_text(payload, "symbol_name", "stk_nm", "name", default=""),
        occurred_at=_timestamp(payload),
        source="kiwoom",
        metadata={"schema_keys": sorted(payload.keys())},
    )


def _text(payload: dict[str, Any], *keys: str, default: str | None = None) -> str:
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    if default is not None:
        return default
    raise ValueError(f"required text field missing: one of {keys}")


def _int(payload: dict[str, Any], *keys: str, default: int | None = None) -> int:
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return int(str(value).replace(",", "").replace("+", "").strip())
    if default is not None:
        return default
    raise ValueError(f"required integer field missing: one of {keys}")


def _float(payload: dict[str, Any], *keys: str, default: float | None = None) -> float:
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return float(str(value).replace(",", "").replace("%", "").replace("+", "").strip())
    if default is not None:
        return default
    raise ValueError(f"required float field missing: one of {keys}")


def _timestamp(payload: dict[str, Any]) -> datetime:
    raw = payload.get("timestamp") or payload.get("datetime") or payload.get("time")
    if not raw:
        return datetime.now(timezone.utc)
    value = str(raw).strip()
    if len(value) == 6 and value.isdigit():
        now = datetime.now(timezone.utc)
        return now.replace(hour=int(value[:2]), minute=int(value[2:4]), second=int(value[4:6]), microsecond=0)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _levels(payload: dict[str, Any], key: str, prefix: str) -> list[OrderBookLevel]:
    raw = payload.get(key)
    if isinstance(raw, list):
        return [OrderBookLevel(price=_coerce_level_int(item, "price"), quantity=_coerce_level_int(item, "quantity")) for item in raw]
    levels: list[OrderBookLevel] = []
    for index in range(1, 6):
        price = payload.get(f"{prefix}{index}_price") or payload.get(f"{prefix}_prc_{index}")
        quantity = payload.get(f"{prefix}{index}_quantity") or payload.get(f"{prefix}_qty_{index}")
        if price is not None and quantity is not None:
            levels.append(OrderBookLevel(price=int(str(price).replace(",", "")), quantity=int(str(quantity).replace(",", ""))))
    return levels


def _coerce_level_int(item: dict[str, Any], key: str) -> int:
    return int(str(item[key]).replace(",", ""))
