from __future__ import annotations

import argparse
import csv
from datetime import datetime
from io import StringIO
from pathlib import Path
import ssl
import urllib.error
import urllib.parse
import urllib.request

import certifi


FRED_SERIES_ID = "DEXKOUS"
FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


class FredFxError(RuntimeError):
    pass


def download_dexkous_csv(from_date: str, to_date: str, *, opener=None) -> str:
    start = _iso_date(from_date)
    end = _iso_date(to_date)
    if start > end:
        raise FredFxError("from date must not be after to date")
    query = urllib.parse.urlencode({"id": FRED_SERIES_ID, "cosd": start, "coed": end})
    request = urllib.request.Request(
        f"{FRED_CSV_URL}?{query}",
        headers={"User-Agent": "strategy-pilot-readonly-fx/1.0"},
        method="GET",
    )
    fetch = opener or _urlopen
    try:
        with fetch(request, 20.0) as response:
            body = response.read().decode("utf-8-sig")
    except (urllib.error.URLError, TimeoutError, UnicodeDecodeError) as exc:
        raise FredFxError(f"FRED download failed: {type(exc).__name__}") from exc
    rows = parse_dexkous_csv(body)
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=["date", "krwPerUsd"])
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def parse_dexkous_csv(body: str) -> list[dict[str, str]]:
    reader = csv.DictReader(StringIO(body))
    if reader.fieldnames is None:
        raise FredFxError("FRED CSV has no header")
    date_key = "observation_date" if "observation_date" in reader.fieldnames else "DATE"
    if date_key not in reader.fieldnames or FRED_SERIES_ID not in reader.fieldnames:
        raise FredFxError("FRED CSV contract mismatch")
    rows: list[dict[str, str]] = []
    for row in reader:
        raw_rate = str(row.get(FRED_SERIES_ID) or "").strip()
        if raw_rate in {"", "."}:
            continue
        try:
            rate = float(raw_rate)
        except ValueError as exc:
            raise FredFxError("FRED CSV contains an invalid rate") from exc
        if rate <= 0:
            raise FredFxError("FRED CSV contains a non-positive rate")
        day = _iso_date(str(row.get(date_key) or ""))
        rows.append({"date": day.replace("-", ""), "krwPerUsd": f"{rate:.6f}"})
    if not rows:
        raise FredFxError("FRED CSV contains no usable observations")
    return rows


def _urlopen(request: urllib.request.Request, timeout: float):
    context = ssl.create_default_context(cafile=certifi.where())
    return urllib.request.urlopen(request, timeout=timeout, context=context)


def _iso_date(value: str) -> str:
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError as exc:
        raise FredFxError("date must be YYYY-MM-DD") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Download official FRED DEXKOUS daily KRW/USD CSV")
    parser.add_argument("--from-date", required=True)
    parser.add_argument("--to-date", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        csv_text = download_dexkous_csv(args.from_date, args.to_date)
    except FredFxError as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(csv_text, encoding="utf-8")
    row_count = max(0, len(csv_text.splitlines()) - 1)
    print(f"FRED_DEXKOUS_READY=true rows={row_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
