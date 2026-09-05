from __future__ import annotations

import argparse
import json
from pathlib import Path

from trading_engine.backtesting.walk_forward import build_walk_forward_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an expanding-window US strategy report")
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--minimum-trades", type=int, default=500)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    trades: list[dict[str, object]] = []
    for path in args.inputs:
        payload = json.loads(path.read_text(encoding="utf-8"))
        source = payload.get("summary", payload) if isinstance(payload, dict) else {}
        rows = source.get("trades", []) if isinstance(source, dict) else []
        if not isinstance(rows, list):
            parser.error(f"trades must be a list: {path}")
        trades.extend(item for item in rows if isinstance(item, dict))
    try:
        report = build_walk_forward_report(trades, minimum_trades=args.minimum_trades)
    except ValueError as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(f"WALK_FORWARD_STATUS={report['status']} total_trades={report['totalTrades']} shortfall={report['shortfallTrades']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
