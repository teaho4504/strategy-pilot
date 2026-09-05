from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime
import json
import math
from pathlib import Path
from typing import Any

from trading_engine.backtesting.us_strategy_backtester import (
    BacktestCostModel,
    backtest_single_candidate,
)
from trading_engine.strategies.us_day_trading import (
    CandidateSnapshot,
    MarketContext,
    STRATEGY_1M_VOLUME_BREAKOUT,
    STRATEGY_5M_TREND_PULLBACK,
    UsCandle,
    UsQuote,
)


SUPPORTED_STRATEGIES = {
    STRATEGY_1M_VOLUME_BREAKOUT,
    STRATEGY_5M_TREND_PULLBACK,
}


class BacktestInputError(ValueError):
    pass


def load_backtest_input(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BacktestInputError("Backtest input must be a readable UTF-8 JSON file") from exc
    if not isinstance(payload, dict):
        raise BacktestInputError("Backtest input root must be an object")
    return payload


def run_backtest_payload(payload: dict[str, Any]) -> dict[str, Any]:
    strategy_id = str(payload.get("strategyId") or "").strip()
    if strategy_id not in SUPPORTED_STRATEGIES:
        raise BacktestInputError("Unsupported strategyId")
    account_equity = _positive_number(payload.get("accountEquityUsd"), "accountEquityUsd")
    candidate = _candidate(payload.get("candidate"))
    candles = _candles(payload.get("candles"), candidate.symbol, candidate.exchange)
    cost_model = _cost_model(payload.get("costModel"), payload.get("fxRateKrwPerUsd"))
    summary = backtest_single_candidate(
        strategy_id=strategy_id,
        candidate=candidate,
        candles=candles,
        account_equity=account_equity,
        cost_model=cost_model,
        market_context=MarketContext(),
    )
    result = asdict(summary)
    if math.isinf(result["profit_factor"]):
        result["profit_factor"] = None
    return {
        "strategyId": strategy_id,
        "symbol": candidate.symbol,
        "exchange": candidate.exchange,
        "currency": "USD",
        "krwConverted": cost_model.fx_rate_krw_per_usd is not None,
        "summary": result,
    }


def _candidate(raw: Any) -> CandidateSnapshot:
    if not isinstance(raw, dict):
        raise BacktestInputError("candidate must be an object")
    symbol = _safe_symbol(raw.get("symbol"))
    exchange = _safe_exchange(raw.get("exchange"))
    quote_raw = raw.get("quote")
    if not isinstance(quote_raw, dict):
        raise BacktestInputError("candidate.quote must be an object")
    quote = UsQuote(
        symbol=symbol,
        exchange=exchange,
        bid=_positive_number(quote_raw.get("bid"), "candidate.quote.bid"),
        ask=_positive_number(quote_raw.get("ask"), "candidate.quote.ask"),
        last=_positive_number(quote_raw.get("last"), "candidate.quote.last"),
        updated_at=_aware_datetime(quote_raw.get("updatedAt"), "candidate.quote.updatedAt"),
    )
    return CandidateSnapshot(
        symbol=symbol,
        exchange=exchange,
        price=_positive_number(raw.get("price"), "candidate.price"),
        open_price=_positive_number(raw.get("openPrice"), "candidate.openPrice"),
        day_high=_positive_number(raw.get("dayHigh"), "candidate.dayHigh"),
        change_rate=_number(raw.get("changeRate"), "candidate.changeRate"),
        cumulative_volume=_positive_integer(raw.get("cumulativeVolume"), "candidate.cumulativeVolume"),
        avg_volume_5d=_positive_integer(raw.get("avgVolume5d"), "candidate.avgVolume5d"),
        same_time_avg_volume=_positive_integer(raw.get("sameTimeAvgVolume"), "candidate.sameTimeAvgVolume"),
        trade_value=_positive_number(raw.get("tradeValue"), "candidate.tradeValue"),
        is_common_stock=raw.get("isCommonStock") is not False,
        is_leveraged_or_inverse_etf=raw.get("isLeveragedOrInverseEtf") is True,
        quote=quote,
    )


def _candles(raw: Any, symbol: str, exchange: str) -> list[UsCandle]:
    if not isinstance(raw, list) or len(raw) < 61:
        raise BacktestInputError("candles must contain at least 61 rows")
    result: list[UsCandle] = []
    for index, row in enumerate(raw):
        if not isinstance(row, dict):
            raise BacktestInputError(f"candles[{index}] must be an object")
        result.append(UsCandle(
            symbol=symbol,
            exchange=exchange,
            open=_positive_number(row.get("open"), f"candles[{index}].open"),
            high=_positive_number(row.get("high"), f"candles[{index}].high"),
            low=_positive_number(row.get("low"), f"candles[{index}].low"),
            close=_positive_number(row.get("close"), f"candles[{index}].close"),
            volume=_positive_integer(row.get("volume"), f"candles[{index}].volume", allow_zero=True),
            timestamp=_aware_datetime(row.get("timestamp"), f"candles[{index}].timestamp"),
        ))
    return result


def _cost_model(raw: Any, fx_rate: Any) -> BacktestCostModel:
    values = raw if isinstance(raw, dict) else {}
    return BacktestCostModel(
        commission_rate=_non_negative_number(values.get("commissionRate", 0.0005), "costModel.commissionRate"),
        fx_cost_rate=_non_negative_number(values.get("fxCostRate", 0.001), "costModel.fxCostRate"),
        entry_slippage_pct=_non_negative_number(values.get("entrySlippagePct", 0.03), "costModel.entrySlippagePct"),
        exit_slippage_pct=_non_negative_number(values.get("exitSlippagePct", 0.03), "costModel.exitSlippagePct"),
        spread_cost_pct=_non_negative_number(values.get("spreadCostPct", 0.05), "costModel.spreadCostPct"),
        fx_rate_krw_per_usd=(
            _positive_number(fx_rate, "fxRateKrwPerUsd") if fx_rate is not None else None
        ),
    )


def _aware_datetime(value: Any, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise BacktestInputError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise BacktestInputError(f"{label} must include a timezone offset")
    return parsed


def _safe_symbol(value: Any) -> str:
    symbol = "".join(ch for ch in str(value or "").upper().strip() if ch.isalnum() or ch in {".", "-"})
    if not symbol or len(symbol) > 12:
        raise BacktestInputError("candidate.symbol is invalid")
    return symbol


def _safe_exchange(value: Any) -> str:
    exchange = str(value or "").upper().strip()
    if exchange not in {"ND", "NY", "NA"}:
        raise BacktestInputError("candidate.exchange is invalid")
    return exchange


def _number(value: Any, label: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise BacktestInputError(f"{label} must be numeric") from exc
    if not math.isfinite(parsed):
        raise BacktestInputError(f"{label} must be finite")
    return parsed


def _positive_number(value: Any, label: str) -> float:
    parsed = _number(value, label)
    if parsed <= 0:
        raise BacktestInputError(f"{label} must be positive")
    return parsed


def _non_negative_number(value: Any, label: str) -> float:
    parsed = _number(value, label)
    if parsed < 0:
        raise BacktestInputError(f"{label} must be non-negative")
    return parsed


def _positive_integer(value: Any, label: str, *, allow_zero: bool = False) -> int:
    parsed = _number(value, label)
    integer = int(parsed)
    if integer != parsed or integer < (0 if allow_zero else 1):
        raise BacktestInputError(f"{label} must be a positive integer")
    return integer


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a local US strategy backtest from historical JSON")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = run_backtest_payload(load_backtest_input(args.input))
    except BacktestInputError as exc:
        parser.error(str(exc))
    serialized = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
        summary = result["summary"]
        assert isinstance(summary, dict)
        print(
            "BACKTEST_READY=true "
            f"strategy={result['strategyId']} trades={summary['total_trades']} net_pnl={summary['net_pnl']}"
        )
    else:
        print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
