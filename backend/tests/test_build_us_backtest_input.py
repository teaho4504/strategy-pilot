from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from scripts.build_us_backtest_input import build_backtest_input


def test_build_backtest_input_merges_and_deduplicates_readonly_datasets(tmp_path):
    start = datetime(2026, 8, 10, 13, 30, tzinfo=timezone.utc)
    rows = [
        {
            "timestamp": (start + timedelta(minutes=minute)).isoformat(),
            "businessDate": "20260810",
            "open": 100,
            "high": 101,
            "low": 99,
            "close": 100.5,
            "volume": 1000,
        }
        for minute in range(61)
    ]
    payload = {
        "datasetType": "kiwoom-us-minute-chart-with-fx",
        "symbol": "NVDA",
        "exchange": "ND",
        "candles": rows,
        "fxRates": [{"date": "20260810", "krwPerUsd": 1400}],
    }
    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    left.write_text(json.dumps(payload), encoding="utf-8")
    right.write_text(json.dumps(payload), encoding="utf-8")

    result = build_backtest_input(
        [left, right],
        strategy_id="US_1M_VOLUME_BREAKOUT",
        account_equity_usd=10_000,
    )

    assert result["coverage"]["sourceFiles"] == 2
    assert result["coverage"]["uniqueCandles"] == 61
    assert result["candidate"]["symbol"] == "NVDA"
    assert result["fxRateKrwPerUsd"] == 1400
