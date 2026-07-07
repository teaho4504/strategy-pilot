from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from trading_engine.domain.enums import ConditionEventType
from trading_engine.domain.events import ConditionEvent
from trading_engine.providers.base import ConditionProvider


class MockConditionProvider(ConditionProvider):
    def __init__(self, events: list[ConditionEvent] | None = None, delay: float = 0) -> None:
        self.events = events or [
            ConditionEvent(
                event_type=ConditionEventType.ENTERED,
                condition_id="cond-volume-breakout",
                condition_name="거래대금 돌파",
                symbol="005930",
                symbol_name="삼성전자",
            ),
        ]
        self.delay = delay

    async def stream(self) -> AsyncIterator[ConditionEvent]:
        for event in self.events:
            if self.delay:
                await asyncio.sleep(self.delay)
            yield event
