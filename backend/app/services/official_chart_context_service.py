from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from time import monotonic

from app.schemas.market import UsChartCandle
from app.services.market_ranking_service import market_ranking_service, parse_kiwoom_us_candle_time


CHART_CACHE_SECONDS = 60
TIMEFRAME_SCOPES = (("1m", "1"), ("5m", "5"), ("1h", "60"))


class OfficialChartContextService:
    def __init__(self) -> None:
        self._cache: dict[tuple[str, str], tuple[float, list[dict[str, object]], dict[str, object]]] = {}
        self._lock = asyncio.Lock()

    async def get(self, symbol: str, exchange: str) -> tuple[list[dict[str, object]], dict[str, object]]:
        key = (symbol.upper(), exchange.upper())
        cached = self._cache.get(key)
        if cached and monotonic() - cached[0] < CHART_CACHE_SECONDS:
            return cached[1], cached[2]
        async with self._lock:
            cached = self._cache.get(key)
            if cached and monotonic() - cached[0] < CHART_CACHE_SECONDS:
                return cached[1], cached[2]
            items: list[dict[str, object]] = []
            unavailable: list[str] = []
            for label, scope in TIMEFRAME_SCOPES:
                try:
                    chart = await market_ranking_service.get_us_chart(
                        timeframe="minute", symbol=key[0], exchange=key[1], tick_scope=scope,
                    )
                except Exception:
                    unavailable.append(label)
                    continue
                if not chart.candles:
                    unavailable.append(label)
                    continue
                items.append(_analyze_chart(chart.candles, label=label, scope=scope, tr_id=chart.trId))
            meta = {
                "source": "kiwoom-usa06011" if items else "persisted-fe-fallback",
                "requestedScopes": [scope for _, scope in TIMEFRAME_SCOPES],
                "availableTimeframes": [str(item["timeframe"]) for item in items],
                "unavailableTimeframes": unavailable,
                "cachedForSeconds": CHART_CACHE_SECONDS,
                "updatedAt": datetime.now(timezone.utc).isoformat(),
            }
            self._cache[key] = (monotonic(), items, meta)
            return items, meta

    def clear(self) -> None:
        self._cache.clear()


def _analyze_chart(candles: list[UsChartCandle], *, label: str, scope: str, tr_id: str) -> dict[str, object]:
    normalized = [candle for candle in candles if candle.close > 0]
    closes = [float(candle.close) for candle in normalized]
    ema9, ema20 = _ema_last(closes, 9), _ema_last(closes, 20)
    latest = closes[-1] if closes else None
    enough = len(closes) >= 3
    trend, pullback = "unavailable", False
    if enough and latest is not None and ema9 is not None and ema20 is not None:
        trend = "bullish" if ema9 > ema20 else "bearish" if ema9 < ema20 else "flat"
        pullback = trend == "bullish" and latest <= ema9 and latest >= ema20 * 0.995
    change_pct = ((closes[-1] / closes[-2]) - 1) * 100 if len(closes) >= 2 and closes[-2] else None
    latest_raw = (normalized[-1].executedAt or normalized[-1].businessDate or "") if normalized else ""
    latest_at = parse_kiwoom_us_candle_time(latest_raw)
    return {
        "timeframe": label, "seconds": int(scope) * 60, "tickScope": scope,
        "trId": tr_id, "source": f"kiwoom-{tr_id}", "candleCount": len(normalized),
        "latestClose": latest, "ema9": ema9, "ema20": ema20,
        "changePct": round(change_pct, 3) if change_pct is not None else None,
        "trend": trend, "pullback": pullback, "dataSufficient": enough,
        "latestCandleAt": latest_raw or None,
        "latestCandleAtUtc": latest_at.astimezone(timezone.utc).isoformat() if latest_at else None,
        "timestampConvention": "kiwoom-us-extended-kst-observed",
        "candles": [{"timestamp": candle.executedAt or candle.businessDate or "",
                     "open": float(candle.open), "high": float(candle.high), "low": float(candle.low),
                     "close": float(candle.close), "volumeDelta": int(candle.volume)}
                    for candle in normalized[-24:]],
    }


def _ema_last(values: list[float], period: int) -> float | None:
    if not values:
        return None
    multiplier, result = 2 / (period + 1), values[0]
    for value in values[1:]:
        result = value * multiplier + result * (1 - multiplier)
    return round(result, 6)


official_chart_context_service = OfficialChartContextService()
