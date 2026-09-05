from __future__ import annotations

from datetime import datetime, timedelta, timezone

from trading_engine.backtesting.walk_forward import build_walk_forward_report


def _trades(count: int) -> list[dict[str, object]]:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return [
        {
            "entry_time": (start + timedelta(hours=index)).isoformat(),
            "net_pnl": 1.0 if index % 3 else -0.5,
            "symbol": "NVDA" if index % 2 else "AAPL",
        }
        for index in range(count)
    ]


def test_walk_forward_blocks_profitability_claim_below_500_trades():
    report = build_walk_forward_report(_trades(120))

    assert report["status"] == "insufficient_sample"
    assert report["shortfallTrades"] == 380
    assert report["profitabilityClaimAllowed"] is False
    assert report["outOfSampleNetPnl"] is None
    assert sum(fold["test_trades"] for fold in report["folds"]) == 48


def test_walk_forward_uses_strictly_earlier_expanding_training_windows():
    report = build_walk_forward_report(list(reversed(_trades(500))))

    assert report["status"] == "ready"
    assert report["profitabilityClaimAllowed"] is True
    assert report["initialTrainTrades"] == 300
    assert report["outOfSampleTrades"] == 200
    assert len(report["folds"]) == 4
    assert all(fold["train_end"] < fold["test_start"] for fold in report["folds"])
    assert [fold["train_trades"] for fold in report["folds"]] == [300, 350, 400, 450]
