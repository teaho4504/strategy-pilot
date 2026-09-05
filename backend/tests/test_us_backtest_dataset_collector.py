from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.schemas.market import UsChartCandle, UsChartResponse
from app.schemas.us_account import UsDailyAccountReturnRow, UsDailyAccountReturnSummary
from app.services.market_ranking_service import MarketRankingService
from scripts import collect_us_backtest_dataset as collector
from scripts.collect_us_backtest_dataset import BacktestDatasetError, _chart_timestamp, _load_fx_csv, collect_dataset
from trading_engine.providers.kiwoom_us.schemas import UsReadOnlyTrResponse


def test_market_chart_history_uses_bounded_continuation_path(monkeypatch):
    service = MarketRankingService()
    calls: list[tuple[str, dict[str, object]]] = []

    async def fake_execute_all(tr_id: str, body: dict[str, object], **kwargs):
        calls.append((tr_id, body))
        assert kwargs["max_pages"] == 7
        assert kwargs["page_delay_seconds"] == 0.25
        assert kwargs["require_complete"] is False
        return UsReadOnlyTrResponse(
            tr_id=tr_id,
            return_code="0",
            return_msg="OK",
            data={
                "result_list": [
                    {
                        "cntr_tm": "20260812100000",
                        "cur_prc": "100.1",
                        "open_pric": "100",
                        "high_pric": "100.2",
                        "low_pric": "99.9",
                        "trde_qty": "1000",
                    }
                ]
            },
        )

    monkeypatch.setattr("app.services.market_ranking_service.us_account_service._execute_all", fake_execute_all)

    result = asyncio.run(service.get_us_chart(
        timeframe="minute",
        symbol="NVDA",
        exchange="ND",
        start_date="20260801",
        tick_scope="1",
        all_pages=True,
        continuation_pages=7,
        continuation_delay_seconds=0.25,
        require_complete=False,
    ))

    assert result.trId == "usa06011"
    assert len(result.candles) == 1
    assert calls[0][0] == "usa06011"
    assert calls[0][1]["strt_dt"] == "20260801"


def test_chart_timestamp_requires_complete_et_timestamp():
    parsed = _chart_timestamp("101500", "20260812")

    assert parsed.isoformat().startswith("2026-08-12T10:15:00")
    assert parsed.utcoffset() is not None
    with pytest.raises(BacktestDatasetError, match="incomplete"):
        _chart_timestamp("1015", "20260812")


def test_chart_timestamp_normalizes_kiwoom_24_hour_boundary():
    parsed = _chart_timestamp("240100", "20260811")
    extended = _chart_timestamp("250100", "20260811")

    assert parsed.isoformat().startswith("2026-08-12T00:01:00")
    assert extended.isoformat().startswith("2026-08-12T01:01:00")
    with pytest.raises(BacktestDatasetError, match="invalid"):
        _chart_timestamp("480100", "20260811")


def test_collector_exports_only_chart_and_fx_fields(monkeypatch):
    async def fake_session(profile):
        return SimpleNamespace()

    async def fake_chart(**kwargs):
        assert kwargs["all_pages"] is True
        assert kwargs["continuation_pages"] == 20
        assert kwargs["continuation_delay_seconds"] == 0.5
        assert kwargs["require_complete"] is False
        return UsChartResponse(
            trId="usa06011",
            code="NVDA",
            exchange="ND",
            timeframe="minute",
            source="fixture",
            updatedAt="2026-08-12T00:00:00+00:00",
            candles=[
                UsChartCandle(
                    open=100,
                    high=101,
                    low=99,
                    close=100.5,
                    volume=1000,
                    executedAt="20260812100000",
                    businessDate="20260812",
                )
            ],
            continuationComplete=False,
            continuationPages=3,
        )

    async def fake_returns(from_date, to_date):
        return UsDailyAccountReturnSummary(
            trId="usa21670",
            returnCode="0",
            returnMessage="OK",
            schemaKeys=[],
            rows=[
                    UsDailyAccountReturnRow(
                        baseDate="20260812",
                        exchangeRate="1395.25",
                        stockValuation="sensitive-account-value-not-exported",
                        unknownFields={},
                    )
            ],
            source="fixture",
            updatedAt="2026-08-12T00:00:00+00:00",
        )

    monkeypatch.setattr(collector.kiwoom_session_manager, "create_session_from_cli_profile", fake_session)
    monkeypatch.setattr(collector.market_ranking_service, "get_us_chart", fake_chart)
    monkeypatch.setattr(collector.us_account_service, "get_daily_returns", fake_returns)

    dataset = asyncio.run(collect_dataset(
        profile="real-profile",
        symbol="NVDA",
        exchange="ND",
        start_date="20260801",
        tick_scope="1",
    ))

    assert dataset["candles"][0]["timestamp"].startswith("2026-08-12T10:00:00")
    assert dataset["fxRates"] == [{"date": "20260812", "krwPerUsd": 1395.25}]
    assert dataset["coverage"]["missingFxDates"] == []
    assert dataset["coverage"]["continuationComplete"] is False
    assert dataset["coverage"]["continuationPages"] == 3
    assert "sensitive-account-value" not in str(dataset)


def test_official_fx_csv_is_filtered_to_candle_dates(tmp_path):
    fx_csv = tmp_path / "official-fx.csv"
    fx_csv.write_text(
        "date,krwPerUsd\n20260811,1390.10\n20260812,1395.25\n",
        encoding="utf-8",
    )

    rows = _load_fx_csv(fx_csv, ["20260812"])

    assert rows == [{
        "date": "20260812",
        "krwPerUsd": 1395.25,
        "sourceDate": "20260812",
        "carryForwardDays": 0,
    }]


def test_official_fx_csv_carries_only_prior_observation_forward(tmp_path):
    fx_csv = tmp_path / "official-fx.csv"
    fx_csv.write_text(
        "date,krwPerUsd\n20260807,1390.10\n20260813,1401.00\n",
        encoding="utf-8",
    )

    rows = _load_fx_csv(fx_csv, ["20260812"])

    assert rows[0]["sourceDate"] == "20260807"
    assert rows[0]["carryForwardDays"] == 5
    assert rows[0]["krwPerUsd"] == 1390.1


def test_fx_csv_rejects_missing_required_columns(tmp_path):
    fx_csv = tmp_path / "bad-fx.csv"
    fx_csv.write_text("day,rate\n20260812,1395.25\n", encoding="utf-8")

    with pytest.raises(BacktestDatasetError, match="date,krwPerUsd"):
        _load_fx_csv(fx_csv, ["20260812"])
