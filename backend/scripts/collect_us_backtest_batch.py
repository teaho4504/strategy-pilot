from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path

from app.services.kiwoom_session import KiwoomSessionError, kiwoom_session_manager
from scripts.collect_us_backtest_dataset import BacktestDatasetError, collect_dataset


class BacktestBatchError(RuntimeError):
    pass


async def collect_batch(manifest: dict[str, object], *, base_dir: Path) -> dict[str, object]:
    items = manifest.get("items")
    if not isinstance(items, list) or not items:
        raise BacktestBatchError("batch manifest requires items")
    profile = str(manifest.get("profile") or "").strip() or None
    session_ready = False
    results: list[dict[str, object]] = []
    for raw in items:
        if not isinstance(raw, dict):
            results.append({"status": "failed", "error": "INVALID_ITEM"})
            continue
        output = base_dir / str(raw.get("output") or "")
        if _valid_existing_dataset(output, raw):
            results.append({"symbol": raw.get("symbol"), "status": "skipped", "output": str(output)})
            continue
        try:
            if not session_ready:
                await kiwoom_session_manager.create_session_from_cli_profile(profile)
                session_ready = True
            dataset = await collect_dataset(
                profile=profile,
                symbol=str(raw.get("symbol") or ""),
                exchange=str(raw.get("exchange") or "ND"),
                start_date=str(raw.get("startDate") or manifest.get("startDate") or ""),
                tick_scope=str(raw.get("tickScope") or manifest.get("tickScope") or "1"),
                fx_csv=(base_dir / str(manifest["fxCsv"])) if manifest.get("fxCsv") else None,
                max_pages=int(raw.get("maxPages") or manifest.get("maxPages") or 20),
                create_session=False,
            )
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(dataset, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
            results.append({
                "symbol": dataset["symbol"],
                "status": "collected",
                "output": str(output),
                "candles": dataset["coverage"]["candleCount"],
                "continuationComplete": dataset["continuationComplete"],
            })
        except (BacktestDatasetError, KiwoomSessionError, OSError, ValueError) as exc:
            results.append({
                "symbol": raw.get("symbol"),
                "status": "failed",
                "error": type(exc).__name__,
            })
    return {
        "schemaVersion": 1,
        "batchType": "kiwoom-us-readonly-backtest-collection",
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "total": len(results),
        "collected": sum(item["status"] == "collected" for item in results),
        "skipped": sum(item["status"] == "skipped" for item in results),
        "failed": sum(item["status"] == "failed" for item in results),
        "items": results,
    }


def _valid_existing_dataset(path: Path, item: dict[str, object]) -> bool:
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        isinstance(payload, dict)
        and payload.get("datasetType") == "kiwoom-us-minute-chart-with-fx"
        and payload.get("symbol") == str(item.get("symbol") or "").upper()
        and isinstance(payload.get("candles"), list)
        and bool(payload["candles"])
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Resume-safe multi-symbol Kiwoom read-only backtest collection")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise BacktestBatchError("batch manifest root must be an object")
        report = asyncio.run(collect_batch(manifest, base_dir=args.manifest.parent))
    except (OSError, json.JSONDecodeError, BacktestBatchError) as exc:
        parser.error(str(exc))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"BACKTEST_BATCH_DONE=true collected={report['collected']} skipped={report['skipped']} failed={report['failed']}")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
