from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
from typing import Any

from trading_engine.config import get_engine_settings


REALTIME_EVENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS realtime_quote_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type TEXT NOT NULL,
  symbol TEXT NOT NULL,
  provider TEXT NOT NULL,
  price REAL,
  change_rate REAL,
  volume INTEGER,
  trade_strength REAL,
  bid REAL,
  ask REAL,
  bid_size INTEGER,
  ask_size INTEGER,
  levels_json TEXT NOT NULL DEFAULT '[]',
  source_event_time TEXT,
  received_at TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_realtime_quote_events_symbol_received
ON realtime_quote_events(symbol, received_at);
"""


@dataclass(frozen=True)
class RealtimeDbWindowMetrics:
    symbol: str
    events10s: int = 0
    events1m: int = 0
    events5m: int = 0
    volume10sDelta: int | None = None
    volume1mDelta: int | None = None
    volume5mDelta: int | None = None
    tradeStrength1mChange: float | None = None
    spreadPctLatest: float | None = None
    lastReceivedAt: str | None = None


def record_realtime_event(event: dict[str, object]) -> None:
    event_type = _safe_text(event.get("type"))
    symbol = _safe_symbol(event.get("symbol"))
    if event_type not in {"TICK", "ORDERBOOK"} or not symbol:
        return
    db_path = _db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.executescript(REALTIME_EVENTS_SCHEMA)
        connection.execute(
            """
            INSERT INTO realtime_quote_events(
              event_type, symbol, provider, price, change_rate, volume,
              trade_strength, bid, ask, bid_size, ask_size, levels_json,
              source_event_time, received_at, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_type,
                symbol,
                _safe_text(event.get("provider")) or "unknown",
                _optional_float(event.get("price")),
                _optional_float(event.get("changeRate")),
                _optional_int(event.get("volume")),
                _optional_float(event.get("tradeStrength")),
                _optional_float(event.get("bid")),
                _optional_float(event.get("ask")),
                _optional_int(event.get("bidSize")),
                _optional_int(event.get("askSize")),
                _safe_levels_json(event.get("levels")),
                _safe_text(event.get("sourceEventTime")) or None,
                _safe_text(event.get("receivedAt")) or _safe_text(event.get("timestamp")) or _now_iso(),
                _now_iso(),
            ),
        )
        connection.commit()


def realtime_event_counts(symbols: list[str]) -> dict[str, int]:
    db_path = _db_path()
    if not db_path.exists():
        return {symbol.upper(): 0 for symbol in symbols}
    cleaned = [_safe_symbol(symbol) for symbol in symbols if _safe_symbol(symbol)]
    if not cleaned:
        return {}
    placeholders = ",".join("?" for _ in cleaned)
    with sqlite3.connect(db_path) as connection:
        connection.executescript(REALTIME_EVENTS_SCHEMA)
        rows = connection.execute(
            f"""
            SELECT symbol, COUNT(*) AS count
            FROM realtime_quote_events
            WHERE symbol IN ({placeholders})
            GROUP BY symbol
            """,
            cleaned,
        ).fetchall()
    counts = {symbol: 0 for symbol in cleaned}
    counts.update({str(row[0]): int(row[1]) for row in rows})
    return counts


def realtime_db_window_metrics(symbols: list[str], now: datetime | None = None) -> dict[str, RealtimeDbWindowMetrics]:
    db_path = _db_path()
    cleaned = [_safe_symbol(symbol) for symbol in symbols if _safe_symbol(symbol)]
    if not cleaned:
        return {}
    if not db_path.exists():
        return {symbol: RealtimeDbWindowMetrics(symbol=symbol) for symbol in cleaned}

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    cutoff_5m = current.timestamp() - 300
    placeholders = ",".join("?" for _ in cleaned)
    with sqlite3.connect(db_path) as connection:
        connection.executescript(REALTIME_EVENTS_SCHEMA)
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            f"""
            SELECT symbol, event_type, volume, trade_strength, bid, ask, received_at
            FROM realtime_quote_events
            WHERE symbol IN ({placeholders})
            ORDER BY received_at ASC
            """,
            cleaned,
        ).fetchall()

    grouped: dict[str, list[sqlite3.Row]] = {symbol: [] for symbol in cleaned}
    for row in rows:
        received_ts = _parse_timestamp(row["received_at"])
        if received_ts is None or received_ts < cutoff_5m:
            continue
        grouped.setdefault(str(row["symbol"]), []).append(row)

    return {symbol: _build_metrics(symbol, symbol_rows, current) for symbol, symbol_rows in grouped.items()}


def _build_metrics(symbol: str, rows: list[sqlite3.Row], now: datetime) -> RealtimeDbWindowMetrics:
    now_ts = now.timestamp()
    rows10s = _rows_since(rows, now_ts - 10)
    rows1m = _rows_since(rows, now_ts - 60)
    rows5m = _rows_since(rows, now_ts - 300)
    spread = _latest_spread_pct(rows5m)
    return RealtimeDbWindowMetrics(
        symbol=symbol,
        events10s=len(rows10s),
        events1m=len(rows1m),
        events5m=len(rows5m),
        volume10sDelta=_volume_delta(rows10s),
        volume1mDelta=_volume_delta(rows1m),
        volume5mDelta=_volume_delta(rows5m),
        tradeStrength1mChange=_trade_strength_change(rows1m),
        spreadPctLatest=spread,
        lastReceivedAt=str(rows5m[-1]["received_at"]) if rows5m else None,
    )


def _rows_since(rows: list[sqlite3.Row], cutoff_ts: float) -> list[sqlite3.Row]:
    filtered: list[sqlite3.Row] = []
    for row in rows:
        received_ts = _parse_timestamp(row["received_at"])
        if received_ts is not None and received_ts >= cutoff_ts:
            filtered.append(row)
    return filtered


def _volume_delta(rows: list[sqlite3.Row]) -> int | None:
    volumes = [int(row["volume"]) for row in rows if row["event_type"] == "TICK" and row["volume"] is not None]
    if len(volumes) < 2:
        return None
    return max(0, volumes[-1] - volumes[0])


def _trade_strength_change(rows: list[sqlite3.Row]) -> float | None:
    values = [float(row["trade_strength"]) for row in rows if row["event_type"] == "TICK" and row["trade_strength"] is not None]
    if len(values) < 2:
        return None
    return values[-1] - values[0]


def _latest_spread_pct(rows: list[sqlite3.Row]) -> float | None:
    for row in reversed(rows):
        bid = row["bid"]
        ask = row["ask"]
        if bid is None or ask is None:
            continue
        bid_value = float(bid)
        ask_value = float(ask)
        mid = (bid_value + ask_value) / 2
        if mid <= 0:
            continue
        return ((ask_value - bid_value) / mid) * 100
    return None


def _parse_timestamp(value: object) -> float | None:
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except (TypeError, ValueError):
        return None


def _db_path() -> Path:
    return get_engine_settings().db_path


def _safe_symbol(value: object) -> str:
    return "".join(ch for ch in str(value or "").upper().strip() if ch.isalnum() or ch in {".", "-"})[:16]


def _safe_text(value: object) -> str:
    return str(value).strip() if value not in (None, "") else ""


def _optional_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "").replace("%", "").replace("+", "").strip())
    except (TypeError, ValueError):
        return None


def _optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).replace(",", "").replace("+", "").strip()))
    except (TypeError, ValueError):
        return None


def _safe_levels_json(value: object) -> str:
    if not isinstance(value, list):
        return "[]"
    safe_levels: list[dict[str, object]] = []
    for raw in value[:10]:
        if not isinstance(raw, dict):
            continue
        safe_levels.append(
            {
                "level": _optional_int(raw.get("level")) or 0,
                "bid": _optional_float(raw.get("bid")) or 0,
                "ask": _optional_float(raw.get("ask")) or 0,
                "bidSize": _optional_int(raw.get("bidSize")) or 0,
                "askSize": _optional_int(raw.get("askSize")) or 0,
            }
        )
    return json.dumps(safe_levels, ensure_ascii=False)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
