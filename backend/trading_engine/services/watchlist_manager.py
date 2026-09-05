from __future__ import annotations

from trading_engine.domain.enums import ConditionEventType, WatchSource, WatchStatus
from trading_engine.domain.events import ConditionEvent
from trading_engine.domain.models import WatchItem


class WatchlistManager:
    def __init__(self) -> None:
        self.items: dict[str, WatchItem] = {}
        self.history: list[ConditionEvent] = []

    def handle_condition_event(self, event: ConditionEvent) -> WatchItem:
        self.history.append(event)
        existing = self.items.get(event.symbol)

        if event.event_type in {ConditionEventType.ENTERED, ConditionEventType.SNAPSHOT}:
            if existing:
                existing.status = WatchStatus.CANDIDATE if existing.status == WatchStatus.EXITED else existing.status
                existing.last_event_at = event.occurred_at
                existing.enter_count += 1
                return existing
            item = WatchItem(
                symbol=event.symbol,
                symbol_name=event.symbol_name,
                status=WatchStatus.CANDIDATE,
                source=WatchSource.CONDITION,
                condition_id=event.condition_id,
                condition_name=event.condition_name,
                first_seen_at=event.occurred_at,
                last_event_at=event.occurred_at,
            )
            self.items[event.symbol] = item
            return item

        if event.event_type == ConditionEventType.EXITED:
            if existing:
                existing.status = WatchStatus.EXITED
                existing.last_event_at = event.occurred_at
                return existing
            item = WatchItem(
                symbol=event.symbol,
                symbol_name=event.symbol_name,
                status=WatchStatus.EXITED,
                source=WatchSource.CONDITION,
                condition_id=event.condition_id,
                condition_name=event.condition_name,
                first_seen_at=event.occurred_at,
                last_event_at=event.occurred_at,
                enter_count=0,
            )
            self.items[event.symbol] = item
            return item

        raise ValueError(f"Unsupported condition event type: {event.event_type}")

    def active_symbols(self) -> set[str]:
        return {symbol for symbol, item in self.items.items() if item.status in {WatchStatus.CANDIDATE, WatchStatus.ACTIVE}}
