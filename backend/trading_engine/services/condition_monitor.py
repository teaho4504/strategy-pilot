from __future__ import annotations

from trading_engine.providers.base import ConditionProvider
from trading_engine.services.watchlist_manager import WatchlistManager
from trading_engine.storage.sqlite_store import SQLiteStore


class ConditionMonitor:
    def __init__(self, provider: ConditionProvider, watchlist_manager: WatchlistManager, store: SQLiteStore) -> None:
        self.provider = provider
        self.watchlist_manager = watchlist_manager
        self.store = store

    async def run_once(self) -> None:
        async for event in self.provider.stream():
            self.watchlist_manager.handle_condition_event(event)
            self.store.record_condition_event(event)
