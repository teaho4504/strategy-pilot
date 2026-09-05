from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from trading_engine.backtesting.us_strategy_backtester import (
    BacktestCostModel,
    _try_exit,
    backtest_single_candidate,
    candidate_from_window,
    summarize_trades,
)
from trading_engine.strategies.us_condition_candidates import (
    ConditionRegistrationError,
    UsConditionCandidateManager,
    UsConditionDefinition,
)
from trading_engine.strategies.us_day_trading import (
    ET,
    STRATEGY_1M_VOLUME_BREAKOUT,
    CandidateSnapshot,
    StrategyDecision,
    StrategyRuntimeState,
    StrategySettings,
    UsCandle,
    UsQuote,
    atr,
    ema,
    evaluate_1m_volume_breakout,
    normalize_candles,
    spread_pct,
    vwap,
)
from trading_engine.storage.sqlite_store import SQLiteStore


def test_indicator_calculators_return_expected_shapes():
    candles = _flat_candles("NVDA", "ND", count=20)

    assert len(ema([c.close for c in candles], 9)) == 20
    assert len(vwap(candles)) == 20
    assert len(atr(candles, 14)) == 20
    assert spread_pct(UsQuote("NVDA", "ND", bid=100, ask=100.1)) < 0.11


def test_candles_are_sorted_and_duplicate_times_are_merged_safely():
    ts = datetime(2026, 7, 10, 10, 0, tzinfo=ET)
    candles = [
        UsCandle("NVDA", "ND", 101, 102, 100, 101.5, 1000, ts + timedelta(minutes=1)),
        UsCandle("NVDA", "ND", 100, 101, 99, 100.5, 700, ts),
        UsCandle("NVDA", "ND", 100.5, 103, 100, 102.5, 300, ts + timedelta(minutes=1)),
    ]

    normalized = normalize_candles(candles)

    assert [c.timestamp for c in normalized] == [ts, ts + timedelta(minutes=1)]
    assert normalized[1].high == 103
    assert normalized[1].low == 100
    assert normalized[1].close == 102.5
    assert normalized[1].volume == 1300


def test_condition_realtime_registration_requires_usa20280_list_first():
    manager = UsConditionCandidateManager()

    try:
        manager.register_realtime("1")
    except ConditionRegistrationError as exc:
        assert "usa20280" in str(exc)
    else:  # pragma: no cover - defensive.
        raise AssertionError("registration should require condition list first")

    manager.load_condition_list([UsConditionDefinition(seq="1", name="US_COMMON_LIQUID_LONG")])
    manager.register_realtime("1")
    candidate = manager.handle_enter(seq="1", symbol="nvda", exchange="ND")

    assert candidate.symbol == "NVDA"
    assert manager.active_candidates()[0].condition_name == "US_COMMON_LIQUID_LONG"


def test_1m_volume_breakout_can_create_ready_limit_order_decision():
    now = datetime(2026, 7, 10, 10, 15, tzinfo=ET)
    candles = _breakout_1m_candles("NVDA", "ND", now)
    candidate = CandidateSnapshot(
        symbol="NVDA",
        exchange="ND",
        price=101.22,
        open_price=99.9,
        day_high=101.25,
        change_rate=3.2,
        cumulative_volume=2_100_000,
        avg_volume_5d=500_000,
        avg_volume_20d=1_000_000,
        same_time_avg_volume=300_000,
        trade_value=45_000_000,
        quote=UsQuote("NVDA", "ND", bid=101.20, ask=101.21, last=101.22, updated_at=now),
    )
    runtime = StrategyRuntimeState(account_equity=100_000)

    decision = evaluate_1m_volume_breakout(candidate, candles, runtime, StrategySettings(), now=now)

    assert decision.strategy_id == STRATEGY_1M_VOLUME_BREAKOUT
    assert decision.ready is True
    assert decision.quantity >= 1
    assert decision.entry_price == 101.21
    assert decision.stop_price is not None
    assert not decision.blocked_reasons


def test_1m_volume_breakout_blocks_when_quote_is_stale():
    now = datetime(2026, 7, 10, 10, 15, tzinfo=ET)
    candles = _breakout_1m_candles("NVDA", "ND", now)
    candidate = CandidateSnapshot(
        symbol="NVDA",
        exchange="ND",
        price=101.22,
        open_price=99.9,
        day_high=101.25,
        change_rate=3.2,
        cumulative_volume=2_100_000,
        avg_volume_5d=500_000,
        same_time_avg_volume=1_000_000,
        trade_value=45_000_000,
        quote=UsQuote("NVDA", "ND", bid=101.20, ask=101.21, last=101.22, updated_at=now - timedelta(seconds=60)),
    )

    decision = evaluate_1m_volume_breakout(candidate, candles, StrategyRuntimeState(account_equity=100_000), now=now)

    assert decision.ready is False
    assert "fresh_quote" in decision.blocked_reasons


def test_backtester_reuses_point_in_time_strategy_decision_without_api_calls():
    now = datetime(2026, 7, 10, 10, 15, tzinfo=ET)
    candles = _breakout_1m_candles("NVDA", "ND", now) + [
        UsCandle("NVDA", "ND", 101.22, 102.50, 101.10, 102.40, 30_000, now + timedelta(minutes=1)),
        UsCandle("NVDA", "ND", 102.40, 103.00, 102.10, 102.80, 20_000, now + timedelta(minutes=2)),
    ]
    candidate = CandidateSnapshot(
        symbol="NVDA",
        exchange="ND",
        price=101.22,
        open_price=99.9,
        day_high=101.25,
        change_rate=3.2,
        cumulative_volume=2_100_000,
        avg_volume_5d=500_000,
        same_time_avg_volume=300_000,
        trade_value=45_000_000,
        quote=UsQuote("NVDA", "ND", bid=101.20, ask=101.21, last=101.22, updated_at=now),
    )

    summary = backtest_single_candidate(
        strategy_id=STRATEGY_1M_VOLUME_BREAKOUT,
        candidate=candidate,
        candles=candles,
        account_equity=100_000,
    )

    # The legacy static candidate claimed a future 3.2% change and 2.1M volume.
    # Point-in-time reconstruction sees only the candles available then and
    # correctly refuses to invent a historical entry from those future values.
    assert summary.total_trades == 0


def test_backtester_time_exit_uses_original_entry_time_and_breaks_out_costs():
    entry_time = datetime(2026, 7, 10, 10, 0, tzinfo=ET)
    decision = StrategyDecision(
        strategy_id=STRATEGY_1M_VOLUME_BREAKOUT,
        symbol="NVDA",
        exchange="ND",
        ready=True,
        entry_price=100.0,
        stop_price=99.0,
        quantity=2,
    )
    candle = UsCandle(
        "NVDA",
        "ND",
        100.4,
        100.7,
        100.2,
        100.5,
        10_000,
        entry_time + timedelta(minutes=30),
    )
    costs = BacktestCostModel(
        commission_rate=0.001,
        fx_cost_rate=0.002,
        entry_slippage_pct=0.02,
        exit_slippage_pct=0.02,
        spread_cost_pct=0.03,
        fx_rate_krw_per_usd=1_400,
    )

    trade = _try_exit(decision, [candle], costs, entry_time=entry_time)

    assert trade is not None
    assert trade.exit_reason == "time_exit"
    assert trade.exit_time == candle.timestamp.isoformat()
    assert trade.execution_cost > 0
    assert trade.commission_cost > 0
    assert trade.fx_cost > 0
    assert trade.total_cost == trade.execution_cost + trade.commission_cost + trade.fx_cost
    assert trade.net_pnl == trade.gross_pnl - trade.total_cost
    assert trade.net_pnl_krw == trade.net_pnl * 1_400

    summary = summarize_trades([trade], fx_rate_krw_per_usd=1_400)
    assert summary.total_cost == trade.total_cost
    assert summary.net_pnl_krw == trade.net_pnl_krw


def test_candidate_snapshot_uses_only_candles_available_at_that_time():
    start = datetime(2026, 7, 10, 9, 30, tzinfo=ET)
    future_high = UsCandle("NVDA", "ND", 101, 150, 100, 140, 900_000, start + timedelta(minutes=2))
    known = [
        UsCandle("NVDA", "ND", 100, 101, 99.5, 100.5, 10_000, start),
        UsCandle("NVDA", "ND", 100.5, 102, 100, 101, 20_000, start + timedelta(minutes=1)),
    ]
    candidate = CandidateSnapshot(
        symbol="NVDA",
        exchange="ND",
        price=140,
        open_price=100,
        day_high=150,
        change_rate=40,
        cumulative_volume=930_000,
        same_time_avg_volume=10_000,
        quote=UsQuote("NVDA", "ND", bid=139.9, ask=140.1, last=140, updated_at=future_high.timestamp),
    )

    snapshot = candidate_from_window(candidate, known)

    assert snapshot.price == 101
    assert snapshot.day_high == 102
    assert snapshot.cumulative_volume == 30_000
    assert snapshot.quote is not None
    assert snapshot.quote.updated_at == known[-1].timestamp
    assert snapshot.price != future_high.close


def test_strategy_decision_can_be_persisted_without_sensitive_values(tmp_path):
    now = datetime(2026, 7, 10, 10, 15, tzinfo=ET)
    candles = _breakout_1m_candles("NVDA", "ND", now)
    candidate = CandidateSnapshot(
        symbol="NVDA",
        exchange="ND",
        price=101.22,
        open_price=99.9,
        day_high=101.25,
        change_rate=3.2,
        cumulative_volume=2_100_000,
        avg_volume_5d=500_000,
        same_time_avg_volume=1_000_000,
        trade_value=45_000_000,
        quote=UsQuote("NVDA", "ND", bid=101.20, ask=101.21, last=101.22, updated_at=now),
    )
    decision = evaluate_1m_volume_breakout(candidate, candles, StrategyRuntimeState(account_equity=100_000), now=now)
    store = SQLiteStore(tmp_path / "engine.sqlite3")
    try:
        store.record_us_strategy_decision(decision)
        row = store.connection.execute("SELECT strategy_id, symbol, ready, criteria_json FROM us_strategy_decisions").fetchone()
    finally:
        store.close()

    assert row["strategy_id"] == STRATEGY_1M_VOLUME_BREAKOUT
    assert row["symbol"] == "NVDA"
    assert "token" not in row["criteria_json"].lower()
    assert "secret" not in row["criteria_json"].lower()


def test_et_timezone_uses_dst_offset_for_summer_and_winter():
    summer = datetime(2026, 7, 10, 10, 0, tzinfo=ET)
    winter = datetime(2026, 1, 10, 10, 0, tzinfo=ET)

    assert summer.utcoffset() != winter.utcoffset()


def _flat_candles(symbol: str, exchange: str, *, count: int) -> list[UsCandle]:
    start = datetime(2026, 7, 10, 9, 30, tzinfo=ET)
    return [
        UsCandle(symbol, exchange, 100, 100.2, 99.8, 100.05, 10_000, start + timedelta(minutes=index))
        for index in range(count)
    ]


def _breakout_1m_candles(symbol: str, exchange: str, now: datetime) -> list[UsCandle]:
    start = now - timedelta(minutes=79)
    candles: list[UsCandle] = []
    price = 100.0
    for index in range(74):
        close = price + 0.01
        candles.append(UsCandle(symbol, exchange, price, close + 0.12, price - 0.12, close, 9_000, start + timedelta(minutes=index)))
        price = close
    base_time = start + timedelta(minutes=74)
    setup = [
        (100.74, 100.94, 100.60, 100.88, 9_000),
        (100.88, 101.02, 100.75, 100.96, 9_000),
        (100.96, 101.10, 100.82, 101.01, 9_000),
        (101.01, 101.18, 100.88, 101.09, 9_000),
        (101.09, 101.19, 100.92, 101.12, 9_000),
        (101.05, 101.24, 100.98, 101.22, 25_000),
    ]
    for offset, values in enumerate(setup):
        candles.append(UsCandle(symbol, exchange, *values, base_time + timedelta(minutes=offset)))
    return candles
