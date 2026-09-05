from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.liquidity_analysis_service import build_liquidity_analysis
from app.services.realtime_event_store import record_realtime_event


def test_liquidity_analysis_tracks_large_wall_and_keeps_signal_advisory(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(tmp_path / "events.sqlite3"))
    start = datetime(2026, 9, 4, 13, 0, tzinfo=timezone.utc)
    for index, price in enumerate((100.0, 101.0, 102.0)):
        at = (start + timedelta(hours=index)).isoformat()
        record_realtime_event({
            "type": "TICK", "symbol": "NVDA", "provider": "kiwoom",
            "price": price, "volume": 1_000 + index * 100, "receivedAt": at,
        })
    for offset, cumulative_volume in ((1.2, 1_200), (1.8, 1_260)):
        record_realtime_event({
            "type": "TICK", "symbol": "NVDA", "provider": "kiwoom",
            "price": 100, "volume": cumulative_volume,
            "receivedAt": (start + timedelta(seconds=offset)).isoformat(),
        })
    for index, size in enumerate((100, 150, 0)):
        at = (start + timedelta(seconds=index)).isoformat()
        record_realtime_event({
            "type": "ORDERBOOK", "symbol": "NVDA", "provider": "kiwoom", "receivedAt": at,
            "levels": [{"level": 1, "bid": 100, "ask": 101, "bidSize": size, "askSize": 0}],
        })

    result = build_liquidity_analysis("nvda", threshold_krw=10_000_000, fx_krw_per_usd=1_350)

    states = [wall["state"] for frame in result["timeline"] for wall in frame["walls"]]
    assert states == ["appeared", "growing", "disappeared"]
    disappeared = result["timeline"][-1]["walls"][0]
    assert disappeared["exitInference"] == "likely-execution"
    assert [item["timeframe"] for item in result["timeframes"]] == ["1m", "5m", "1h"]
    assert all(item["dataSufficient"] for item in result["timeframes"])
    assert result["executionAuthorized"] is False
    assert result["signal"]["executionAuthorized"] is False
    assert result["signalHistory"][0]["executionAuthorized"] is False
    assert result["streamOwner"] == "fastapi-shared-kiwoom-websocket"


def test_liquidity_analysis_rejects_empty_symbol():
    try:
        build_liquidity_analysis("../")
    except ValueError as exc:
        assert str(exc) == "US symbol is required"
    else:
        raise AssertionError("unsafe empty symbols must be rejected")


def test_liquidity_signal_requires_fresh_connected_market_observation(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(tmp_path / "quality.sqlite3"))
    market_open = datetime(2026, 9, 4, 14, 0, tzinfo=timezone.utc)
    received_at = (market_open - timedelta(seconds=2)).isoformat()
    record_realtime_event({
        "type": "TICK", "symbol": "NVDA", "provider": "kiwoom",
        "price": 100, "volume": 1_000, "receivedAt": received_at,
    })
    record_realtime_event({
        "type": "ORDERBOOK", "symbol": "NVDA", "provider": "kiwoom",
        "receivedAt": received_at,
        "levels": [{"level": 1, "bid": 100, "ask": 101, "bidSize": 100, "askSize": 0}],
    })
    timeframes = [
        {"timeframe": label, "seconds": seconds, "candleCount": 100, "latestClose": 100,
         "ema9": 101, "ema20": 99, "changePct": 0.1, "trend": "bullish",
         "pullback": False, "dataSufficient": True, "candles": [],
         "latestCandleAtUtc": (market_open - timedelta(seconds=min(seconds, 60))).isoformat()}
        for label, seconds in (("1m", 60), ("5m", 300), ("1h", 3600))
    ]
    chart_context = {
        "source": "kiwoom-usa06011",
        "availableTimeframes": ["1m", "5m", "1h"],
    }
    monitor = {"running": True, "connected": True}

    ready = build_liquidity_analysis(
        "NVDA", fx_krw_per_usd=1_350, timeframe_context=timeframes,
        chart_context=chart_context, monitor_context=monitor, observation_now=market_open,
    )
    assert ready["observationQuality"]["state"] == "ready"
    assert ready["observationQuality"]["signalEligible"] is True
    assert ready["signal"]["action"] == "BUY_WATCH"
    assert ready["signal"]["expiresAt"] is not None
    assert ready["signal"]["executionAuthorized"] is False

    weekend = build_liquidity_analysis(
        "NVDA", fx_krw_per_usd=1_350, timeframe_context=timeframes,
        chart_context=chart_context, monitor_context=monitor,
        observation_now=datetime(2026, 9, 5, 14, 0, tzinfo=timezone.utc),
    )
    assert weekend["observationQuality"]["state"] == "off_hours"
    assert weekend["observationQuality"]["signalEligible"] is False
    assert weekend["signal"]["action"] == "WATCH"
    assert weekend["signal"]["expiresAt"] is None
    assert weekend["executionAuthorized"] is False

    stale_timeframes = [
        {**item, "latestCandleAtUtc": (market_open - timedelta(days=1)).isoformat()}
        for item in timeframes
    ]
    stale_chart = build_liquidity_analysis(
        "NVDA", fx_krw_per_usd=1_350, timeframe_context=stale_timeframes,
        chart_context=chart_context, monitor_context=monitor, observation_now=market_open,
    )
    assert stale_chart["observationQuality"]["state"] == "degraded"
    assert stale_chart["observationQuality"]["staleTimeframes"] == ["1m", "5m", "1h"]
    assert stale_chart["observationQuality"]["signalEligible"] is False
    assert stale_chart["signal"]["action"] == "WATCH"


def test_liquidity_websocket_requires_authentication():
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app).websocket_connect("/api/realtime/us/liquidity/ws") as websocket:
        websocket.send_json({"type": "AUTH", "token": ""})
        assert websocket.receive_json() == {"type": "ERROR", "errorType": "AUTH_REQUIRED"}
