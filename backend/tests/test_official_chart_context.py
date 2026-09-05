from __future__ import annotations

import asyncio
from datetime import date

from app.schemas.market import UsChartCandle, UsChartResponse
from app.services.official_chart_context_service import OfficialChartContextService
from app.services.market_ranking_service import _default_chart_start, parse_kiwoom_us_candle_time


def test_official_chart_context_requests_1_5_60_minute_scopes(monkeypatch):
    from app.services import official_chart_context_service as module

    scopes: list[str] = []

    async def fake_chart(**kwargs):
        scopes.append(kwargs["tick_scope"])
        candles = [
            UsChartCandle(close=100 + index, volume=1000 + index, open=99 + index,
                          high=101 + index, low=98 + index, executedAt=f"20260904120{index}00")
            for index in range(3)
        ]
        return UsChartResponse(trId="usa06011", code="NVDA", exchange="ND", timeframe="minute",
                               source="fixture", updatedAt="2026-09-05T00:00:00+00:00", candles=candles)

    monkeypatch.setattr(module.market_ranking_service, "get_us_chart", fake_chart)
    service = OfficialChartContextService()
    items, meta = asyncio.run(service.get("NVDA", "ND"))

    assert scopes == ["1", "5", "60"]
    assert [item["timeframe"] for item in items] == ["1m", "5m", "1h"]
    assert all(item["trId"] == "usa06011" for item in items)
    assert all(item["continuationComplete"] is True for item in items)
    assert all(item["latestCandleAtUtc"] for item in items)
    assert items[0]["latestCandleAtUtc"] == "2026-09-04T03:02:00+00:00"
    assert items[0]["timestampConvention"] == "kiwoom-us-extended-kst-observed"
    assert meta["source"] == "kiwoom-usa06011"


def test_kiwoom_extended_kst_chart_time_maps_to_us_market_time():
    parsed = parse_kiwoom_us_candle_time("20260828274400")

    assert parsed is not None
    assert parsed.isoformat() == "2026-08-29T03:44:00+09:00"
    assert parsed.astimezone().timestamp() > 0


def test_minute_chart_default_uses_current_as_of_date():
    assert _default_chart_start("minute", today=date(2026, 9, 5)) == "20260905"
    assert _default_chart_start("day", today=date(2026, 9, 5)) == "20260309"
