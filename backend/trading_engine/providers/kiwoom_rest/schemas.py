from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from trading_engine.domain.events import utc_now


@dataclass(frozen=True)
class KiwoomRequestSpec:
    api_id: str
    path: str
    body: dict[str, Any] = field(default_factory=dict)
    cont_yn: str | None = None
    next_key: str | None = None


@dataclass(frozen=True)
class KiwoomTokenStatus:
    configured: bool
    cached: bool
    expires_at: datetime | None = None


@dataclass(frozen=True)
class MarketTick:
    symbol: str
    last_price: int
    change_rate: float
    trade_volume: int
    cumulative_volume: int
    bid: int
    ask: int
    timestamp: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class OrderBookLevel:
    price: int
    quantity: int


@dataclass(frozen=True)
class OrderBook:
    symbol: str
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]
    timestamp: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class SubscribeRequest:
    items: list[str]
    types: list[str]
    group_no: str = "1"
    refresh: str = "1"

    def to_reg_packet(self) -> dict[str, Any]:
        if not self.types:
            raise ValueError("types is required")
        return {
            "trnm": "REG",
            "grp_no": self.group_no,
            "refresh": self.refresh,
            "data": [{"item": self.items, "type": self.types}],
        }
