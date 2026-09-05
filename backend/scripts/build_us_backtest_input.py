from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime
import json
from pathlib import Path
from typing import Any


SUPPORTED_STRATEGIES = {"US_1M_VOLUME_BREAKOUT", "US_5M_TREND_PULLBACK"}


class BacktestInputBuildError(ValueError):
    pass


def build_backtest_input(
    paths: list[Path],
    *,
    strategy_id: str,
    account_equity_usd: float,
) -> dict[str, object]:
    if strategy_id not in SUPPORTED_STRATEGIES:
        raise BacktestInputBuildError("unsupported strategy")
    if account_equity_usd <= 0:
        raise BacktestInputBuildError("account equity must be positive")

    symbol = ""
    exchange = ""
    candles_by_timestamp: dict[str, dict[str, object]] = {}
    fx_by_date: dict[str, float] = {}
    for path in paths:
        payload = _load_dataset(path)
        dataset_symbol = str(payload.get("symbol") or "").strip().upper()
        dataset_exchange = str(payload.get("exchange") or "").strip().upper()
        if not symbol:
            symbol, exchange = dataset_symbol, dataset_exchange
        if (dataset_symbol, dataset_exchange) != (symbol, exchange):
            raise BacktestInputBuildError("all datasets must use the same symbol and exchange")
        for row in payload.get("candles", []):
            if not isinstance(row, dict):
                continue
            normalized = _candle(row)
            candles_by_timestamp[str(normalized["timestamp"])] = normalized
        for row in payload.get("fxRates", []):
            if not isinstance(row, dict):
                continue
            day = str(row.get("date") or "")
            rate = _positive_float(row.get("krwPerUsd"))
            if len(day) == 8 and rate is not None:
                fx_by_date[day] = rate

    candles = sorted(candles_by_timestamp.values(), key=lambda row: str(row["timestamp"]))
    if len(candles) < 61:
        raise BacktestInputBuildError("at least 61 unique candles are required")

    sessions: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in candles:
        sessions[str(row["businessDate"])].append(row)
    session_rows = list(sessions.values())
    average_daily_volume = max(
        1,
        round(sum(sum(int(row["volume"]) for row in rows) for rows in session_rows) / len(session_rows)),
    )
    same_time_average_volume = max(
        1,
        round(sum(sum(int(row["volume"]) for row in rows[:60]) for rows in session_rows) / len(session_rows)),
    )
    first = candles[0]
    first_session = sessions[str(first["businessDate"])]
    first_price = float(first["close"])
    spread = first_price * 0.001
    candidate = {
        "symbol": symbol,
        "exchange": exchange,
        "price": first_price,
        "openPrice": float(first_session[0]["open"]),
        "dayHigh": max(float(row["high"]) for row in first_session),
        "changeRate": 0.0,
        "cumulativeVolume": max(1, int(first["volume"])),
        "avgVolume5d": average_daily_volume,
        "sameTimeAvgVolume": same_time_average_volume,
        "tradeValue": max(1.0, sum(float(row["close"]) * int(row["volume"]) for row in first_session)),
        "quote": {
            "bid": max(0.0001, first_price - spread / 2),
            "ask": first_price + spread / 2,
            "last": first_price,
            "updatedAt": str(first["timestamp"]),
        },
    }
    latest_fx = fx_by_date[sorted(fx_by_date)[-1]] if fx_by_date else None
    result: dict[str, object] = {
        "strategyId": strategy_id,
        "accountEquityUsd": account_equity_usd,
        "candidate": candidate,
        "costModel": {
            "commissionRate": 0.0005,
            "fxCostRate": 0.001,
            "entrySlippagePct": 0.03,
            "exitSlippagePct": 0.03,
            "spreadCostPct": 0.05,
        },
        "candles": [
            {key: row[key] for key in ("open", "high", "low", "close", "volume", "timestamp")}
            for row in candles
        ],
        "coverage": {
            "sourceFiles": len(paths),
            "uniqueCandles": len(candles),
            "tradingDates": sorted(sessions),
        },
    }
    if latest_fx is not None:
        result["fxRateKrwPerUsd"] = latest_fx
    return result


def _load_dataset(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BacktestInputBuildError(f"dataset is not readable: {path.name}") from exc
    if not isinstance(payload, dict) or payload.get("datasetType") != "kiwoom-us-minute-chart-with-fx":
        raise BacktestInputBuildError(f"unsupported dataset: {path.name}")
    return payload


def _candle(row: dict[str, object]) -> dict[str, object]:
    timestamp = str(row.get("timestamp") or "")
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BacktestInputBuildError("candle timestamp is invalid") from exc
    if parsed.tzinfo is None:
        raise BacktestInputBuildError("candle timestamp must include timezone")
    business_date = str(row.get("businessDate") or "")
    if len(business_date) != 8 or not business_date.isdigit():
        raise BacktestInputBuildError("candle business date is invalid")
    values = {name: _positive_float(row.get(name)) for name in ("open", "high", "low", "close")}
    if any(value is None for value in values.values()):
        raise BacktestInputBuildError("candle OHLC must be positive")
    volume = _nonnegative_int(row.get("volume"))
    return {
        "timestamp": parsed.isoformat(),
        "businessDate": business_date,
        **values,
        "volume": volume,
    }


def _positive_float(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _nonnegative_int(value: object) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise BacktestInputBuildError("candle volume is invalid") from exc
    if parsed < 0:
        raise BacktestInputBuildError("candle volume is invalid")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge read-only Kiwoom chart datasets into one backtest input")
    parser.add_argument("datasets", nargs="+", type=Path)
    parser.add_argument("--strategy", choices=sorted(SUPPORTED_STRATEGIES), required=True)
    parser.add_argument("--account-equity-usd", type=float, default=10_000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = build_backtest_input(
            args.datasets,
            strategy_id=args.strategy,
            account_equity_usd=args.account_equity_usd,
        )
    except BacktestInputBuildError as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    coverage = result["coverage"]
    assert isinstance(coverage, dict)
    print(
        "BACKTEST_INPUT_READY=true "
        f"strategy={result['strategyId']} candles={coverage['uniqueCandles']} dates={len(coverage['tradingDates'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
