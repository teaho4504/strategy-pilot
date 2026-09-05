from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import ssl
from typing import Any, Literal
from zoneinfo import ZoneInfo

from app.services.realtime_event_store import record_realtime_event
from app.services.kiwoom_session import KiwoomSession
from app.services.kiwoom_websocket import kiwoom_websocket_ssl_context
from trading_engine.providers.kiwoom_us.request_builder import build_realtime_registration
from trading_engine.providers.kiwoom_us.schemas import UsRealtimeSymbol


QuoteProvider = Literal["kiwoom"]

DEFAULT_QUOTE_SYMBOLS = ["NVDA", "TSLA", "AAPL", "MSFT", "AMD"]
MAX_SYMBOLS = 20
KIWOOM_US_WEBSOCKET_URL = "wss://api.kiwoom.com:10000/api/us/websocket"
READONLY_REALTIME_TYPES = {"FE", "FT"}
QUOTE_RECONNECT_BASE_SECONDS = 1
QUOTE_RECONNECT_MAX_SECONDS = 30
QUOTE_MAX_AGE_SECONDS = 10
US_MARKET_TIMEZONE = ZoneInfo("America/New_York")


class RealtimeQuoteError(RuntimeError):
    pass


@dataclass(frozen=True)
class RealtimeQuoteTick:
    symbol: str
    name: str
    price: int
    change_rate: float
    volume: int
    rank: int
    provider: QuoteProvider
    timestamp: str

    def to_event(self) -> dict[str, object]:
        return {
            "type": "TICK",
            "symbol": self.symbol,
            "name": self.name,
            "price": self.price,
            "changeRate": self.change_rate,
            "volume": self.volume,
            "rank": self.rank,
            "provider": self.provider,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class RealtimeWindowSummary:
    symbol: str
    tickCount: int
    orderbookCount: int
    latestPrice: float | None
    latestChangeRate: float | None
    latestVolume: int | None
    volume10sDelta: int | None
    volume10sIncreasing: bool | None
    tradeStrength: float | None
    tradeStrengthIncreasing: bool | None
    bid: float | None
    ask: float | None
    spreadPct: float | None
    spreadWithin01Pct: bool | None
    lastEventAt: str | None
    sourceEventTime: str | None
    receiveDelayMs: int | None

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "tickCount": self.tickCount,
            "orderbookCount": self.orderbookCount,
            "latestPrice": self.latestPrice,
            "latestChangeRate": self.latestChangeRate,
            "latestVolume": self.latestVolume,
            "volume10sDelta": self.volume10sDelta,
            "volume10sIncreasing": self.volume10sIncreasing,
            "tradeStrength": self.tradeStrength,
            "tradeStrengthIncreasing": self.tradeStrengthIncreasing,
            "bid": self.bid,
            "ask": self.ask,
            "spreadPct": self.spreadPct,
            "spreadWithin01Pct": self.spreadWithin01Pct,
            "lastEventAt": self.lastEventAt,
            "sourceEventTime": self.sourceEventTime,
            "receiveDelayMs": self.receiveDelayMs,
        }


class RealtimeWindowStore:
    def __init__(self, max_events: int = 240) -> None:
        self._ticks: dict[str, deque[dict[str, object]]] = {}
        self._orderbooks: dict[str, deque[dict[str, object]]] = {}
        self._max_events = max_events

    def clear(self) -> None:
        self._ticks.clear()
        self._orderbooks.clear()

    def record(self, event: dict[str, object]) -> None:
        symbol = str(event.get("symbol") or "").upper().strip()
        event_type = str(event.get("type") or "")
        if not symbol:
            return
        row = dict(event)
        row["symbol"] = symbol
        row.setdefault("receivedAt", datetime.now(timezone.utc).isoformat())
        if event_type == "TICK":
            self._ticks.setdefault(symbol, deque(maxlen=self._max_events)).append(row)
        elif event_type == "ORDERBOOK":
            self._orderbooks.setdefault(symbol, deque(maxlen=self._max_events)).append(row)
        try:
            record_realtime_event(row)
        except Exception:
            pass

    def summary(self, symbol: str) -> RealtimeWindowSummary:
        clean_symbol = symbol.upper().strip()
        ticks = list(self._ticks.get(clean_symbol, ()))
        orderbooks = list(self._orderbooks.get(clean_symbol, ()))
        latest_tick = ticks[-1] if ticks else {}
        latest_book = orderbooks[-1] if orderbooks else {}
        latest_price = _optional_float(latest_tick.get("price"))
        latest_change_rate = _optional_float(latest_tick.get("changeRate"))
        latest_volume = _optional_int(latest_tick.get("volume"))
        volume_delta = _volume_delta(ticks, seconds=10)
        trade_strength = _optional_float(latest_tick.get("tradeStrength"))
        trade_strength_increasing = _trade_strength_increasing(ticks)
        bid = _optional_float(latest_book.get("bid"))
        ask = _optional_float(latest_book.get("ask"))
        spread_pct = _spread_pct(bid, ask)
        last_event = _latest_event(ticks, orderbooks)
        source_event_time = str(last_event.get("sourceEventTime") or "") or None
        return RealtimeWindowSummary(
            symbol=clean_symbol,
            tickCount=len(ticks),
            orderbookCount=len(orderbooks),
            latestPrice=latest_price,
            latestChangeRate=latest_change_rate,
            latestVolume=latest_volume,
            volume10sDelta=volume_delta,
            volume10sIncreasing=volume_delta is not None and volume_delta > 0,
            tradeStrength=trade_strength,
            tradeStrengthIncreasing=trade_strength_increasing,
            bid=bid,
            ask=ask,
            spreadPct=spread_pct,
            spreadWithin01Pct=spread_pct is not None and spread_pct <= 0.1,
            lastEventAt=str(last_event.get("receivedAt") or last_event.get("timestamp") or "") or None,
            sourceEventTime=source_event_time,
            receiveDelayMs=_receive_delay_ms(last_event),
        )

    def summaries(self, symbols: list[str] | None = None) -> list[RealtimeWindowSummary]:
        if symbols:
            keys = safe_quote_symbols(symbols)
        else:
            keys = sorted(set(self._ticks.keys()) | set(self._orderbooks.keys()))
        return [self.summary(symbol) for symbol in keys]


realtime_window_store = RealtimeWindowStore()


class KiwoomQuoteMonitor:
    def __init__(self, *, sleep=asyncio.sleep) -> None:
        self._sleep = sleep
        self._task: asyncio.Task[None] | None = None
        self._session_token: str | None = None
        self._symbols: tuple[str, ...] = ()
        self._exchanges: dict[str, str] = {}
        self._last_error: str | None = None
        self._connected = False
        self._last_connected_at: str | None = None
        self._last_heartbeat_at: str | None = None
        self._reconnect_count = 0
        self._next_retry_seconds: int | None = None

    async def ensure(
        self,
        session: KiwoomSession,
        symbols: list[str],
        exchanges: dict[str, str] | None = None,
    ) -> None:
        requested = tuple(safe_quote_symbols(symbols))
        requested_exchanges = {
            symbol: _safe_exchange((exchanges or {}).get(symbol))
            for symbol in requested
        }
        if (
            self._task is not None
            and not self._task.done()
            and self._session_token == session.session_token
            and self._symbols == requested
            and self._exchanges == requested_exchanges
        ):
            return
        await self.stop()
        self._session_token = session.session_token
        self._symbols = requested
        self._exchanges = requested_exchanges
        self._last_error = None
        self._connected = False
        self._last_connected_at = None
        self._last_heartbeat_at = None
        self._reconnect_count = 0
        self._next_retry_seconds = None
        self._task = asyncio.create_task(
            self._run(session, list(requested), requested_exchanges),
            name="strategy-pilot-kiwoom-fe-ft-monitor",
        )

    async def ensure_union(
        self,
        session: KiwoomSession,
        symbols: list[str],
        exchanges: dict[str, str] | None = None,
        *,
        prefer_existing: bool = False,
    ) -> None:
        requested = safe_quote_symbols(symbols)
        current = list(self._symbols)
        merged = [*current, *requested] if prefer_existing else [*requested, *current]
        merged = safe_quote_symbols(merged)
        merged_exchanges = dict(self._exchanges)
        for symbol in requested:
            merged_exchanges[symbol] = _safe_exchange((exchanges or {}).get(symbol))
        await self.ensure(session, merged, merged_exchanges)

    async def stop(self) -> None:
        task = self._task
        self._task = None
        self._session_token = None
        self._symbols = ()
        self._exchanges = {}
        self._connected = False
        self._next_retry_seconds = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    def status(self) -> dict[str, object]:
        return {
            "running": self._task is not None and not self._task.done(),
            "symbols": list(self._symbols),
            "exchanges": dict(self._exchanges),
            "channels": ["FE", "FT"],
            "connected": self._connected,
            "lastConnectedAt": self._last_connected_at,
            "lastHeartbeatAt": self._last_heartbeat_at,
            "reconnectCount": self._reconnect_count,
            "nextRetrySeconds": self._next_retry_seconds,
            "lastError": self._last_error,
        }

    async def _run(self, session: KiwoomSession, symbols: list[str], exchanges: dict[str, str]) -> None:
        consecutive_failures = 0
        while True:
            try:
                async for event in kiwoom_quote_stream(session, symbols, exchanges=exchanges):
                    event_type = event.get("type")
                    event_time = str(event.get("timestamp") or datetime.now(timezone.utc).isoformat())
                    if event_type == "STATUS":
                        status = str(event.get("status") or "")
                        if status == "CONNECTED":
                            if not self._connected:
                                self._last_connected_at = event_time
                            self._connected = True
                            self._last_heartbeat_at = event_time
                            self._last_error = None
                            self._next_retry_seconds = None
                            consecutive_failures = 0
                        elif status == "HEARTBEAT":
                            self._connected = True
                            self._last_heartbeat_at = event_time
                        continue
                    if event_type == "ERROR":
                        self._connected = False
                        self._last_error = str(event.get("errorType") or "QUOTE_STREAM_ERROR")
                    elif event_type in {"TICK", "ORDERBOOK"}:
                        if not self._connected:
                            self._last_connected_at = event_time
                        self._connected = True
                        self._last_heartbeat_at = event_time
                        self._last_error = None
                        consecutive_failures = 0
                self._connected = False
                if self._last_error is None:
                    self._last_error = "QUOTE_STREAM_ENDED"
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._connected = False
                self._last_error = exc.__class__.__name__
            delay = quote_reconnect_delay(consecutive_failures)
            consecutive_failures += 1
            self._reconnect_count += 1
            self._next_retry_seconds = delay
            await self._sleep(delay)
            self._next_retry_seconds = None


class SharedKiwoomQuoteMonitor:
    """Facade over the single Kiwoom US realtime session shared with condition search."""

    async def ensure(
        self,
        session: KiwoomSession,
        symbols: list[str],
        exchanges: dict[str, str] | None = None,
    ) -> None:
        from app.services.us_condition_service import us_condition_service

        await us_condition_service.ensure_quote_monitor(session, symbols, exchanges)

    async def ensure_union(
        self,
        session: KiwoomSession,
        symbols: list[str],
        exchanges: dict[str, str] | None = None,
        *,
        prefer_existing: bool = False,
    ) -> None:
        from app.services.us_condition_service import us_condition_service

        await us_condition_service.ensure_quote_union(
            session,
            symbols,
            exchanges,
            prefer_existing=prefer_existing,
        )

    async def stop(self) -> None:
        from app.services.us_condition_service import us_condition_service

        await us_condition_service.stop_quote_monitor()

    def status(self) -> dict[str, object]:
        from app.services.us_condition_service import us_condition_service

        return us_condition_service.quote_monitor_status()


kiwoom_quote_monitor = SharedKiwoomQuoteMonitor()


def safe_quote_symbols(symbols: list[str] | None) -> list[str]:
    cleaned: list[str] = []
    for value in symbols or DEFAULT_QUOTE_SYMBOLS:
        symbol = "".join(ch for ch in str(value).upper().strip() if ch.isalnum() or ch in {".", "-"})
        if not symbol or len(symbol) > 12:
            continue
        if symbol not in cleaned:
            cleaned.append(symbol)
        if len(cleaned) >= MAX_SYMBOLS:
            break
    return cleaned or DEFAULT_QUOTE_SYMBOLS


def build_kiwoom_login_packet(access_token: str) -> dict[str, str]:
    if not access_token:
        raise RealtimeQuoteError("Kiwoom access token is required")
    return {"trnm": "LOGIN", "token": access_token}


def build_kiwoom_quote_reg_packet(
    symbols: list[str],
    exchange: str = "ND",
    channels: list[str] | None = None,
    exchanges: dict[str, str] | None = None,
) -> dict[str, Any]:
    channel_list = channels or ["FE", "FT"]
    assert_readonly_realtime_types(channel_list)
    realtime_symbols = [
        UsRealtimeSymbol(symbol, _safe_exchange((exchanges or {}).get(symbol) or exchange))
        for symbol in safe_quote_symbols(symbols)
    ]
    if not channel_list:
        raise RealtimeQuoteError("US realtime channel is required")
    packet = build_realtime_registration(channel_list[0], realtime_symbols).to_packet()
    packet["data"][0]["type"] = channel_list
    return packet


def assert_readonly_realtime_types(types: list[str]) -> None:
    blocked = [value for value in types if value not in READONLY_REALTIME_TYPES]
    if blocked:
        raise RealtimeQuoteError("Unsupported realtime type for read-only quote stream")


def normalize_kiwoom_realtime_message(message: dict[str, Any]) -> list[dict[str, object]]:
    if message.get("trnm") in {"LOGIN", "PING"}:
        return []

    data = message.get("data")
    if not isinstance(data, list):
        return [
            {
                "type": "SCHEMA",
                "provider": "kiwoom",
                "trnm": str(message.get("trnm") or ""),
                "schemaKeys": sorted(str(key) for key in message.keys()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ]

    events: list[dict[str, object]] = []
    for index, row in enumerate(data, start=1):
        if not isinstance(row, dict):
            continue
        item = row.get("item")
        if isinstance(item, dict):
            symbol = str(item.get("jmcode") or item.get("stk_cd") or item.get("symbol") or "")
        else:
            symbol = str(item or row.get("code") or row.get("symbol") or row.get("stk_cd") or row.get("jmcode") or "")
        values = row.get("values") if isinstance(row.get("values"), dict) else row
        price = _safe_price(values.get("10") or values.get("price") or values.get("cur_prc"))
        change_rate = _safe_float(values.get("12") or values.get("changeRate") or values.get("flu_rt"))
        volume = _safe_int(values.get("13") or values.get("volume") or values.get("trde_qty"))
        if not symbol:
            continue
        name = str(row.get("name") or row.get("stk_nm") or row.get("symbol_name") or symbol)
        timestamp = datetime.now(timezone.utc).isoformat()
        source_event_time = _source_event_time(values)
        if price:
            events.append(
                {
                    "type": "TICK",
                    "symbol": symbol,
                    "name": name,
                    "price": price,
                    "changeRate": change_rate,
                    "volume": volume,
                    "rank": index,
                    "provider": "kiwoom",
                    "timestamp": timestamp,
                    "receivedAt": timestamp,
                    "sourceEventTime": source_event_time,
                    "tradeStrength": _safe_float(values.get("228") or values.get("tradeStrength") or values.get("cntr_str")),
                }
            )
        bid = _safe_price(values.get("51") or values.get("27") or values.get("bid") or values.get("bid_prc") or values.get("best_bid"))
        ask = _safe_price(values.get("41") or values.get("28") or values.get("ask") or values.get("ask_prc") or values.get("best_ask"))
        if bid or ask:
            levels = _orderbook_levels(values)
            events.append(
                {
                    "type": "ORDERBOOK",
                    "symbol": symbol,
                    "name": name,
                    "bid": bid,
                    "ask": ask,
                    "bidSize": _safe_int(values.get("61") or values.get("29") or values.get("bid_size")),
                    "askSize": _safe_int(values.get("71") or values.get("30") or values.get("ask_size")),
                    "levels": levels,
                    "provider": "kiwoom",
                    "timestamp": timestamp,
                    "receivedAt": timestamp,
                    "sourceEventTime": source_event_time,
                }
            )
    return events


async def kiwoom_quote_stream(
    session: KiwoomSession,
    symbols: list[str],
    exchanges: dict[str, str] | None = None,
) -> AsyncIterator[dict[str, object]]:
    import websockets

    url = KIWOOM_US_WEBSOCKET_URL
    yield {
        "type": "STATUS",
        "provider": "kiwoom",
        "status": "CONNECTING",
        "symbols": safe_quote_symbols(symbols),
        "channels": ["FE", "FT"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        async with websockets.connect(url, ping_interval=None, open_timeout=10, close_timeout=3, ssl=kiwoom_websocket_ssl_context()) as websocket:
            await websocket.send(json.dumps(build_kiwoom_login_packet(session.access_token)))
            login_raw = await asyncio.wait_for(websocket.recv(), timeout=10)
            login_response = json.loads(login_raw)
            if (
                login_response.get("trnm") != "LOGIN"
                or login_response.get("return_code") not in (0, "0")
            ):
                yield {
                    "type": "ERROR",
                    "provider": "kiwoom",
                    "errorType": "KIWOOM_WEBSOCKET_LOGIN_FAILED",
                    "returnCode": str(login_response.get("return_code")),
                    "returnMessage": str(login_response.get("return_msg") or ""),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                return

            await websocket.send(json.dumps(build_kiwoom_quote_reg_packet(symbols, exchanges=exchanges)))
            yield {
                "type": "STATUS",
                "provider": "kiwoom",
                "status": "CONNECTED",
                "symbols": safe_quote_symbols(symbols),
                "channels": ["FE", "FT"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            while True:
                try:
                    raw = await asyncio.wait_for(websocket.recv(), timeout=30)
                except asyncio.TimeoutError:
                    yield {
                        "type": "STATUS",
                        "provider": "kiwoom",
                        "status": "HEARTBEAT",
                        "symbols": safe_quote_symbols(symbols),
                        "channels": ["FE", "FT"],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    continue
                message = json.loads(raw)
                if message.get("trnm") == "PING":
                    await websocket.send(json.dumps(message))
                    continue
                for event in normalize_kiwoom_realtime_message(message):
                    realtime_window_store.record(event)
                    yield event
    except Exception as exc:
        yield {
            "type": "ERROR",
            "provider": "kiwoom",
            "errorType": _safe_websocket_error_type(exc),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


def _safe_websocket_error_type(exc: Exception) -> str:
    """Classify connection failures without exposing tokens or broker payloads."""
    if isinstance(exc, asyncio.TimeoutError):
        return "KIWOOM_WEBSOCKET_TIMEOUT"
    if isinstance(exc, json.JSONDecodeError):
        return "KIWOOM_WEBSOCKET_INVALID_RESPONSE"
    if isinstance(exc, ssl.SSLError):
        return "KIWOOM_WEBSOCKET_SSL_ERROR"
    if exc.__class__.__name__.startswith("ConnectionClosed"):
        return "KIWOOM_WEBSOCKET_CONNECTION_CLOSED"
    if isinstance(exc, OSError):
        return "KIWOOM_WEBSOCKET_CONNECTION_ERROR"
    return "KIWOOM_WEBSOCKET_UNAVAILABLE"


def _safe_int(value: object) -> int:
    try:
        return abs(int(float(str(value).replace(",", "").replace("+", "").strip())))
    except (TypeError, ValueError):
        return 0


def _safe_exchange(value: object) -> str:
    exchange = str(value or "").upper().strip()
    return exchange if exchange in {"ND", "NY", "NA"} else "ND"


def _safe_float(value: object) -> float:
    try:
        return float(str(value).replace(",", "").replace("%", "").replace("+", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _safe_price(value: object) -> float:
    return abs(_safe_float(value))


def _optional_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    parsed = _safe_float(value)
    return parsed if parsed != 0.0 else None


def _optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    parsed = _safe_int(value)
    return parsed if parsed != 0 else None


def _latest_event(ticks: list[dict[str, object]], orderbooks: list[dict[str, object]]) -> dict[str, object]:
    candidates = [row for row in (ticks[-1:] + orderbooks[-1:]) if row]
    if not candidates:
        return {}
    return max(candidates, key=lambda row: str(row.get("receivedAt") or row.get("timestamp") or ""))


def realtime_summary_is_fresh(
    summary: RealtimeWindowSummary,
    *,
    max_age_seconds: int = QUOTE_MAX_AGE_SECONDS,
) -> bool:
    event_time = _parse_iso(str(summary.lastEventAt or ""))
    if event_time is None:
        return False
    age_seconds = (datetime.now(timezone.utc) - event_time.astimezone(timezone.utc)).total_seconds()
    max_age = max(1, int(max_age_seconds))
    receive_delay_ms = getattr(summary, "receiveDelayMs", None)
    if receive_delay_ms is not None and receive_delay_ms > max_age * 1000:
        return False
    return 0 <= age_seconds <= max_age


def quote_reconnect_delay(failure_index: int) -> int:
    bounded_index = min(max(int(failure_index), 0), 10)
    return min(
        QUOTE_RECONNECT_BASE_SECONDS * (2**bounded_index),
        QUOTE_RECONNECT_MAX_SECONDS,
    )


def _volume_delta(ticks: list[dict[str, object]], seconds: int) -> int | None:
    if len(ticks) < 2:
        return None
    latest = ticks[-1]
    latest_time = _parse_iso(str(latest.get("receivedAt") or latest.get("timestamp") or ""))
    latest_volume = _optional_int(latest.get("volume"))
    if latest_time is None or latest_volume is None:
        return None
    baseline = ticks[0]
    for row in reversed(ticks[:-1]):
        row_time = _parse_iso(str(row.get("receivedAt") or row.get("timestamp") or ""))
        if row_time is None:
            continue
        if (latest_time - row_time).total_seconds() >= seconds:
            baseline = row
            break
    baseline_volume = _optional_int(baseline.get("volume"))
    if baseline_volume is None:
        return None
    return max(0, latest_volume - baseline_volume)


def _trade_strength_increasing(ticks: list[dict[str, object]]) -> bool | None:
    strengths = [_optional_float(row.get("tradeStrength")) for row in ticks[-6:]]
    values = [value for value in strengths if value is not None]
    if len(values) < 2:
        return None
    return values[-1] > values[0]


def _spread_pct(bid: float | None, ask: float | None) -> float | None:
    if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
        return None
    mid = (bid + ask) / 2
    if mid <= 0:
        return None
    return ((ask - bid) / mid) * 100


def _orderbook_levels(values: dict[str, Any]) -> list[dict[str, object]]:
    levels: list[dict[str, object]] = []
    for index in range(10):
        ask = _safe_price(values.get(str(41 + index)))
        bid = _safe_price(values.get(str(51 + index)))
        bid_size = _safe_int(values.get(str(61 + index)))
        ask_size = _safe_int(values.get(str(71 + index)))
        if not any((ask, bid, bid_size, ask_size)):
            continue
        levels.append(
            {
                "level": index + 1,
                "bid": bid,
                "ask": ask,
                "bidSize": bid_size,
                "askSize": ask_size,
            }
        )
    return levels


def _source_event_time(values: dict[str, Any]) -> str | None:
    raw_date = str(values.get("22") or values.get("date") or "").strip()
    raw_time = str(values.get("20") or values.get("51020") or values.get("21") or values.get("time") or "").strip()
    if raw_date and raw_time:
        return f"{raw_date}T{raw_time}"
    return raw_time or None


def _receive_delay_ms(event: dict[str, object]) -> int | None:
    source = str(event.get("sourceEventTime") or "")
    received = _parse_iso(str(event.get("receivedAt") or event.get("timestamp") or ""))
    if received is None or "T" not in source:
        return None
    raw_date, raw_time = source.split("T", 1)
    digits = "".join(ch for ch in raw_time if ch.isdigit())
    if len(raw_date) != 8 or len(digits) < 6:
        return None
    try:
        source_dt = datetime(
            int(raw_date[:4]),
            int(raw_date[4:6]),
            int(raw_date[6:8]),
            int(digits[:2]),
            int(digits[2:4]),
            int(digits[4:6]),
            tzinfo=US_MARKET_TIMEZONE,
        )
    except ValueError:
        return None
    delta = (received - source_dt).total_seconds() * 1000
    if abs(delta) > 86_400_000:
        return None
    # FE/FT may supply a six-digit clock whose seconds remain ``00``. Treat it
    # as a minute bucket and report only the minimum provable transport delay.
    if digits[4:6] == "00":
        delta = max(0, delta - 59_999)
    return int(delta)


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
