from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from trading_engine.config import EngineSettings
from trading_engine.domain.enums import ConditionEventType, FillSide, SignalType, WatchStatus
from trading_engine.domain.events import ConditionEvent, MarketDataEvent
from trading_engine.providers.mock_condition_provider import MockConditionProvider
from trading_engine.services.condition_monitor import ConditionMonitor
from trading_engine.services.journal_service import JournalService
from trading_engine.services.market_cache import MarketCache
from trading_engine.services.paper_broker import PaperBroker
from trading_engine.services.risk_manager import RiskManager
from trading_engine.services.strategy_runner import SimpleConditionStrategy
from trading_engine.services.watchlist_manager import WatchlistManager
from trading_engine.storage.sqlite_store import SQLiteStore


@pytest.fixture
def store(tmp_path):
    db = SQLiteStore(tmp_path / "engine.sqlite3")
    yield db
    db.close()


@pytest.fixture
def entered_event():
    return ConditionEvent(
        event_type=ConditionEventType.ENTERED,
        condition_id="cond-1",
        condition_name="거래대금 돌파",
        symbol="005930",
        symbol_name="삼성전자",
    )


@pytest.fixture
def market_event():
    return MarketDataEvent(
        symbol="005930",
        last_price=72_000,
        change_rate=2.2,
        trade_volume=120_000,
        cumulative_volume=3_200_000,
        bid=71_900,
        ask=72_000,
    )


def test_condition_enter_event_adds_watch_candidate_and_records(store, entered_event):
    manager = WatchlistManager()

    item = manager.handle_condition_event(entered_event)
    store.record_condition_event(entered_event)

    assert item.symbol == "005930"
    assert item.status == WatchStatus.CANDIDATE
    assert store.count_rows("condition_events") == 1


def test_duplicate_condition_enter_does_not_duplicate_watch_item(entered_event):
    manager = WatchlistManager()

    first = manager.handle_condition_event(entered_event)
    second = manager.handle_condition_event(entered_event)

    assert first is second
    assert len(manager.items) == 1
    assert manager.items["005930"].enter_count == 2


def test_condition_exit_event_is_recorded_and_marks_exited(store, entered_event):
    manager = WatchlistManager()
    manager.handle_condition_event(entered_event)
    exited = ConditionEvent(
        event_type=ConditionEventType.EXITED,
        condition_id=entered_event.condition_id,
        condition_name=entered_event.condition_name,
        symbol=entered_event.symbol,
        symbol_name=entered_event.symbol_name,
    )

    item = manager.handle_condition_event(exited)
    store.record_condition_event(exited)

    assert item.status == WatchStatus.EXITED
    assert store.count_rows("condition_events") == 1


def test_mock_condition_provider_streams_events(store):
    manager = WatchlistManager()
    provider = MockConditionProvider(events=[
        ConditionEvent(ConditionEventType.ENTERED, "cond", "거래대금 돌파", "005930", "삼성전자"),
    ])
    monitor = ConditionMonitor(provider, manager, store)

    asyncio.run(monitor.run_once())

    assert "005930" in manager.items
    assert store.count_rows("condition_events") == 1


def test_market_event_updates_cache_and_store(store, entered_event, market_event):
    manager = WatchlistManager()
    item = manager.handle_condition_event(entered_event)
    cache = MarketCache(tick_window=3)

    snapshot = cache.apply_event(market_event, item)
    store.record_market_event(market_event)

    assert snapshot.last_price == 72_000
    assert snapshot.bid == 71_900
    assert snapshot.ask == 72_000
    assert snapshot.seconds_since_condition_entered is not None
    assert store.count_rows("market_events") == 1


def test_strategy_generates_paper_buy_candidate(entered_event, market_event):
    manager = WatchlistManager()
    item = manager.handle_condition_event(entered_event)
    snapshot = MarketCache().apply_event(market_event, item)
    broker = PaperBroker()

    signal = SimpleConditionStrategy().evaluate(item, snapshot, broker.account_state())

    assert signal.signal_type == SignalType.PAPER_BUY_CANDIDATE
    assert signal.symbol == "005930"


def test_kill_switch_blocks_entry_and_records_reason(store, entered_event, market_event):
    item = WatchlistManager().handle_condition_event(entered_event)
    snapshot = MarketCache().apply_event(market_event, item)
    broker = PaperBroker()
    signal = SimpleConditionStrategy().evaluate(item, snapshot, broker.account_state())
    risk = RiskManager(EngineSettings(kill_switch=True))

    decision = risk.check_entry(signal, broker.account_state(), entry_amount=500_000)
    if not decision.allowed:
        store.record_risk_block(signal.symbol, decision.reason, datetime.now(timezone.utc).isoformat())

    assert decision.allowed is False
    assert "kill switch" in decision.reason
    assert store.count_rows("risk_blocks") == 1


def test_paper_broker_never_calls_real_order_api(entered_event, market_event):
    item = WatchlistManager().handle_condition_event(entered_event)
    signal = SimpleConditionStrategy().evaluate(item, MarketCache().apply_event(market_event, item), PaperBroker().account_state())
    broker = PaperBroker()

    fill = broker.paper_buy(item, signal, market_event.last_price, amount=500_000)

    assert fill.side == FillSide.BUY
    assert broker.order_api_call_count == 0


def test_paper_fill_is_stored_in_sqlite(store, entered_event, market_event):
    item = WatchlistManager().handle_condition_event(entered_event)
    signal = SimpleConditionStrategy().evaluate(item, MarketCache().apply_event(market_event, item), PaperBroker().account_state())
    broker = PaperBroker()
    fill = broker.paper_buy(item, signal, market_event.last_price, amount=500_000)

    store.record_fill(fill)

    assert store.count_rows("paper_fills") == 1


def test_daily_journal_aggregates_paper_trades(store, entered_event, market_event):
    item = WatchlistManager().handle_condition_event(entered_event)
    signal = SimpleConditionStrategy().evaluate(item, MarketCache().apply_event(market_event, item), PaperBroker().account_state())
    broker = PaperBroker()
    buy = broker.paper_buy(item, signal, market_event.last_price, amount=500_000)
    sell = broker.paper_sell(item.symbol, 73_000, "paper take profit")
    assert sell is not None
    store.record_fill(buy)
    store.record_fill(sell)

    journal = JournalService(store).daily(buy.filled_at.date().isoformat())

    assert journal.entries == 1
    assert journal.exits == 1
    assert journal.total_pnl == sell.realized_pnl
    assert journal.strategy_breakdown[signal.strategy_name]["entries"] == 1


def test_order_related_paths_are_disabled_by_configuration():
    settings = EngineSettings()

    assert settings.mode == "paper"
    assert settings.order_enabled is False
    assert settings.live_provider_enabled is False


def test_no_order_endpoint_or_kiwoom_order_api_is_imported():
    import pathlib

    backend_root = pathlib.Path(__file__).resolve().parents[2]
    order_api = backend_root / "app" / "api" / "orders.py"

    assert not order_api.exists()
