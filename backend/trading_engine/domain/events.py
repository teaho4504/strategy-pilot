from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from trading_engine.domain.enums import ConditionEventType


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ConditionEvent:
    event_type: ConditionEventType
    condition_id: str
    condition_name: str
    symbol: str
    symbol_name: str
    occurred_at: datetime = field(default_factory=utc_now)
    source: str = "kiwoom"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MarketDataEvent:
    symbol: str
    last_price: int
    change_rate: float
    trade_volume: int
    cumulative_volume: int
    bid: int
    ask: int
    timestamp: datetime = field(default_factory=utc_now)
