from __future__ import annotations

from collections import deque
from datetime import datetime, timezone

from trading_engine.domain.events import MarketDataEvent
from trading_engine.domain.models import MarketSnapshot, WatchItem


class MarketCache:
    def __init__(self, tick_window: int = 20) -> None:
        self.tick_window = tick_window
        self.snapshots: dict[str, MarketSnapshot] = {}

    def apply_event(self, event: MarketDataEvent, watch_item: WatchItem | None = None) -> MarketSnapshot:
        previous = self.snapshots.get(event.symbol)
        ticks = deque(previous.ticks if previous else [], maxlen=self.tick_window)
        ticks.append({
            "last_price": event.last_price,
            "change_rate": event.change_rate,
            "trade_volume": event.trade_volume,
            "bid": event.bid,
            "ask": event.ask,
            "timestamp": event.timestamp.isoformat(),
        })
        seconds_since_condition_entered = None
        if watch_item:
            seconds_since_condition_entered = (event.timestamp - watch_item.first_seen_at).total_seconds()
        snapshot = MarketSnapshot(
            symbol=event.symbol,
            last_price=event.last_price,
            change_rate=event.change_rate,
            trade_volume=event.trade_volume,
            cumulative_volume=event.cumulative_volume,
            bid=event.bid,
            ask=event.ask,
            updated_at=event.timestamp,
            ticks=list(ticks),
            seconds_since_condition_entered=seconds_since_condition_entered,
        )
        self.snapshots[event.symbol] = snapshot
        return snapshot

    def get(self, symbol: str) -> MarketSnapshot | None:
        return self.snapshots.get(symbol)
