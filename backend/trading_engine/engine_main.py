from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from trading_engine.config import get_engine_settings
from trading_engine.domain.enums import SignalType
from trading_engine.providers.mock_condition_provider import MockConditionProvider
from trading_engine.providers.mock_market_data_provider import MockMarketDataProvider
from trading_engine.services.condition_monitor import ConditionMonitor
from trading_engine.services.journal_service import JournalService
from trading_engine.services.market_cache import MarketCache
from trading_engine.services.paper_broker import PaperBroker
from trading_engine.services.risk_manager import RiskManager
from trading_engine.services.strategy_runner import SimpleConditionStrategy
from trading_engine.services.watchlist_manager import WatchlistManager
from trading_engine.storage.sqlite_store import SQLiteStore


async def run_engine_once() -> dict[str, object]:
    settings = get_engine_settings()
    print(f"Trading engine starting mode={settings.mode} orderEnabled={settings.order_enabled} liveProvider={settings.live_provider_enabled}")
    if settings.mode != "paper" or settings.order_enabled or settings.live_provider_enabled:
        raise RuntimeError("Unsafe trading engine settings: only paper mode with orders disabled is allowed")

    store = SQLiteStore(settings.db_path)
    watchlist = WatchlistManager()
    condition_monitor = ConditionMonitor(MockConditionProvider(), watchlist, store)
    market_cache = MarketCache(settings.tick_window)
    broker = PaperBroker()
    risk = RiskManager(settings)
    strategy = SimpleConditionStrategy()

    try:
        await condition_monitor.run_once()
        market_provider = MockMarketDataProvider()
        async for event in market_provider.stream(watchlist.active_symbols()):
            store.record_market_event(event)
            watch_item = watchlist.items.get(event.symbol)
            snapshot = market_cache.apply_event(event, watch_item)
            if not watch_item:
                continue
            signal = strategy.evaluate(watch_item, snapshot, broker.account_state())
            store.record_signal(signal)
            if signal.signal_type == SignalType.PAPER_BUY_CANDIDATE:
                decision = risk.check_entry(signal, broker.account_state(), entry_amount=500_000)
                if not decision.allowed:
                    store.record_risk_block(signal.symbol, decision.reason, datetime.now(timezone.utc).isoformat())
                    continue
                fill = broker.paper_buy(watch_item, signal, snapshot.last_price, amount=500_000)
                risk.mark_entry(signal.symbol)
                store.record_fill(fill)
        journal = JournalService(store).daily()
        return {
            "mode": settings.mode,
            "orderEnabled": settings.order_enabled,
            "watchlistSize": len(watchlist.items),
            "fills": len(broker.fills),
            "journalEntries": journal.entries,
        }
    finally:
        store.close()


async def main() -> None:
    try:
        result = await run_engine_once()
        print(f"Trading engine completed {result}")
    except KeyboardInterrupt:
        print("Trading engine shutdown requested")
    except Exception as exc:
        print(f"Trading engine stopped safely: {exc}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
