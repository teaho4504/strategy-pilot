from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import require_authenticated_user
from app.schemas.market import (
    MarketRankingResponse,
    UsQuoteResponse,
    UsAutoTradePlanListResponse,
    UsAutoTradePlanResponse,
    UsConditionSearchResponse,
    UsChartResponse,
    UsRealtimeWindowItem,
    UsRealtimeWindowResponse,
)
from app.services.market_ranking_service import MarketRankingError, market_ranking_service
from app.services.liquidity_analysis_service import build_liquidity_analysis
from app.services.official_chart_context_service import official_chart_context_service
from app.core.time import now_iso
from app.services.realtime_event_store import realtime_db_window_metrics, realtime_event_counts
from app.services.realtime_quote_service import kiwoom_quote_monitor, realtime_window_store, safe_quote_symbols
from app.services.kiwoom_session import get_active_or_latest_kiwoom_session
from app.services.us_condition_service import UsConditionSearchError, us_condition_service
from app.services.us_account_service import US_READONLY_SERVICE_ERRORS, us_account_service
from trading_engine.services.market_time import market_time_context


router = APIRouter(dependencies=[Depends(require_authenticated_user)])


@router.get("/market/rankings/us/{ranking_type}", response_model=MarketRankingResponse)
async def get_us_ranking(ranking_type: str) -> MarketRankingResponse:
    try:
        return await market_ranking_service.get_us_ranking(ranking_type)
    except MarketRankingError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/market/us/order-candidates", response_model=MarketRankingResponse)
async def get_us_order_candidates(maxNotional: float = 500.0, limit: int = 8) -> MarketRankingResponse:
    try:
        return await market_ranking_service.get_us_order_candidates(max_notional=maxNotional, limit=limit)
    except MarketRankingError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/market/us/auto-trade-plan/pullback-rank3", response_model=UsAutoTradePlanResponse)
async def get_us_pullback_rank3_plan() -> UsAutoTradePlanResponse:
    try:
        return await market_ranking_service.get_us_pullback_auto_trade_plan()
    except MarketRankingError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/market/us/auto-trade-plans/pullback", response_model=UsAutoTradePlanListResponse)
async def get_us_pullback_strategy_plans() -> UsAutoTradePlanListResponse:
    try:
        return await market_ranking_service.get_us_pullback_auto_trade_plans()
    except MarketRankingError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/market/us/conditions", response_model=UsConditionSearchResponse)
async def get_us_conditions(seq: str | None = None) -> UsConditionSearchResponse:
    try:
        if seq is None:
            return await us_condition_service.get_condition_list()
        return await us_condition_service.get_condition_search(seq=seq)
    except UsConditionSearchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/market/us/realtime-window", response_model=UsRealtimeWindowResponse)
async def get_us_realtime_window(symbols: str | None = None, exchanges: str | None = None) -> UsRealtimeWindowResponse:
    requested_symbols = safe_quote_symbols(symbols.split(",")) if symbols else None
    if requested_symbols:
        session = get_active_or_latest_kiwoom_session()
        if session is not None:
            await kiwoom_quote_monitor.ensure_union(
                session,
                requested_symbols,
                _safe_exchange_map(exchanges),
            )
    monitor = kiwoom_quote_monitor.status()
    monitored_symbols = list(monitor["symbols"])
    expected_symbols = requested_symbols if requested_symbols is not None else monitored_symbols
    summaries = realtime_window_store.summaries(expected_symbols or None)
    counts = realtime_event_counts([item.symbol for item in summaries])
    db_metrics = realtime_db_window_metrics([item.symbol for item in summaries])
    quality = _realtime_quality(
        summaries,
        expected_symbols,
        monitor_running=bool(monitor["running"]),
        monitor_connected=bool(monitor["connected"]),
    )
    return UsRealtimeWindowResponse(
        source="kiwoom-us-fe-ft-window",
        channels=["FE", "FT"],
        updatedAt=now_iso(),
        monitorRunning=bool(monitor["running"]),
        monitorConnected=bool(monitor["connected"]),
        monitoredSymbols=monitored_symbols,
        monitorLastError=str(monitor["lastError"]) if monitor["lastError"] else None,
        monitorLastConnectedAt=str(monitor["lastConnectedAt"]) if monitor["lastConnectedAt"] else None,
        monitorLastHeartbeatAt=str(monitor["lastHeartbeatAt"]) if monitor["lastHeartbeatAt"] else None,
        monitorReconnectCount=int(monitor["reconnectCount"]),
        monitorNextRetrySeconds=int(monitor["nextRetrySeconds"]) if monitor["nextRetrySeconds"] is not None else None,
        marketSession=market_time_context().us_session.value,
        **quality,
        items=[
            UsRealtimeWindowItem(
                **{
                    **item.to_dict(),
                    "persistedEventCount": counts.get(item.symbol, 0),
                    "dbEvents10s": db_metrics.get(item.symbol).events10s if db_metrics.get(item.symbol) else 0,
                    "dbEvents1m": db_metrics.get(item.symbol).events1m if db_metrics.get(item.symbol) else 0,
                    "dbEvents5m": db_metrics.get(item.symbol).events5m if db_metrics.get(item.symbol) else 0,
                    "dbVolume10sDelta": db_metrics.get(item.symbol).volume10sDelta if db_metrics.get(item.symbol) else None,
                    "dbVolume1mDelta": db_metrics.get(item.symbol).volume1mDelta if db_metrics.get(item.symbol) else None,
                    "dbVolume5mDelta": db_metrics.get(item.symbol).volume5mDelta if db_metrics.get(item.symbol) else None,
                    "dbTradeStrength1mChange": db_metrics.get(item.symbol).tradeStrength1mChange if db_metrics.get(item.symbol) else None,
                    "dbSpreadPct": db_metrics.get(item.symbol).spreadPctLatest if db_metrics.get(item.symbol) else None,
                }
            )
            for item in summaries
        ],
    )


@router.get("/market/us/liquidity-analysis")
async def get_us_liquidity_analysis(
    symbol: str = "NVDA",
    exchange: str = "ND",
    thresholdKrw: int = 10_000_000,
    fxKrwPerUsd: float | None = None,
    snapshotLimit: int = 48,
) -> dict[str, object]:
    """Analyze persisted FE/FT data while FastAPI remains the sole stream owner."""
    clean_symbol = safe_quote_symbols([symbol])
    if not clean_symbol:
        raise HTTPException(status_code=400, detail="US symbol is required")
    clean_exchange = exchange.upper().strip() if exchange.upper().strip() in {"ND", "NY", "NA"} else "ND"
    session = get_active_or_latest_kiwoom_session()
    if session is not None:
        await kiwoom_quote_monitor.ensure_union(session, clean_symbol, {clean_symbol[0]: clean_exchange})
    official_timeframes, chart_context = await official_chart_context_service.get(clean_symbol[0], clean_exchange)
    monitor = kiwoom_quote_monitor.status()
    result = build_liquidity_analysis(
        clean_symbol[0], threshold_krw=thresholdKrw,
        fx_krw_per_usd=fxKrwPerUsd, snapshot_limit=snapshotLimit,
        timeframe_context=official_timeframes, chart_context=chart_context,
        monitor_context=monitor,
    )
    result["monitor"] = monitor
    return result


@router.get("/market/us/quote", response_model=UsQuoteResponse)
async def get_us_quote(symbol: str, exchange: str = "ND") -> UsQuoteResponse:
    clean_symbol = "".join(ch for ch in symbol.upper().strip() if ch.isalnum() or ch in {".", "-"})[:12]
    clean_exchange = exchange.upper().strip() if exchange.upper().strip() in {"ND", "NY", "NA"} else "ND"
    if not clean_symbol:
        raise HTTPException(status_code=400, detail="US quote symbol is required")
    try:
        summary = await us_account_service.get_current_quote(clean_exchange, clean_symbol)
    except US_READONLY_SERVICE_ERRORS as exc:
        raise HTTPException(status_code=502, detail="US quote lookup failed") from exc
    row = _first_result_row(summary.data)
    data = {**summary.data, **row}
    return UsQuoteResponse(
        symbol=clean_symbol,
        exchange=clean_exchange,
        name=_safe_text(data.get("stk_nm") or data.get("stk_enm")),
        price=_safe_number(data.get("cur_prc") or data.get("curr_pric") or data.get("last_prc") or data.get("close_pric"), absolute=True),
        changeRate=_safe_number(data.get("flu_rt") or data.get("diff_rate_for_gjga")),
        volume=_safe_integer(data.get("acc_trde_qty") or data.get("trde_qty")),
        updatedAt=summary.updatedAt,
    )


def _first_result_row(data: dict[str, object]) -> dict[str, object]:
    raw = data.get("result_list") or data.get("result_lsit")
    if not isinstance(raw, list):
        return {}
    return next((item for item in raw if isinstance(item, dict)), {})


def _safe_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _safe_number(value: object, *, absolute: bool = False) -> float | None:
    try:
        parsed = float(str(value).replace(",", "").replace("%", "").replace("+", "").strip())
    except (TypeError, ValueError):
        return None
    return abs(parsed) if absolute else parsed


def _safe_integer(value: object) -> int | None:
    parsed = _safe_number(value, absolute=True)
    return int(parsed) if parsed is not None else None


def _safe_exchange_map(value: str | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in str(value or "").split(","):
        symbol, separator, exchange = item.partition(":")
        clean_symbol = symbol.upper().strip()
        clean_exchange = exchange.upper().strip()
        symbol_valid = 0 < len(clean_symbol) <= 12 and all(
            ch.isalnum() or ch in {".", "-"} for ch in clean_symbol
        )
        if separator and symbol_valid and clean_exchange in {"ND", "NY", "NA"}:
            result[clean_symbol] = clean_exchange
    return result


def _realtime_quality(
    summaries,
    expected_symbols: list[str],
    *,
    monitor_running: bool = False,
    monitor_connected: bool = False,
) -> dict[str, object]:
    expected = len(expected_symbols)
    if expected == 0:
        return {
            "qualityState": "idle",
            "expectedSymbolCount": 0,
            "freshSymbolCount": 0,
            "staleSymbolCount": 0,
            "missingSymbolCount": 0,
            "delayedSymbolCount": 0,
            "coveragePct": 0,
            "averageReceiveDelayMs": None,
            "maxReceiveDelayMs": None,
        }
    by_symbol = {item.symbol: item for item in summaries}
    fresh = 0
    stale = 0
    missing = 0
    delays: list[int] = []
    delayed = 0
    now = market_time_context().utc
    for symbol in expected_symbols:
        item = by_symbol.get(symbol)
        if item is None or item.lastEventAt is None:
            missing += 1
            continue
        try:
            event_time = datetime.fromisoformat(item.lastEventAt.replace("Z", "+00:00"))
            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=timezone.utc)
            age_seconds = (now - event_time.astimezone(timezone.utc)).total_seconds()
        except ValueError:
            missing += 1
            continue
        if 0 <= age_seconds <= 10:
            fresh += 1
        else:
            stale += 1
        if item.receiveDelayMs is not None:
            delay = max(0, int(item.receiveDelayMs))
            delays.append(delay)
            if delay > 2_000:
                delayed += 1
    coverage = round((fresh / expected) * 100, 1)
    state = "healthy" if fresh == expected and delayed == 0 else "degraded" if fresh > 0 else "stale"
    # A recently cached event can remain fresh while the FE/FT monitor is
    # reconnecting. Keep the freshness counters, but never report the live
    # stream itself as healthy until the monitor is connected again.
    if state == "healthy" and monitor_running and not monitor_connected:
        state = "degraded"
    return {
        "qualityState": state,
        "expectedSymbolCount": expected,
        "freshSymbolCount": fresh,
        "staleSymbolCount": stale,
        "missingSymbolCount": missing,
        "delayedSymbolCount": delayed,
        "coveragePct": coverage,
        "averageReceiveDelayMs": round(sum(delays) / len(delays)) if delays else None,
        "maxReceiveDelayMs": max(delays) if delays else None,
    }


@router.get("/market/us/chart/{timeframe}", response_model=UsChartResponse)
async def get_us_chart(
    timeframe: str,
    symbol: str,
    exchange: str = "ND",
    startDate: str | None = None,
    tickScope: str = "1",
) -> UsChartResponse:
    try:
        return await market_ranking_service.get_us_chart(
            timeframe=timeframe,
            symbol=symbol,
            exchange=exchange,
            start_date=startDate,
            tick_scope=tickScope,
        )
    except MarketRankingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="US chart lookup failed") from exc
