from __future__ import annotations

import json

from scripts.enrich_us_backtest_fx import enrich_dataset


def test_existing_dataset_is_enriched_without_refetching_chart(tmp_path):
    dataset = tmp_path / "dataset.json"
    dataset.write_text(json.dumps({
        "schemaVersion": 1,
        "datasetType": "kiwoom-us-minute-chart-with-fx",
        "symbol": "NVDA",
        "candles": [{"businessDate": "20260812", "close": 100}],
        "fxRates": [],
        "fxSource": "missing",
        "coverage": {"fxDateCount": 0, "missingFxDates": ["20260812"]},
    }), encoding="utf-8")
    fx_csv = tmp_path / "fred.csv"
    fx_csv.write_text("date,krwPerUsd\n20260807,1390.10\n", encoding="utf-8")

    result = enrich_dataset(dataset, fx_csv)

    assert result["fxSource"] == "fred-dexkous-h10-readonly-csv"
    assert result["fxRates"][0]["date"] == "20260812"
    assert result["fxRates"][0]["sourceDate"] == "20260807"
    assert result["coverage"]["missingFxDates"] == []
