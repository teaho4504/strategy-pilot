from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from trading_engine.domain.events import ConditionEvent, MarketDataEvent


class ConditionProvider(ABC):
    @abstractmethod
    async def stream(self) -> AsyncIterator[ConditionEvent]:
        raise NotImplementedError


class MarketDataProvider(ABC):
    @abstractmethod
    async def stream(self, symbols: set[str]) -> AsyncIterator[MarketDataEvent]:
        raise NotImplementedError
