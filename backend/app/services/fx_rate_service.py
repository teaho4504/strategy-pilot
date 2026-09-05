from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
import os
from pathlib import Path


@dataclass(frozen=True)
class FxRateSnapshot:
    krw_per_usd: float
    as_of: str | None
    source: str
    stale_days: int | None


def latest_usd_krw(*, today: date | None = None) -> FxRateSnapshot:
    current = today or date.today()
    candidates = _candidate_paths()
    latest: tuple[date, float] | None = None
    selected: Path | None = None
    for path in candidates:
        for observed, value in _read_rates(path):
            if observed > current or (latest is not None and observed <= latest[0]):
                continue
            latest, selected = (observed, value), path
    if latest is None:
        return FxRateSnapshot(krw_per_usd=1_350.0, as_of=None, source="fallback-reference", stale_days=None)
    observed, value = latest
    return FxRateSnapshot(
        krw_per_usd=value,
        as_of=observed.isoformat(),
        source=f"fred-dexkous:{selected.name if selected else 'cache'}",
        stale_days=max(0, (current - observed).days),
    )


def _candidate_paths() -> list[Path]:
    configured = os.getenv("KIWOOM_US_FX_CSV", "").strip()
    paths = [Path(configured)] if configured else []
    paths.extend(sorted(Path(".run").glob("fred_dexkous*.csv")))
    return [path for path in paths if path.is_file()]


def _read_rates(path: Path) -> list[tuple[date, float]]:
    rows: list[tuple[date, float]] = []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.reader(handle):
                if len(row) < 2:
                    continue
                try:
                    observed = datetime.strptime(row[0].strip().replace("-", ""), "%Y%m%d").date()
                    value = float(row[1].strip())
                except (TypeError, ValueError):
                    continue
                if 100 <= value <= 10_000:
                    rows.append((observed, value))
    except OSError:
        return []
    return rows
