from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from typing import Any

from app.services.kiwoom_session import KiwoomSession
from app.services.kiwoom_websocket import kiwoom_websocket_ssl_context
from trading_engine.providers.kiwoom_us.order_event_mapper import (
    UsBrokerOrderEvent,
    map_us_order_realtime_payload,
)
from trading_engine.risk.allocation_store import (
    AllocationCycle,
    CapitalAllocationStore,
)
from trading_engine.risk.order_recovery import apply_us_order_events


KIWOOM_US_ORDER_STATE_WEBSOCKET_URL = (
    "wss://api.kiwoom.com:10000/api/us/websocket"
)
ORDER_STATE_MONITOR_CONFIRM = "I_UNDERSTAND_F4_F5_READ_ONLY"
ORDER_STATE_CHANNELS = ("F4", "F5")
ORDER_STATE_RECONNECT_BASE_SECONDS = 1
ORDER_STATE_RECONNECT_MAX_SECONDS = 30
ReconcileCallback = Callable[[], Awaitable[object]]
SleepCallback = Callable[[float], Awaitable[None]]


class UsOrderStateMonitorError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OrderStateStreamBatch:
    connected: bool
    events: tuple[UsBrokerOrderEvent, ...]
    received_at: str


def order_state_monitor_configured() -> bool:
    return (
        _env_bool("KIWOOM_US_ORDER_STATE_MONITOR_ENABLED", False)
        and os.getenv("KIWOOM_US_ORDER_STATE_MONITOR_CONFIRM")
        == ORDER_STATE_MONITOR_CONFIRM
    )


def build_order_state_registration_packet(
    symbols: list[str],
    exchanges: dict[str, str],
) -> dict[str, Any]:
    items: list[dict[str, str]] = []
    for symbol in _safe_symbols(symbols):
        items.append(
            {
                "jmcode": symbol,
                "stex_tp": _safe_exchange(exchanges.get(symbol)),
            }
        )
    if not items:
        raise UsOrderStateMonitorError("submitted order symbol is required")
    return {
        "trnm": "REG",
        "grp_no": "91",
        "refresh": "1",
        "data": [{"item": items, "type": list(ORDER_STATE_CHANNELS)}],
    }


async def kiwoom_order_state_stream(
    session: KiwoomSession,
    symbols: list[str],
    exchanges: dict[str, str],
) -> AsyncIterator[OrderStateStreamBatch]:
    if not order_state_monitor_configured():
        raise UsOrderStateMonitorError("F4/F5 order-state monitor is disabled")
    if session.mode != "live" or session.is_expired:
        raise UsOrderStateMonitorError("a valid live Kiwoom session is required")

    import websockets

    async with websockets.connect(
        KIWOOM_US_ORDER_STATE_WEBSOCKET_URL,
        ping_interval=None,
        open_timeout=10,
        close_timeout=3,
        ssl=kiwoom_websocket_ssl_context(),
    ) as websocket:
        await websocket.send(
            json.dumps({"trnm": "LOGIN", "token": session.access_token})
        )
        login_raw = await asyncio.wait_for(websocket.recv(), timeout=10)
        login_response = json.loads(login_raw)
        if (
            login_response.get("trnm") != "LOGIN"
            or login_response.get("return_code") not in (0, "0")
        ):
            raise UsOrderStateMonitorError("Kiwoom F4/F5 login failed")

        await websocket.send(
            json.dumps(
                build_order_state_registration_packet(symbols, exchanges)
            )
        )
        yield OrderStateStreamBatch(
            connected=True,
            events=(),
            received_at=_now_iso(),
        )

        while True:
            try:
                raw = await asyncio.wait_for(websocket.recv(), timeout=30)
            except asyncio.TimeoutError:
                yield OrderStateStreamBatch(
                    connected=True,
                    events=(),
                    received_at=_now_iso(),
                )
                continue

            message = json.loads(raw)
            if message.get("trnm") == "PING":
                await websocket.send(json.dumps(message))
                continue
            if message.get("trnm") != "REAL":
                continue

            events = tuple(map_us_order_realtime_payload(message))
            if events:
                yield OrderStateStreamBatch(
                    connected=True,
                    events=events,
                    received_at=_now_iso(),
                )


class KiwoomOrderStateMonitor:
    def __init__(
        self,
        *,
        sleep: SleepCallback = asyncio.sleep,
    ) -> None:
        self._sleep = sleep
        self._task: asyncio.Task[None] | None = None
        self._session_token: str | None = None
        self._cycle_id: int | None = None
        self._symbols: tuple[str, ...] = ()
        self._exchanges: dict[str, str] = {}
        self._connected = False
        self._last_event_at: str | None = None
        self._last_error: str | None = None
        self._last_reconcile_error: str | None = None
        self._last_connected_at: str | None = None
        self._last_heartbeat_at: str | None = None
        self._reconnect_count = 0
        self._next_retry_seconds: int | None = None
        self._updated_count = 0
        self._duplicate_count = 0

    async def ensure(
        self,
        *,
        session: KiwoomSession,
        cycle: AllocationCycle,
        store: CapitalAllocationStore,
        symbols: list[str],
        exchanges: dict[str, str],
        reconcile: ReconcileCallback | None = None,
    ) -> None:
        if not order_state_monitor_configured():
            await self.stop()
            return

        safe_symbols = tuple(_safe_symbols(symbols))
        safe_exchanges = {
            symbol: _safe_exchange(exchanges.get(symbol))
            for symbol in safe_symbols
        }
        if not safe_symbols:
            await self.stop()
            return
        if (
            self._task is not None
            and not self._task.done()
            and self._session_token == session.session_token
            and self._cycle_id == cycle.id
            and self._symbols == safe_symbols
            and self._exchanges == safe_exchanges
        ):
            return

        await self.stop()
        self._session_token = session.session_token
        self._cycle_id = cycle.id
        self._symbols = safe_symbols
        self._exchanges = safe_exchanges
        self._last_error = None
        self._last_reconcile_error = None
        self._last_connected_at = None
        self._last_heartbeat_at = None
        self._reconnect_count = 0
        self._next_retry_seconds = None
        self._updated_count = 0
        self._duplicate_count = 0
        self._task = asyncio.create_task(
            self._run(
                session=session,
                cycle=cycle,
                store=store,
                symbols=list(safe_symbols),
                exchanges=safe_exchanges,
                reconcile=reconcile,
            ),
            name="strategy-pilot-kiwoom-f4-f5-monitor",
        )

    async def stop(self) -> None:
        task = self._task
        self._task = None
        self._session_token = None
        self._cycle_id = None
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
            "enabled": order_state_monitor_configured(),
            "running": self._task is not None and not self._task.done(),
            "connected": self._connected,
            "cycleId": self._cycle_id,
            "symbols": list(self._symbols),
            "channels": list(ORDER_STATE_CHANNELS),
            "lastEventAt": self._last_event_at,
            "lastConnectedAt": self._last_connected_at,
            "lastHeartbeatAt": self._last_heartbeat_at,
            "lastError": self._last_error,
            "lastReconcileError": self._last_reconcile_error,
            "reconnectCount": self._reconnect_count,
            "nextRetrySeconds": self._next_retry_seconds,
            "updatedCount": self._updated_count,
            "duplicateCount": self._duplicate_count,
        }

    async def _run(
        self,
        *,
        session: KiwoomSession,
        cycle: AllocationCycle,
        store: CapitalAllocationStore,
        symbols: list[str],
        exchanges: dict[str, str],
        reconcile: ReconcileCallback | None,
    ) -> None:
        consecutive_failures = 0
        while True:
            try:
                async for batch in kiwoom_order_state_stream(
                    session,
                    symbols,
                    exchanges,
                ):
                    if batch.connected and not self._connected:
                        self._last_connected_at = batch.received_at
                    self._connected = batch.connected
                    self._last_heartbeat_at = batch.received_at
                    self._last_error = None
                    self._next_retry_seconds = None
                    consecutive_failures = 0
                    if not batch.events:
                        continue

                    summary = apply_us_order_events(
                        store=store,
                        cycle=cycle,
                        events=batch.events,
                    )
                    self._updated_count += summary.updated_count
                    self._duplicate_count += summary.duplicate_count
                    self._last_event_at = batch.received_at
                    if reconcile is not None:
                        try:
                            await reconcile()
                            self._last_reconcile_error = None
                        except asyncio.CancelledError:
                            raise
                        except Exception as exc:
                            self._last_reconcile_error = exc.__class__.__name__
                self._connected = False
                self._last_error = "ORDER_STATE_STREAM_ENDED"
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._connected = False
                self._last_error = exc.__class__.__name__
            delay = order_state_reconnect_delay(consecutive_failures)
            consecutive_failures += 1
            self._reconnect_count += 1
            self._next_retry_seconds = delay
            await self._sleep(delay)
            self._next_retry_seconds = None


kiwoom_order_state_monitor = KiwoomOrderStateMonitor()


def _safe_symbols(values: list[str]) -> list[str]:
    symbols: list[str] = []
    for value in values:
        symbol = "".join(
            character
            for character in str(value).upper().strip()
            if character.isalnum() or character in {".", "-"}
        )[:12]
        if symbol and symbol not in symbols:
            symbols.append(symbol)
        if len(symbols) >= 20:
            break
    return symbols


def _safe_exchange(value: object) -> str:
    exchange = str(value or "").upper().strip()
    return exchange if exchange in {"ND", "NY", "NA"} else "ND"


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not str(value).strip():
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def order_state_reconnect_delay(failure_index: int) -> int:
    bounded_index = min(max(int(failure_index), 0), 10)
    return min(
        ORDER_STATE_RECONNECT_BASE_SECONDS * (2**bounded_index),
        ORDER_STATE_RECONNECT_MAX_SECONDS,
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
