from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from trading_engine.domain.events import MarketDataEvent
from trading_engine.providers.base import MarketDataProvider


class MockMarketDataProvider(MarketDataProvider):
    def __init__(self, events: list[MarketDataEvent] | None = None, delay: float = 0) -> None:
        self.events = events or [
            MarketDataEvent(
                symbol="005930",
                last_price=72_000,
                change_rate=2.2,
                trade_volume=120_000,
                cumulative_volume=3_200_000,
                bid=71_900,
                ask=72_000,
            )
        ]
        self.delay = delay

    async def stream(self, symbols: set[str]) -> AsyncIterator[MarketDataEvent]:
        for event in self.events:
            if symbols and event.symbol not in symbols:
                continue
            if self.delay:
                await asyncio.sleep(self.delay)
            yield event
