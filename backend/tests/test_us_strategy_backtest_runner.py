from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from scripts.run_us_strategy_backtest import BacktestInputError, run_backtest_payload
from trading_engine.backtesting.us_strategy_backtester import candidate_from_window
from trading_engine.strategies.us_day_trading import CandidateSnapshot, UsCandle, UsQuote


def _payload() -> dict[str, object]:
    start = datetime(2026, 7, 10, 13, 30, tzinfo=timezone.utc)
    candles = [
        {
            "open": 100.0,
            "high": 100.2,
            "low": 99.8,
            "close": 100.05,
            "volume": 10_000,
            "timestamp": (start + timedelta(minutes=index)).isoformat(),
        }
        for index in range(61)
    ]
    quote_time = candles[-1]["timestamp"]
    return {
        "strategyId": "US_1M_VOLUME_BREAKOUT",
        "accountEquityUsd": 10_000,
        "fxRateKrwPerUsd": 1_400,
        "costModel": {
            "commissionRate": 0.0005,
            "fxCostRate": 0.001,
            "entrySlippagePct": 0.03,
            "exitSlippagePct": 0.03,
            "spreadCostPct": 0.05,
        },
        "candidate": {
            "symbol": "NVDA",
            "exchange": "ND",
            "price": 100.05,
            "openPrice": 100,
            "dayHigh": 100.2,
            "changeRate": 2.0,
            "cumulativeVolume": 1_000_000,
            "avgVolume5d": 500_000,
            "sameTimeAvgVolume": 500_000,
            "tradeValue": 30_000_000,
            "quote": {
                "bid": 100.04,
                "ask": 100.06,
                "last": 100.05,
                "updatedAt": quote_time,
            },
        },
        "candles": candles,
    }


def test_backtest_runner_returns_reproducible_cost_and_fx_summary():
    result = run_backtest_payload(_payload())

    assert result["strategyId"] == "US_1M_VOLUME_BREAKOUT"
    assert result["symbol"] == "NVDA"
    assert result["krwConverted"] is True
    assert result["summary"]["fx_rate_krw_per_usd"] == 1_400
    assert "commission_cost" in result["summary"]
    assert "fx_cost" in result["summary"]
    assert "execution_cost" in result["summary"]


def test_backtest_runner_rejects_timezone_free_candles():
    payload = _payload()
    payload["candles"][0]["timestamp"] = "2026-07-10T09:30:00"

    with pytest.raises(BacktestInputError, match="timezone"):
        run_backtest_payload(payload)


def test_backtest_runner_rejects_negative_cost_assumptions():
    payload = _payload()
    payload["costModel"]["commissionRate"] = -0.1

    with pytest.raises(BacktestInputError, match="non-negative"):
        run_backtest_payload(payload)


def test_candidate_volume_baselines_use_only_prior_sessions():
    first_day = datetime(2026, 8, 10, 13, 30, tzinfo=timezone.utc)
    second_day = first_day + timedelta(days=1)
    candles = [
        UsCandle("NVDA", "ND", 100, 101, 99, 100, 100, first_day + timedelta(minutes=index))
        for index in range(3)
    ] + [
        UsCandle("NVDA", "ND", 101, 102, 100, 101, 200, second_day + timedelta(minutes=index))
        for index in range(2)
    ]
    candidate = CandidateSnapshot(
        symbol="NVDA",
        exchange="ND",
        price=101,
        open_price=101,
        day_high=102,
        change_rate=0,
        cumulative_volume=400,
        avg_volume_5d=999,
        same_time_avg_volume=999,
        quote=UsQuote("NVDA", "ND", 100.9, 101.1, 101, updated_at=second_day),
    )

    rebuilt = candidate_from_window(candidate, candles)

    assert rebuilt.avg_volume_5d == 300
    assert rebuilt.avg_volume_20d == 300
    assert rebuilt.same_time_avg_volume == 200
