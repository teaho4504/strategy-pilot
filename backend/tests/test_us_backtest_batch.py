from __future__ import annotations

import asyncio
import json

from scripts import collect_us_backtest_batch as batch


def test_batch_skips_valid_existing_dataset_without_network(monkeypatch, tmp_path):
    existing = tmp_path / "nvda.json"
    existing.write_text(json.dumps({
        "datasetType": "kiwoom-us-minute-chart-with-fx",
        "symbol": "NVDA",
        "candles": [{"close": 100}],
    }), encoding="utf-8")

    async def fake_session(profile):
        raise AssertionError("session must remain unused when every item is cached")

    async def unexpected_collect(**kwargs):
        raise AssertionError("existing dataset must not be recollected")

    monkeypatch.setattr(batch.kiwoom_session_manager, "create_session_from_cli_profile", fake_session)
    monkeypatch.setattr(batch, "collect_dataset", unexpected_collect)

    report = asyncio.run(batch.collect_batch({
        "profile": "real",
        "items": [{"symbol": "NVDA", "output": "nvda.json"}],
    }, base_dir=tmp_path))

    assert report["skipped"] == 1
    assert report["collected"] == 0
    assert report["failed"] == 0


def test_batch_records_safe_failure_and_continues(monkeypatch, tmp_path):
    async def fake_session(profile):
        return object()

    async def fake_collect(**kwargs):
        if kwargs["symbol"] == "FAIL":
            raise ValueError("secret-value-must-not-leak")
        return {
            "datasetType": "kiwoom-us-minute-chart-with-fx",
            "symbol": kwargs["symbol"],
            "continuationComplete": False,
            "candles": [{"close": 100}],
            "coverage": {"candleCount": 1},
        }

    monkeypatch.setattr(batch.kiwoom_session_manager, "create_session_from_cli_profile", fake_session)
    monkeypatch.setattr(batch, "collect_dataset", fake_collect)

    report = asyncio.run(batch.collect_batch({
        "items": [
            {"symbol": "FAIL", "startDate": "20260801", "output": "fail.json"},
            {"symbol": "NVDA", "startDate": "20260801", "output": "nvda.json"},
        ],
    }, base_dir=tmp_path))

    assert report["failed"] == 1
    assert report["collected"] == 1
    assert report["items"][0]["error"] == "ValueError"
    assert "secret-value" not in str(report)
