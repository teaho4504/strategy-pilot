from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.collect_us_backtest_dataset import BacktestDatasetError, _load_fx_csv


def enrich_dataset(dataset_path: Path, fx_csv_path: Path) -> dict[str, object]:
    try:
        payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BacktestDatasetError("backtest dataset is not readable JSON") from exc
    if not isinstance(payload, dict) or payload.get("datasetType") != "kiwoom-us-minute-chart-with-fx":
        raise BacktestDatasetError("backtest dataset contract mismatch")
    candles = payload.get("candles")
    if not isinstance(candles, list) or not candles:
        raise BacktestDatasetError("backtest dataset contains no candles")
    candle_dates = sorted({
        str(row.get("businessDate"))
        for row in candles
        if isinstance(row, dict) and str(row.get("businessDate") or "")
    })
    fx_rates = _load_fx_csv(fx_csv_path, candle_dates)
    covered = {str(row["date"]) for row in fx_rates}
    payload["fxSource"] = "fred-dexkous-h10-readonly-csv"
    payload["fxRates"] = fx_rates
    coverage = payload.get("coverage")
    if not isinstance(coverage, dict):
        coverage = {}
        payload["coverage"] = coverage
    coverage["fxDateCount"] = len(fx_rates)
    coverage["missingFxDates"] = sorted(set(candle_dates) - covered)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Enrich an existing US backtest dataset with official FX CSV")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--fx-csv", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        enriched = enrich_dataset(args.dataset, args.fx_csv)
    except BacktestDatasetError as exc:
        parser.error(str(exc))
    output = args.output or args.dataset
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(enriched, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    coverage = enriched["coverage"]
    print(
        "BACKTEST_FX_ENRICHED=true "
        f"fx_dates={coverage['fxDateCount']} missing_fx_dates={len(coverage['missingFxDates'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
