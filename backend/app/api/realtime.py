from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.kiwoom_session import kiwoom_session_manager
from app.services.liquidity_analysis_service import build_liquidity_analysis
from app.services.official_chart_context_service import official_chart_context_service
from app.services.realtime_quote_service import (
    kiwoom_quote_monitor,
    realtime_window_store,
    safe_quote_symbols,
)
from app.services.us_condition_service import us_condition_service


router = APIRouter()


@router.websocket("/realtime/rankings/ws")
async def realtime_rankings_websocket(websocket: WebSocket) -> None:
    """Push one shared FE/FT monitor snapshot to dashboard clients every two seconds."""
    await websocket.accept()
    try:
        first_message = await asyncio.wait_for(websocket.receive_json(), timeout=10)
    except Exception:
        await websocket.send_json({"type": "ERROR", "errorType": "AUTH_REQUIRED"})
        await websocket.close(code=1008)
        return

    token = _safe_string(first_message.get("token"))
    if first_message.get("type") != "AUTH" or not token:
        await websocket.send_json({"type": "ERROR", "errorType": "AUTH_REQUIRED"})
        await websocket.close(code=1008)
        return

    session = kiwoom_session_manager.get_session(token)
    if session is None:
        await websocket.send_json({"type": "ERROR", "errorType": "AUTH_EXPIRED"})
        await websocket.close(code=1008)
        return

    requested = _safe_symbol_items(first_message.get("symbols"))
    if not requested:
        await websocket.send_json({"type": "ERROR", "errorType": "SYMBOLS_REQUIRED"})
        await websocket.close(code=1008)
        return

    symbols = safe_quote_symbols([item["symbol"] for item in requested])
    exchanges = {item["symbol"]: item["exchange"] for item in requested}
    await kiwoom_quote_monitor.ensure_union(session, symbols, exchanges)
    await websocket.send_json(
        {
            "type": "STATUS",
            "status": "AUTHENTICATED",
            "symbols": symbols,
            "intervalMs": 2000,
            "channels": ["FE", "FT"],
            "readOnly": True,
            "orderEnabled": False,
        }
    )

    try:
        while True:
            monitor = kiwoom_quote_monitor.status()
            await websocket.send_json(
                {
                    "type": "RANKING_SNAPSHOT",
                    "intervalMs": 2000,
                    "monitorConnected": bool(monitor.get("connected")),
                    "monitoredSymbols": monitor.get("symbols", []),
                    "lastError": monitor.get("lastError"),
                    "items": [item.to_dict() for item in realtime_window_store.summaries(symbols)],
                }
            )
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        return
    except Exception:
        try:
            await websocket.send_json({"type": "ERROR", "errorType": "RANKING_STREAM_UNAVAILABLE"})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except RuntimeError:
            pass


@router.websocket("/realtime/quotes/ws")
async def realtime_quotes_websocket(websocket: WebSocket) -> None:
    """Push snapshots from the shared FE/FT monitor without opening another broker session."""
    await websocket.accept()
    try:
        first_message = await asyncio.wait_for(websocket.receive_json(), timeout=10)
    except Exception:
        await websocket.send_json({"type": "ERROR", "errorType": "AUTH_REQUIRED"})
        await websocket.close(code=1008)
        return

    token = _safe_string(first_message.get("token"))
    if first_message.get("type") != "AUTH" or not token:
        await websocket.send_json({"type": "ERROR", "errorType": "AUTH_REQUIRED"})
        await websocket.close(code=1008)
        return

    session = kiwoom_session_manager.get_session(token)
    if session is None:
        await websocket.send_json({"type": "ERROR", "errorType": "AUTH_EXPIRED"})
        await websocket.close(code=1008)
        return

    if first_message.get("provider") not in (None, "kiwoom"):
        await websocket.send_json({"type": "ERROR", "errorType": "LIVE_PROVIDER_REQUIRED"})
        await websocket.close(code=1008)
        return
    provider = "kiwoom"
    symbols = safe_quote_symbols(_safe_symbol_list(first_message.get("symbols")))
    exchanges = _safe_exchange_map(first_message.get("exchanges"), symbols)
    await kiwoom_quote_monitor.ensure_union(session, symbols, exchanges)
    await websocket.send_json(
        {
            "type": "STATUS",
            "status": "AUTHENTICATED",
            "provider": provider,
            "symbols": symbols,
            "intervalMs": 2000,
            "channels": ["FE", "FT"],
            "readOnly": True,
            "orderEnabled": False,
        }
    )

    try:
        while True:
            monitor = kiwoom_quote_monitor.status()
            await websocket.send_json(
                {
                    "type": "QUOTE_SNAPSHOT",
                    "intervalMs": 2000,
                    "monitorConnected": bool(monitor.get("connected")),
                    "monitoredSymbols": monitor.get("symbols", []),
                    "lastError": monitor.get("lastError"),
                    "items": [item.to_dict() for item in realtime_window_store.summaries(symbols)],
                }
            )
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        return
    except Exception:
        try:
            await websocket.send_json({"type": "ERROR", "errorType": "QUOTE_STREAM_UNAVAILABLE"})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except RuntimeError:
            pass


@router.websocket("/realtime/us/conditions/ws")
async def realtime_us_conditions_websocket(websocket: WebSocket) -> None:
    """Push shared condition-monitor snapshots without creating a per-browser Kiwoom socket."""
    await websocket.accept()
    try:
        first_message = await asyncio.wait_for(websocket.receive_json(), timeout=10)
    except Exception:
        await websocket.send_json({"type": "ERROR", "errorType": "AUTH_REQUIRED"})
        await websocket.close(code=1008)
        return

    token = _safe_string(first_message.get("token"))
    if first_message.get("type") != "AUTH" or not token:
        await websocket.send_json({"type": "ERROR", "errorType": "AUTH_REQUIRED"})
        await websocket.close(code=1008)
        return

    session = kiwoom_session_manager.get_session(token)
    if session is None:
        await websocket.send_json({"type": "ERROR", "errorType": "AUTH_EXPIRED"})
        await websocket.close(code=1008)
        return

    if first_message.get("provider") not in (None, "kiwoom"):
        await websocket.send_json({"type": "ERROR", "errorType": "LIVE_PROVIDER_REQUIRED"})
        await websocket.close(code=1008)
        return
    provider = "kiwoom"
    seqs = _safe_condition_seqs(first_message.get("seqs"))
    legacy_seq = _safe_string(first_message.get("seq"))
    if legacy_seq and legacy_seq not in seqs:
        seqs.insert(0, legacy_seq)
    seqs = seqs[:10]
    await websocket.send_json(
        {
            "type": "CONDITION_STATUS",
            "status": "AUTHENTICATED",
            "provider": provider,
            "seqs": seqs,
            "intervalMs": 2000,
            "readOnly": True,
            "orderEnabled": False,
        }
    )

    ensure_tasks = [
        asyncio.create_task(us_condition_service.ensure_realtime_monitor(session, seq))
        for seq in seqs
    ]
    try:
        while True:
            items = []
            for seq in seqs:
                status = us_condition_service.monitor_status(seq)
                items.append(
                    {
                        "seq": seq,
                        "selectedSeq": status.get("selectedSeq"),
                        "selectedName": status.get("selectedName"),
                        "connected": bool(status.get("active")),
                        "registered": bool(status.get("registered")),
                        "matchCount": int(status.get("matchCount") or 0),
                        "matches": [
                            match.model_dump()
                            for match in us_condition_service.monitor_matches(seq)
                        ],
                        "error": status.get("error"),
                        "errorType": status.get("errorType"),
                        "lastConnectedAt": status.get("lastConnectedAt"),
                        "lastReceivedAt": status.get("lastReceivedAt"),
                        "reconnectCount": int(status.get("reconnectCount") or 0),
                        "nextRetrySeconds": status.get("nextRetrySeconds"),
                    }
                )
            await websocket.send_json(
                {
                    "type": "CONDITION_SNAPSHOT",
                    "intervalMs": 2000,
                    "items": items,
                }
            )
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        return
    except Exception:
        try:
            await websocket.send_json({"type": "ERROR", "errorType": "CONDITION_STREAM_UNAVAILABLE"})
        except Exception:
            pass
    finally:
        for task in ensure_tasks:
            if not task.done():
                task.cancel()
        try:
            await websocket.close()
        except RuntimeError:
            pass


@router.websocket("/realtime/us/liquidity/ws")
async def realtime_us_liquidity_websocket(websocket: WebSocket) -> None:
    """Push persisted FE/FT analysis; never open a browser-owned broker socket."""
    await websocket.accept()
    try:
        first_message = await asyncio.wait_for(websocket.receive_json(), timeout=10)
    except Exception:
        await websocket.send_json({"type": "ERROR", "errorType": "AUTH_REQUIRED"})
        await websocket.close(code=1008)
        return
    token = _safe_string(first_message.get("token"))
    if first_message.get("type") != "AUTH" or not token:
        await websocket.send_json({"type": "ERROR", "errorType": "AUTH_REQUIRED"})
        await websocket.close(code=1008)
        return
    session = kiwoom_session_manager.get_session(token)
    if session is None:
        await websocket.send_json({"type": "ERROR", "errorType": "AUTH_EXPIRED"})
        await websocket.close(code=1008)
        return
    symbols = safe_quote_symbols([_safe_string(first_message.get("symbol"))])
    if not symbols:
        await websocket.send_json({"type": "ERROR", "errorType": "SYMBOL_REQUIRED"})
        await websocket.close(code=1008)
        return
    symbol = symbols[0]
    exchange = _safe_string(first_message.get("exchange")).upper()
    if exchange not in {"ND", "NY", "NA"}:
        exchange = "ND"
    threshold = _safe_int_range(first_message.get("thresholdKrw"), 10_000_000, 1_000_000, 1_000_000_000)
    raw_fx = first_message.get("fxKrwPerUsd")
    fx = None if raw_fx in (None, "") else _safe_float_range(raw_fx, 1_350.0, 100.0, 10_000.0)
    await kiwoom_quote_monitor.ensure_union(session, [symbol], {symbol: exchange})
    await websocket.send_json({
        "type": "LIQUIDITY_STATUS", "status": "AUTHENTICATED", "symbol": symbol,
        "intervalMs": 2_000, "channels": ["FE", "FT"], "streamOwner": "fastapi",
        "readOnly": True, "orderEnabled": False, "executionAuthorized": False,
    })
    try:
        while True:
            official_timeframes, chart_context = await official_chart_context_service.get(symbol, exchange)
            monitor = kiwoom_quote_monitor.status()
            analysis = build_liquidity_analysis(
                symbol, threshold_krw=threshold, fx_krw_per_usd=fx,
                timeframe_context=official_timeframes, chart_context=chart_context,
                monitor_context=monitor,
            )
            analysis["monitor"] = monitor
            await websocket.send_json({"type": "LIQUIDITY_SNAPSHOT", "analysis": analysis})
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        return
    except Exception:
        try:
            await websocket.send_json({"type": "ERROR", "errorType": "LIQUIDITY_STREAM_UNAVAILABLE"})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except RuntimeError:
            pass
def _safe_string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _safe_symbol_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _safe_exchange_map(value: Any, symbols: list[str]) -> dict[str, str]:
    if not isinstance(value, dict):
        return {symbol: "ND" for symbol in symbols}
    return {
        symbol: exchange if exchange in {"ND", "NY", "NA"} else "ND"
        for symbol in symbols
        for exchange in [_safe_string(value.get(symbol)).upper()]
    }


def _safe_condition_seqs(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        seq = _safe_string(item)
        if not seq or len(seq) > 32 or seq in result:
            continue
        result.append(seq)
        if len(result) >= 10:
            break
    return result


def _safe_symbol_items(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        symbol = _safe_string(item.get("symbol")).upper()
        exchange = _safe_string(item.get("exchange")).upper()
        if not symbol or symbol in seen:
            continue
        if exchange not in {"ND", "NY", "NA"}:
            exchange = "ND"
        seen.add(symbol)
        result.append({"symbol": symbol, "exchange": exchange})
        if len(result) >= 20:
            break
    return result


def _safe_int_range(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, minimum), maximum)


def _safe_float_range(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, minimum), maximum)
