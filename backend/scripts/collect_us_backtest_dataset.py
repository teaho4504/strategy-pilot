from __future__ import annotations

import argparse
import asyncio
import csv
from datetime import datetime, timedelta
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from app.services.kiwoom_session import KiwoomSessionError, kiwoom_session_manager
from app.services.market_ranking_service import MarketRankingError, market_ranking_service
from app.services.us_account_service import US_READONLY_SERVICE_ERRORS, us_account_service
from trading_engine.providers.kiwoom_us.http_sender import KiwoomUsHttpSenderError


ET = ZoneInfo("America/New_York")


class BacktestDatasetError(RuntimeError):
    pass


COLLECTION_ERRORS = (KiwoomSessionError, MarketRankingError, *US_READONLY_SERVICE_ERRORS)


async def collect_dataset(
    *,
    profile: str | None,
    symbol: str,
    exchange: str,
    start_date: str,
    tick_scope: str,
    manual_fx_rate: float | None = None,
    fx_csv: Path | None = None,
    max_pages: int = 20,
    create_session: bool = True,
) -> dict[str, object]:
    clean_symbol = _safe_symbol(symbol)
    clean_exchange = _safe_exchange(exchange)
    clean_start = _safe_date(start_date)
    clean_tick = _safe_tick_scope(tick_scope)
    if manual_fx_rate is not None and manual_fx_rate <= 0:
        raise BacktestDatasetError("manual FX rate must be positive")
    if manual_fx_rate is not None and fx_csv is not None:
        raise BacktestDatasetError("use either manual FX rate or FX CSV, not both")
    if not 1 <= max_pages <= 20:
        raise BacktestDatasetError("max pages must be between 1 and 20")

    try:
        if create_session:
            await kiwoom_session_manager.create_session_from_cli_profile(profile)
        chart = await market_ranking_service.get_us_chart(
            timeframe="minute",
            symbol=clean_symbol,
            exchange=clean_exchange,
            start_date=clean_start,
            tick_scope=clean_tick,
            all_pages=True,
            continuation_pages=max_pages,
            continuation_delay_seconds=0.5,
            require_complete=False,
        )
    except COLLECTION_ERRORS as exc:
        raise BacktestDatasetError(
            f"read-only chart collection failed: {_safe_error_code(exc)}"
        ) from exc

    candles = [_normalized_candle(item) for item in chart.candles]
    candle_dates = sorted({str(item["businessDate"]) for item in candles})
    if not candles:
        raise BacktestDatasetError("read-only chart response contained no valid candles")

    if fx_csv is not None:
        fx_rates = _load_fx_csv(fx_csv, candle_dates)
        fx_source = "user-supplied-official-csv"
    elif manual_fx_rate is not None:
        fx_rates = [
            {"date": day, "krwPerUsd": round(manual_fx_rate, 6)}
            for day in candle_dates
        ]
        fx_source = "manual-explicit-rate"
    else:
        fx_rates = await _read_account_fx_rates(candle_dates)
        fx_source = "kiwoom-usa21670-readonly"

    return {
        "schemaVersion": 1,
        "datasetType": "kiwoom-us-minute-chart-with-fx",
        "symbol": clean_symbol,
        "exchange": clean_exchange,
        "timeframe": "minute",
        "tickScope": clean_tick,
        "startDate": clean_start,
        "chartTrId": chart.trId,
        "fxSource": fx_source,
        "continuationComplete": chart.continuationComplete,
        "continuationPages": chart.continuationPages,
        "candles": candles,
        "fxRates": fx_rates,
        "coverage": {
            "candleCount": len(candles),
            "tradingDateCount": len(candle_dates),
            "fxDateCount": len(fx_rates),
            "missingFxDates": sorted(set(candle_dates) - {str(item["date"]) for item in fx_rates}),
            "continuationComplete": chart.continuationComplete,
            "continuationPages": chart.continuationPages,
        },
    }


async def _read_account_fx_rates(candle_dates: list[str]) -> list[dict[str, object]]:
    if not candle_dates:
        return []
    try:
        summary = await us_account_service.get_daily_returns(
            from_date=candle_dates[0],
            to_date=candle_dates[-1],
        )
    except US_READONLY_SERVICE_ERRORS as exc:
        raise BacktestDatasetError(f"read-only FX lookup failed: {type(exc).__name__}") from exc
    result: list[dict[str, object]] = []
    for row in summary.rows:
        day = _digits(row.baseDate)
        rate = _positive_float(row.exchangeRate)
        if len(day) == 8 and rate is not None:
            result.append({"date": day, "krwPerUsd": round(rate, 6)})
    return _dedupe_fx_rates(result)


def _normalized_candle(item) -> dict[str, object]:
    timestamp = _chart_timestamp(item.executedAt, item.businessDate)
    return {
        "timestamp": timestamp.isoformat(),
        "businessDate": timestamp.strftime("%Y%m%d"),
        "open": float(item.open),
        "high": float(item.high),
        "low": float(item.low),
        "close": float(item.close),
        "volume": int(item.volume),
    }


def _chart_timestamp(executed_at: str | None, business_date: str | None) -> datetime:
    executed_digits = _digits(executed_at)
    business_digits = _digits(business_date)
    combined = executed_digits
    if len(executed_digits) == 6 and len(business_digits) >= 8:
        combined = business_digits[:8] + executed_digits
    if len(combined) < 14:
        raise BacktestDatasetError("chart candle timestamp is incomplete")
    day_text = combined[:8]
    time_text = combined[8:14]
    try:
        hour = int(time_text[:2])
    except ValueError as exc:
        raise BacktestDatasetError(f"chart candle timestamp is invalid: {combined[:14]}") from exc
    if 24 <= hour < 48:
        try:
            base_day = datetime.strptime(day_text, "%Y%m%d")
            normalized_time = datetime.strptime(f"{hour - 24:02d}" + time_text[2:], "%H%M%S").time()
        except ValueError as exc:
            raise BacktestDatasetError(f"chart candle timestamp is invalid: {combined[:14]}") from exc
        return datetime.combine(base_day.date() + timedelta(days=1), normalized_time, tzinfo=ET)
    try:
        return datetime.strptime(combined[:14], "%Y%m%d%H%M%S").replace(tzinfo=ET)
    except ValueError as exc:
        raise BacktestDatasetError(f"chart candle timestamp is invalid: {combined[:14]}") from exc


def _dedupe_fx_rates(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    by_date = {str(row["date"]): row for row in rows}
    return [by_date[day] for day in sorted(by_date)]


def _load_fx_csv(path: Path, candle_dates: list[str]) -> list[dict[str, object]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or not {"date", "krwPerUsd"}.issubset(reader.fieldnames):
                raise BacktestDatasetError("FX CSV requires date,krwPerUsd columns")
            observations: dict[str, float] = {}
            for index, row in enumerate(reader, start=2):
                day = _safe_date(str(row.get("date") or ""))
                rate = _positive_float(row.get("krwPerUsd"))
                if rate is None:
                    raise BacktestDatasetError(f"FX CSV row {index} rate must be positive")
                observations[day] = rate
    except OSError as exc:
        raise BacktestDatasetError("FX CSV is not readable") from exc
    rows: list[dict[str, object]] = []
    sorted_observation_dates = sorted(observations)
    for candle_day in candle_dates:
        eligible = [day for day in sorted_observation_dates if day <= candle_day]
        if not eligible:
            continue
        source_day = eligible[-1]
        carry_days = (
            datetime.strptime(candle_day, "%Y%m%d")
            - datetime.strptime(source_day, "%Y%m%d")
        ).days
        if carry_days > 7:
            continue
        rows.append({
            "date": candle_day,
            "krwPerUsd": round(observations[source_day], 6),
            "sourceDate": source_day,
            "carryForwardDays": carry_days,
        })
    return _dedupe_fx_rates(rows)


def _safe_symbol(value: str) -> str:
    symbol = "".join(ch for ch in str(value).upper().strip() if ch.isalnum() or ch in {".", "-"})
    if not symbol or len(symbol) > 12:
        raise BacktestDatasetError("symbol is invalid")
    return symbol


def _safe_exchange(value: str) -> str:
    exchange = str(value).upper().strip()
    if exchange not in {"ND", "NY", "NA"}:
        raise BacktestDatasetError("exchange is invalid")
    return exchange


def _safe_date(value: str) -> str:
    clean = _digits(value)
    if len(clean) != 8:
        raise BacktestDatasetError("start date must be YYYYMMDD")
    try:
        datetime.strptime(clean, "%Y%m%d")
    except ValueError as exc:
        raise BacktestDatasetError("start date is invalid") from exc
    return clean


def _safe_tick_scope(value: str) -> str:
    clean = str(value).strip()
    if clean not in {"1", "3", "5", "10", "15", "30", "60"}:
        raise BacktestDatasetError("tick scope is unsupported")
    return clean


def _digits(value: object) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _positive_float(value: object) -> float | None:
    try:
        parsed = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _safe_error_code(exc: Exception) -> str:
    if isinstance(exc, KiwoomUsHttpSenderError):
        return f"{exc.error_type}:http_{exc.http_status or 'none'}"
    return type(exc).__name__


async def _main_async(args) -> int:
    dataset = await collect_dataset(
        profile=args.profile,
        symbol=args.symbol,
        exchange=args.exchange,
        start_date=args.start_date,
        tick_scope=args.tick_scope,
        manual_fx_rate=args.fx_rate_krw,
        fx_csv=args.fx_csv,
        max_pages=args.max_pages,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    coverage = dataset["coverage"]
    print(
        "BACKTEST_DATASET_READY=true "
        f"symbol={dataset['symbol']} candles={coverage['candleCount']} "
        f"dates={coverage['tradingDateCount']} fx_dates={coverage['fxDateCount']}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect a read-only Kiwoom US minute-chart backtest dataset")
    parser.add_argument("--profile")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--exchange", default="ND")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--tick-scope", default="1")
    parser.add_argument("--fx-rate-krw", type=float)
    parser.add_argument("--fx-csv", type=Path)
    parser.add_argument("--max-pages", type=int, default=20)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        return asyncio.run(_main_async(args))
    except BacktestDatasetError as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
