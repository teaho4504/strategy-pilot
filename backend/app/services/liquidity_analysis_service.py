from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
import math
import sqlite3
from typing import Any

from trading_engine.config import get_engine_settings
from trading_engine.services.market_time import market_time_context
from app.services.fx_rate_service import latest_usd_krw

DEFAULT_WALL_THRESHOLD_KRW = 10_000_000
DEFAULT_USD_KRW = 1_350.0
MAX_ORDERBOOK_SNAPSHOTS = 120
MAX_TICK_EVENTS = 20_000
SIGNAL_HISTORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS liquidity_signal_observations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol TEXT NOT NULL,
  action TEXT NOT NULL,
  source_event_at TEXT,
  reasons_json TEXT NOT NULL DEFAULT '[]',
  execution_authorized INTEGER NOT NULL DEFAULT 0 CHECK (execution_authorized = 0),
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_liquidity_signal_symbol_created
ON liquidity_signal_observations(symbol, created_at DESC);
"""


def build_liquidity_analysis(symbol: str, *, threshold_krw: int = DEFAULT_WALL_THRESHOLD_KRW,
                             fx_krw_per_usd: float | None = None,
                             snapshot_limit: int = 48,
                             timeframe_context: list[dict[str, object]] | None = None,
                             chart_context: dict[str, object] | None = None,
                             monitor_context: dict[str, object] | None = None,
                             observation_now: datetime | None = None) -> dict[str, object]:
    clean_symbol = _safe_symbol(symbol)
    if not clean_symbol:
        raise ValueError("US symbol is required")
    threshold = min(max(int(threshold_krw), 1_000_000), 1_000_000_000)
    fx_snapshot = latest_usd_krw() if fx_krw_per_usd is None else None
    fx = min(max(float(fx_krw_per_usd if fx_krw_per_usd is not None else fx_snapshot.krw_per_usd), 100.0), 10_000.0)
    limit = min(max(int(snapshot_limit), 12), MAX_ORDERBOOK_SNAPSHOTS)
    orderbooks, ticks = _load_events(clean_symbol, limit=limit)
    timeline, latest = _build_wall_timeline(orderbooks, ticks, threshold, fx)
    derived_timeframes = [_timeframe_analysis(ticks, seconds=60, label="1m"),
                          _timeframe_analysis(ticks, seconds=300, label="5m"),
                          _timeframe_analysis(ticks, seconds=3_600, label="1h")]
    official_by_label = {str(item.get("timeframe")): item for item in (timeframe_context or [])}
    timeframes = [official_by_label.get(str(item["timeframe"]), item) for item in derived_timeframes]
    effective_chart_context = chart_context or {"source": "persisted-fe-fallback", "availableTimeframes": []}
    observation_quality = _observation_quality(
        orderbooks, ticks, timeframes, effective_chart_context, monitor_context or {},
        now=observation_now,
    )
    signal = _advisory_signal(timeframes, latest, observation_quality, now=observation_now)
    signal_history = _record_signal_observation(
        clean_symbol, signal, str(timeline[-1]["timestamp"]) if timeline else None,
    )
    return {
        "source": "kiwoom-us-fe-ft-persisted-readonly", "symbol": clean_symbol,
        "thresholdKrw": threshold, "fxKrwPerUsd": fx,
        "fxSource": fx_snapshot.source if fx_snapshot else "request-reference",
        "fxAsOf": fx_snapshot.as_of if fx_snapshot else None,
        "fxStaleDays": fx_snapshot.stale_days if fx_snapshot else None,
        "streamOwner": "fastapi-shared-kiwoom-websocket", "channels": ["FE", "FT"],
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "orderbookSnapshotCount": len(orderbooks), "tickEventCount": len(ticks),
        "latest": latest, "timeline": timeline, "timeframes": timeframes,
        "chartContext": effective_chart_context, "observationQuality": observation_quality,
        "signal": signal, "signalHistory": signal_history, "executionAuthorized": False,
        "limitations": [
            "호가는 가격대별 집계값이며 주문자나 개별 주문 ID를 식별하지 않습니다.",
            "호가 소멸은 체결 또는 취소일 수 있어 동일 주체의 이탈로 확정할 수 없습니다.",
            "환율은 요청 시 전달된 참고값이며 실시간 체결 환율이 아닙니다.",
        ],
    }


def _load_events(symbol: str, *, limit: int) -> tuple[list[sqlite3.Row], list[sqlite3.Row]]:
    path = get_engine_settings().db_path
    if not path.exists():
        return [], []
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='realtime_quote_events'").fetchone()
        if exists is None:
            return [], []
        orderbooks = connection.execute(
            "SELECT levels_json, received_at FROM realtime_quote_events WHERE symbol = ? AND event_type = 'ORDERBOOK' ORDER BY received_at DESC LIMIT ?",
            (symbol, limit)).fetchall()
        ticks = connection.execute(
            "SELECT price, volume, trade_strength, received_at FROM realtime_quote_events WHERE symbol = ? AND event_type = 'TICK' AND price IS NOT NULL ORDER BY received_at DESC LIMIT ?",
            (symbol, MAX_TICK_EVENTS)).fetchall()
    return list(reversed(orderbooks)), list(reversed(ticks))


def _build_wall_timeline(rows: list[sqlite3.Row], ticks: list[sqlite3.Row], threshold_krw: int,
                         fx_krw_per_usd: float) -> tuple[list[dict[str, object]], dict[str, object]]:
    timeline: list[dict[str, object]] = []
    previous: dict[tuple[str, float], dict[str, object]] = {}
    previous_at: datetime | None = None
    for row in rows:
        current_at = _timestamp(str(row["received_at"] or ""))
        current: dict[tuple[str, float], dict[str, object]] = {}
        try:
            levels = json.loads(str(row["levels_json"] or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            levels = []
        for level in levels if isinstance(levels, list) else []:
            if not isinstance(level, dict):
                continue
            for side, price_key, size_key in (("bid", "bid", "bidSize"), ("ask", "ask", "askSize")):
                price, quantity = _positive_float(level.get(price_key)), _positive_int(level.get(size_key))
                notional = price * quantity * fx_krw_per_usd
                if price <= 0 or quantity <= 0 or notional < threshold_krw:
                    continue
                key = (side, round(price, 6))
                prior = previous.get(key)
                current[key] = {"side": side, "level": _positive_int(level.get("level")), "price": price,
                                "quantity": quantity, "notionalKrw": round(notional),
                                "state": _wall_state(quantity, int(prior["quantity"])) if prior else "appeared",
                                "exitInference": None}
        disappeared = [
            {**wall, "quantity": 0, "notionalKrw": 0, "state": "disappeared",
             "exitInference": _infer_exit(wall, previous_at, current_at, ticks)}
            for key, wall in previous.items() if key not in current
        ]
        walls = sorted([*current.values(), *disappeared], key=lambda item: (str(item["side"]), -float(item["price"])))
        timeline.append({"timestamp": str(row["received_at"]), "walls": walls})
        previous = current
        previous_at = current_at
    latest_bid = sum(float(item["notionalKrw"]) for (side, _), item in previous.items() if side == "bid")
    latest_ask = sum(float(item["notionalKrw"]) for (side, _), item in previous.items() if side == "ask")
    total = latest_bid + latest_ask
    imbalance = ((latest_bid - latest_ask) / total * 100) if total > 0 else None
    latest = {"bidWallKrw": round(latest_bid), "askWallKrw": round(latest_ask),
              "imbalancePct": round(imbalance, 2) if imbalance is not None else None,
              "dominantSide": "bid" if latest_bid > latest_ask else "ask" if latest_ask > latest_bid else "balanced",
              "wallCount": len(previous)}
    return timeline, latest


def _wall_state(quantity: int, previous_quantity: int) -> str:
    ratio = quantity / previous_quantity if previous_quantity > 0 else 99
    return "appeared" if previous_quantity <= 0 else "growing" if ratio >= 1.1 else "shrinking" if ratio <= 0.9 else "stable"


def _infer_exit(wall: dict[str, object], start: datetime | None, end: datetime | None,
                ticks: list[sqlite3.Row]) -> str:
    if start is None or end is None:
        return "unknown"
    wall_price = float(wall["price"])
    tolerance = max(0.01, wall_price * 0.0002)
    observed: list[sqlite3.Row] = []
    matched: list[sqlite3.Row] = []
    for tick in ticks:
        at = _timestamp(str(tick["received_at"] or ""))
        if at is None or at < start or at > end:
            continue
        observed.append(tick)
        if abs(_positive_float(tick["price"]) - wall_price) <= tolerance:
            matched.append(tick)
    if len(matched) >= 2:
        volumes = [_positive_int(tick["volume"]) for tick in matched if tick["volume"] is not None]
        if len(volumes) >= 2 and volumes[-1] > volumes[0]:
            return "likely-execution"
    if matched:
        return "possible-execution"
    if observed:
        return "likely-cancel"
    return "unknown"


def _timeframe_analysis(rows: list[sqlite3.Row], *, seconds: int, label: str) -> dict[str, object]:
    buckets: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        timestamp = _timestamp(str(row["received_at"] or ""))
        if timestamp is not None:
            buckets[math.floor(timestamp.timestamp() / seconds) * seconds].append(row)
    candles: list[dict[str, object]] = []
    for bucket, events in sorted(buckets.items()):
        prices = [price for price in (_positive_float(event["price"]) for event in events) if price > 0]
        if not prices:
            continue
        volumes = [_positive_int(event["volume"]) for event in events if event["volume"] is not None]
        candles.append({"timestamp": datetime.fromtimestamp(bucket, tz=timezone.utc).isoformat(),
                        "open": prices[0], "high": max(prices), "low": min(prices), "close": prices[-1],
                        "volumeDelta": max(0, volumes[-1] - volumes[0]) if len(volumes) >= 2 else 0})
    closes = [float(candle["close"]) for candle in candles]
    ema9, ema20 = _ema_last(closes, 9), _ema_last(closes, 20)
    latest = closes[-1] if closes else None
    change_pct = ((closes[-1] / closes[-2]) - 1) * 100 if len(closes) >= 2 and closes[-2] else None
    enough, trend, pullback = len(candles) >= 3, "unavailable", False
    if enough and ema9 is not None and ema20 is not None and latest is not None:
        trend = "bullish" if ema9 > ema20 else "bearish" if ema9 < ema20 else "flat"
        pullback = trend == "bullish" and latest <= ema9 and latest >= ema20 * 0.995
    return {"timeframe": label, "seconds": seconds, "candleCount": len(candles), "latestClose": latest,
            "ema9": ema9, "ema20": ema20, "changePct": round(change_pct, 3) if change_pct is not None else None,
            "trend": trend, "pullback": pullback, "dataSufficient": enough, "candles": candles[-24:]}


def _advisory_signal(timeframes: list[dict[str, object]], latest: dict[str, object],
                     observation_quality: dict[str, object], *,
                     now: datetime | None = None) -> dict[str, object]:
    available = [item for item in timeframes if item["dataSufficient"]]
    bullish = sum(item["trend"] == "bullish" for item in available)
    bearish = sum(item["trend"] == "bearish" for item in available)
    pullbacks = [str(item["timeframe"]) for item in available if item["pullback"]]
    imbalance_value = float(latest.get("imbalancePct") or 0)
    action, reasons = "WATCH", []
    if bullish >= 2 and imbalance_value >= 10:
        action, reasons = "BUY_WATCH", ["2개 이상 시간대 상승 흐름과 매수 호가벽 우위"]
    elif bearish >= 2 and imbalance_value <= -10:
        action, reasons = "SELL_WATCH", ["2개 이상 시간대 하락 흐름과 매도 호가벽 우위"]
    else:
        reasons.append("시간대 정렬 또는 호가 불균형 확인 대기")
    if pullbacks:
        reasons.append(f"눌림 후보 시간대: {', '.join(pullbacks)}")
    if not available:
        reasons.append("저장된 체결 데이터가 부족함")
    if not bool(observation_quality["signalEligible"]):
        if action != "WATCH":
            action = "WATCH"
        reasons.append(f"데이터 품질 게이트: {observation_quality['state']}")
    expires_at = None
    if action in {"BUY_WATCH", "SELL_WATCH"}:
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        expires_at = (current + timedelta(seconds=10)).isoformat()
    return {"action": action, "confidence": "observation-only", "reasons": reasons,
            "executionAuthorized": False, "expiresAt": expires_at}


def _observation_quality(orderbooks: list[sqlite3.Row], ticks: list[sqlite3.Row],
                         timeframes: list[dict[str, object]], chart_context: dict[str, object],
                         monitor: dict[str, object], *,
                         now: datetime | None = None) -> dict[str, object]:
    context = market_time_context(now)
    timestamps = [
        _timestamp(str(row["received_at"] or ""))
        for row in [*(orderbooks[-1:] or []), *(ticks[-1:] or [])]
    ]
    valid_timestamps = [value.astimezone(timezone.utc) for value in timestamps if value is not None]
    latest_event = max(valid_timestamps) if valid_timestamps else None
    age_seconds = (context.utc - latest_event).total_seconds() if latest_event else None
    fresh = age_seconds is not None and 0 <= age_seconds <= 10
    available = {str(value) for value in chart_context.get("availableTimeframes", [])}
    missing_timeframes = [value for value in ("1m", "5m", "1h") if value not in available]
    chart_ages: dict[str, float | None] = {}
    stale_timeframes: list[str] = []
    for item in timeframes:
        label = str(item.get("timeframe") or "")
        if label not in {"1m", "5m", "1h"} or label not in available:
            continue
        candle_at = _timestamp(str(item.get("latestCandleAtUtc") or ""))
        age = (context.utc - candle_at.astimezone(timezone.utc)).total_seconds() if candle_at else None
        chart_ages[label] = round(age, 3) if age is not None else None
        max_age = max(180, int(item.get("seconds") or 60) * 2 + 60)
        if age is None or age < -int(item.get("seconds") or 60) or age > max_age:
            stale_timeframes.append(label)
    running, connected = bool(monitor.get("running")), bool(monitor.get("connected"))
    session = context.us_session.value
    reasons: list[str] = []
    if session == "closed":
        state = "off_hours"
        reasons.append("미국장 관찰 시간 외 또는 주말")
    elif not running:
        state = "missing"
        reasons.append("키움 FE/FT 모니터가 실행 중이 아님")
    elif not connected:
        state = "reconnecting"
        reasons.append("키움 FE/FT 모니터 재연결 대기")
    elif latest_event is None:
        state = "missing"
        reasons.append("수신된 FE/FT 이벤트가 없음")
    elif not fresh:
        state = "stale"
        reasons.append("최근 FE/FT 이벤트가 10초 기준을 초과")
    elif missing_timeframes:
        state = "degraded"
        reasons.append("필수 공식 분봉 일부 누락")
    elif stale_timeframes:
        state = "degraded"
        reasons.append("필수 공식 분봉 최신성 기준 미충족")
    else:
        state = "ready"
    if missing_timeframes:
        reasons.append(f"누락 시간대: {', '.join(missing_timeframes)}")
    if stale_timeframes and session != "closed":
        reasons.append(f"오래된 시간대: {', '.join(stale_timeframes)}")
    eligible = state == "ready"
    return {
        "state": state, "signalEligible": eligible, "marketSession": session,
        "marketDate": context.us_market_date, "marketTimeZone": "America/New_York",
        "calendarMode": "weekday-session-approximation", "monitorRunning": running,
        "monitorConnected": connected,
        "latestEventAt": latest_event.isoformat() if latest_event else None,
        "eventAgeSeconds": round(age_seconds, 3) if age_seconds is not None else None,
        "maxEventAgeSeconds": 10, "requiredTimeframes": ["1m", "5m", "1h"],
        "availableTimeframes": sorted(available), "missingTimeframes": missing_timeframes,
        "chartAgeSeconds": chart_ages, "staleTimeframes": stale_timeframes,
        "reasons": reasons,
    }


def _record_signal_observation(symbol: str, signal: dict[str, object],
                               source_event_at: str | None) -> list[dict[str, object]]:
    path = get_engine_settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        connection.executescript(SIGNAL_HISTORY_SCHEMA)
        latest = connection.execute(
            "SELECT action FROM liquidity_signal_observations WHERE symbol = ? ORDER BY id DESC LIMIT 1",
            (symbol,),
        ).fetchone()
        action = str(signal["action"])
        if latest is None or str(latest["action"]) != action:
            connection.execute(
                "INSERT INTO liquidity_signal_observations(symbol, action, source_event_at, reasons_json, execution_authorized, created_at) VALUES (?, ?, ?, ?, 0, ?)",
                (symbol, action, source_event_at, json.dumps(signal["reasons"], ensure_ascii=False), created_at),
            )
            connection.commit()
        rows = connection.execute(
            "SELECT action, source_event_at, reasons_json, execution_authorized, created_at FROM liquidity_signal_observations WHERE symbol = ? ORDER BY id DESC LIMIT 20",
            (symbol,),
        ).fetchall()
    return [{"action": str(row["action"]), "sourceEventAt": row["source_event_at"],
             "reasons": json.loads(str(row["reasons_json"] or "[]")),
             "executionAuthorized": bool(row["execution_authorized"]), "createdAt": str(row["created_at"])}
            for row in rows]


def _ema_last(values: list[float], period: int) -> float | None:
    if not values:
        return None
    multiplier, result = 2 / (period + 1), values[0]
    for value in values[1:]:
        result = value * multiplier + result * (1 - multiplier)
    return round(result, 6)


def _timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _safe_symbol(value: object) -> str:
    cleaned = "".join(ch for ch in str(value or "").upper().strip() if ch.isalnum() or ch in {".", "-"})[:16]
    return cleaned if any(ch.isalnum() for ch in cleaned) else ""


def _positive_float(value: Any) -> float:
    try:
        return abs(float(str(value).replace(",", "").replace("+", "").strip()))
    except (TypeError, ValueError):
        return 0.0


def _positive_int(value: Any) -> int:
    try:
        return abs(int(float(str(value).replace(",", "").replace("+", "").strip())))
    except (TypeError, ValueError):
        return 0
