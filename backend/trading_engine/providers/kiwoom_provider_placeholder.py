from __future__ import annotations

from collections.abc import AsyncIterator

from trading_engine.domain.events import ConditionEvent, MarketDataEvent
from trading_engine.providers.base import ConditionProvider, MarketDataProvider


class KiwoomProviderPlaceholder(ConditionProvider, MarketDataProvider):
    """Placeholder only. It intentionally does not connect to Kiwoom."""

    async def stream(self) -> AsyncIterator[ConditionEvent]:
        raise RuntimeError("Kiwoom condition provider is disabled until official protocol review is complete")

    async def stream_market_data(self, symbols: set[str]) -> AsyncIterator[MarketDataEvent]:
        raise RuntimeError("Kiwoom market data provider is disabled until official protocol review is complete")
