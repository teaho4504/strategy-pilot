from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


class UsOrderEventMappingError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class UsBrokerOrderEvent:
    tr_id: str
    order_no: str
    original_order_no: str | None
    symbol: str
    side: str
    order_type: str | None
    trade_type: str | None
    status: str
    order_quantity: int | None
    order_price: float | None
    unfilled_quantity: int | None
    fill_no: str | None
    fill_quantity: int | None
    fill_price: float | None
    holding_quantity: int | None
    event_time: str | None
    currency: str | None
    unknown_field_ids: tuple[str, ...]


_ORDER_EVENT_CHANNELS = {"F4", "F5"}
_SENSITIVE_FIELD_IDS = {"9201"}
_KNOWN_FIELD_IDS = {
    "302",
    "900",
    "901",
    "902",
    "904",
    "905",
    "906",
    "907",
    "908",
    "909",
    "910",
    "911",
    "913",
    "930",
    "931",
    "934",
    "936",
    "1091",
    "8004",
    "8005",
    "8018",
    "8019",
    "8043",
    "8046",
    "8075",
    "9001",
    "9203",
    "13006",
    "50072",
    "50073",
    "50724",
    "50725",
    "50810",
    "50841",
    "50844",
    "55190",
}


def map_us_order_realtime_payload(payload: dict[str, Any]) -> list[UsBrokerOrderEvent]:
    if payload.get("trnm") != "REAL":
        raise UsOrderEventMappingError("order event payload must have trnm=REAL")

    raw_items = payload.get("data")
    if not isinstance(raw_items, list):
        raise UsOrderEventMappingError("order event payload data must be a list")

    events: list[UsBrokerOrderEvent] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            raise UsOrderEventMappingError("order event item must be an object")

        tr_id = _optional_text(raw_item.get("type"))
        if tr_id not in _ORDER_EVENT_CHANNELS:
            continue

        values = raw_item.get("values")
        if not isinstance(values, dict):
            raise UsOrderEventMappingError(f"{tr_id} values must be an object")

        normalized = {str(key): value for key, value in values.items()}
        order_no = _required_text(normalized, "9203", "order number")
        symbol = _optional_text(normalized.get("9001")) or _optional_text(raw_item.get("item"))
        if symbol is None:
            raise UsOrderEventMappingError(f"{tr_id} symbol is missing")

        status = _required_text(normalized, "913", "order status")
        events.append(
            UsBrokerOrderEvent(
                tr_id=tr_id,
                order_no=order_no,
                original_order_no=_normalize_original_order_no(normalized.get("904")),
                symbol=symbol.upper(),
                side=_map_side(normalized.get("907")),
                order_type=_optional_text(normalized.get("905")),
                trade_type=_optional_text(normalized.get("906")),
                status=status,
                order_quantity=_optional_nonnegative_int(normalized.get("900"), "order quantity"),
                order_price=_optional_nonnegative_float(normalized.get("901"), "order price"),
                unfilled_quantity=_optional_nonnegative_int(normalized.get("902"), "unfilled quantity"),
                fill_no=_normalize_original_order_no(normalized.get("909")),
                fill_quantity=_optional_nonnegative_int(normalized.get("911"), "fill quantity"),
                fill_price=_optional_nonnegative_float(normalized.get("910"), "fill price"),
                holding_quantity=_optional_nonnegative_int(normalized.get("930"), "holding quantity"),
                event_time=_optional_text(normalized.get("908")),
                currency=_optional_text(normalized.get("8043")),
                unknown_field_ids=tuple(
                    sorted(
                        field_id
                        for field_id in normalized
                        if field_id not in _KNOWN_FIELD_IDS and field_id not in _SENSITIVE_FIELD_IDS
                    )
                ),
            )
        )
    return events


def _required_text(values: dict[str, Any], key: str, label: str) -> str:
    value = _optional_text(values.get(key))
    if value is None:
        raise UsOrderEventMappingError(f"{label} is missing")
    return value


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_original_order_no(value: object) -> str | None:
    normalized = _optional_text(value)
    if normalized is None or set(normalized) == {"0"}:
        return None
    return normalized


def _map_side(value: object) -> str:
    normalized = _optional_text(value)
    if normalized == "01":
        return "sell"
    if normalized == "02":
        return "buy"
    return "unknown"


def _optional_nonnegative_int(value: object, label: str) -> int | None:
    normalized = _optional_number(value)
    if normalized is None:
        return None
    try:
        decimal_value = Decimal(normalized)
    except (InvalidOperation, ValueError) as exc:
        raise UsOrderEventMappingError(f"{label} must be numeric") from exc
    if not decimal_value.is_finite() or decimal_value != decimal_value.to_integral_value():
        raise UsOrderEventMappingError(f"{label} must be an integer")
    if decimal_value < 0:
        raise UsOrderEventMappingError(f"{label} must be nonnegative")
    return int(decimal_value)


def _optional_nonnegative_float(value: object, label: str) -> float | None:
    normalized = _optional_number(value)
    if normalized is None:
        return None
    try:
        decimal_value = Decimal(normalized)
    except (InvalidOperation, ValueError) as exc:
        raise UsOrderEventMappingError(f"{label} must be numeric") from exc
    if not decimal_value.is_finite():
        raise UsOrderEventMappingError(f"{label} must be finite")
    if decimal_value < 0:
        raise UsOrderEventMappingError(f"{label} must be nonnegative")
    return float(decimal_value)


def _optional_number(value: object) -> str | None:
    normalized = _optional_text(value)
    if normalized is None:
        return None
    return normalized.replace(",", "").lstrip("+").strip()
