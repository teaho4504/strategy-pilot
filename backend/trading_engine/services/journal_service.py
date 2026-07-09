from __future__ import annotations

from trading_engine.domain.models import DailyJournal
from trading_engine.services.market_time import market_time_context
from trading_engine.storage.sqlite_store import SQLiteStore


class JournalService:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def daily(self, trade_date: str | None = None) -> DailyJournal:
        return self.store.daily_journal(trade_date or market_time_context().us_market_date)
