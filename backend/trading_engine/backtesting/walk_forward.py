from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class WalkForwardFold:
    fold: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    train_trades: int
    test_trades: int
    test_net_pnl: float
    test_win_rate: float
    test_max_drawdown: float


def build_walk_forward_report(
    trades: list[dict[str, Any]],
    *,
    minimum_trades: int = 500,
    initial_train_ratio: float = 0.6,
    test_folds: int = 4,
) -> dict[str, object]:
    if minimum_trades < 1:
        raise ValueError("minimum_trades must be positive")
    if not 0.5 <= initial_train_ratio < 1:
        raise ValueError("initial_train_ratio must be between 0.5 and 1")
    if test_folds < 1:
        raise ValueError("test_folds must be positive")
    ordered = sorted((_validated_trade(item) for item in trades), key=lambda item: item["entry_time"])
    total = len(ordered)
    train_size = max(1, int(total * initial_train_ratio)) if total else 0
    remaining = total - train_size
    window = max(1, remaining // test_folds) if remaining else 0
    folds: list[dict[str, object]] = []
    if window:
        for fold_index in range(test_folds):
            test_start_index = train_size + fold_index * window
            test_end_index = total if fold_index == test_folds - 1 else min(total, test_start_index + window)
            test = ordered[test_start_index:test_end_index]
            train = ordered[:test_start_index]
            if not test:
                continue
            pnls = [float(item["net_pnl"]) for item in test]
            folds.append(asdict(WalkForwardFold(
                fold=fold_index + 1,
                train_start=train[0]["entry_time"],
                train_end=train[-1]["entry_time"],
                test_start=test[0]["entry_time"],
                test_end=test[-1]["entry_time"],
                train_trades=len(train),
                test_trades=len(test),
                test_net_pnl=sum(pnls),
                test_win_rate=sum(value > 0 for value in pnls) / len(pnls),
                test_max_drawdown=_max_drawdown(pnls),
            )))
    oos_trades = ordered[train_size:] if total else []
    oos_pnls = [float(item["net_pnl"]) for item in oos_trades]
    sufficient = total >= minimum_trades
    return {
        "status": "ready" if sufficient else "insufficient_sample",
        "minimumTrades": minimum_trades,
        "totalTrades": total,
        "shortfallTrades": max(0, minimum_trades - total),
        "profitabilityClaimAllowed": sufficient,
        "initialTrainTrades": train_size,
        "outOfSampleTrades": len(oos_trades),
        "outOfSampleNetPnl": sum(oos_pnls) if sufficient else None,
        "outOfSampleWinRate": (sum(value > 0 for value in oos_pnls) / len(oos_pnls)) if sufficient and oos_pnls else None,
        "outOfSampleMaxDrawdown": _max_drawdown(oos_pnls) if sufficient else None,
        "folds": folds,
    }


def _validated_trade(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("trade must be an object")
    try:
        entry = datetime.fromisoformat(str(raw["entry_time"]).replace("Z", "+00:00"))
        net_pnl = float(raw["net_pnl"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("trade requires entry_time and net_pnl") from exc
    if entry.tzinfo is None:
        raise ValueError("trade entry_time must include timezone")
    return {**raw, "entry_time": entry.isoformat(), "net_pnl": net_pnl}


def _max_drawdown(pnls: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    drawdown = 0.0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown
