from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import dataclass, field
import json
import re
import ssl
import time
from typing import Any

from app.core.config import get_settings
from app.schemas.market import UsConditionItem, UsConditionSearchMatch, UsConditionSearchResponse
from app.services.kiwoom_session import KiwoomSession, get_active_or_latest_kiwoom_session
from app.services.kiwoom_websocket import kiwoom_websocket_ssl_context
from app.core.time import now_iso
from app.services.realtime_quote_service import (
    KIWOOM_US_WEBSOCKET_URL,
    build_kiwoom_login_packet,
    build_kiwoom_quote_reg_packet,
    normalize_kiwoom_realtime_message,
    realtime_window_store,
    safe_quote_symbols,
)
from trading_engine.providers.kiwoom_us.request_builder import build_condition_clear_request, build_condition_list_request, build_condition_search_request


class UsConditionSearchError(RuntimeError):
    pass


class _ConditionMonitorRefresh(RuntimeError):
    pass


CONDITION_CATALOG_TTL_SECONDS = 300


@dataclass
class _ConditionMonitorState:
    key: tuple[str, str | None]
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    response: UsConditionSearchResponse | None = None
    error: str | None = None
    error_type: str | None = None
    task: asyncio.Task[None] | None = None
    registered: bool = False
    last_connected_at: str | None = None
    last_received_at: str | None = None
    reconnect_count: int = 0
    next_retry_seconds: int | None = None


class UsConditionService:
    def __init__(self) -> None:
        self._monitor_states: dict[tuple[str, str | None], _ConditionMonitorState] = {}
        self._session_monitor_tasks: dict[str, asyncio.Task[None]] = {}
        self._last_good_responses: dict[tuple[str, str | None], UsConditionSearchResponse] = {}
        self._entry_signal = asyncio.Event()
        self._cached_response: UsConditionSearchResponse | None = None
        self._cached_seq: str | None = None
        self._cached_at = 0.0
        self._monitor_task: asyncio.Task[None] | None = None
        self._monitor_key: tuple[str, str | None] | None = None
        self._monitor_ready: asyncio.Event | None = None
        self._monitor_error: str | None = None
        self._condition_catalog: UsConditionSearchResponse | None = None
        self._condition_catalog_key: str | None = None
        self._condition_catalog_at = 0.0
        self._quote_session_token: str | None = None
        self._quote_symbols: tuple[str, ...] = ()
        self._quote_exchanges: dict[str, str] = {}
        self._quote_connected = False
        self._quote_last_connected_at: str | None = None
        self._quote_last_heartbeat_at: str | None = None
        self._quote_last_error: str | None = None
        self._quote_reconnect_count = 0
        self._quote_next_retry_seconds: int | None = None

    async def get_condition_search(self, seq: str | None = None) -> UsConditionSearchResponse:
        session = get_active_or_latest_kiwoom_session()
        if session is None:
            raise UsConditionSearchError("Kiwoom session is required for US condition search")

        normalized_seq = _normalized_condition_seq(seq)
        state = await self.ensure_realtime_monitor(session, normalized_seq)
        if state.response is not None:
            return state.response
        cached = self._last_good_responses.get((session.session_token, normalized_seq))
        if cached is not None:
            return cached
        raise UsConditionSearchError(state.error or "Kiwoom condition search response was not received")

    async def get_condition_list(self, *, force_refresh: bool = False) -> UsConditionSearchResponse:
        """Fetch the HTS condition catalog without registering realtime search."""
        session = get_active_or_latest_kiwoom_session()
        if session is None:
            raise UsConditionSearchError("Kiwoom session is required for US condition search")
        catalog_key = str(
            getattr(session, "session_token", "")
            or getattr(session, "access_token", "")
        )
        if (
            not force_refresh
            and
            self._condition_catalog is not None
            and self._condition_catalog_key == catalog_key
            and time.monotonic() - self._condition_catalog_at < CONDITION_CATALOG_TTL_SECONDS
        ):
            return self._condition_catalog
        payload, schema_keys = await _send_condition_request(
            session.access_token,
            session.mode,
            build_condition_list_request().body,
        )
        response = UsConditionSearchResponse(
            source="kiwoom-us-condition-list",
            listTrId="usa20280",
            searchTrId="usa20281",
            realtimeTrId="usa20290",
            clearTrId="usa20291",
            updatedAt=now_iso(),
            conditions=_map_conditions(payload),
            selectedSeq=None,
            selectedName=None,
            matches=[],
            schemaKeys=schema_keys,
        )
        self._condition_catalog = response
        self._condition_catalog_key = catalog_key
        self._condition_catalog_at = time.monotonic()
        return response

    async def ensure_quote_monitor(
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
        await self._stop_other_session_monitors(session.session_token)
        self._quote_session_token = session.session_token
        self._quote_symbols = requested
        self._quote_exchanges = requested_exchanges
        task = self._session_monitor_tasks.get(session.session_token)
        if task is None or task.done():
            self._quote_connected = False
            self._quote_last_error = None
            self._quote_reconnect_count = 0
            self._quote_next_retry_seconds = None
            task = asyncio.create_task(
                self._run_session_realtime_monitor(session),
                name="strategy-pilot-us-realtime-hub",
            )
            self._session_monitor_tasks[session.session_token] = task

    async def ensure_quote_union(
        self,
        session: KiwoomSession,
        symbols: list[str],
        exchanges: dict[str, str] | None = None,
        *,
        prefer_existing: bool = False,
    ) -> None:
        requested = safe_quote_symbols(symbols)
        current = list(self._quote_symbols)
        merged = [*current, *requested] if prefer_existing else [*requested, *current]
        merged = safe_quote_symbols(merged)
        merged_exchanges = dict(self._quote_exchanges)
        for symbol in requested:
            merged_exchanges[symbol] = _safe_exchange((exchanges or {}).get(symbol))
        await self.ensure_quote_monitor(session, merged, merged_exchanges)

    async def stop_quote_monitor(self) -> None:
        session_token = self._quote_session_token
        self._quote_session_token = None
        self._quote_symbols = ()
        self._quote_exchanges = {}
        self._quote_connected = False
        self._quote_next_retry_seconds = None
        if session_token is None:
            return
        if any(key[0] == session_token for key in self._monitor_states):
            return
        task = self._session_monitor_tasks.pop(session_token, None)
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    def quote_monitor_status(self) -> dict[str, object]:
        task = (
            self._session_monitor_tasks.get(self._quote_session_token)
            if self._quote_session_token
            else None
        )
        return {
            "running": task is not None and not task.done(),
            "symbols": list(self._quote_symbols),
            "exchanges": dict(self._quote_exchanges),
            "channels": ["FE", "FT"],
            "connected": self._quote_connected,
            "lastConnectedAt": self._quote_last_connected_at,
            "lastHeartbeatAt": self._quote_last_heartbeat_at,
            "reconnectCount": self._quote_reconnect_count,
            "nextRetrySeconds": self._quote_next_retry_seconds,
            "lastError": self._quote_last_error,
        }

    async def ensure_realtime_monitor(
        self,
        session: KiwoomSession,
        seq: str | None = None,
    ) -> _ConditionMonitorState:
        normalized_seq = _normalized_condition_seq(seq)
        key = (session.session_token, normalized_seq)
        await self._stop_other_session_monitors(session.session_token)
        state = self._monitor_states.get(key)
        if state is None:
            state = _ConditionMonitorState(key=key)
            self._monitor_states[key] = state
        task = self._session_monitor_tasks.get(session.session_token)
        if task is None or task.done():
            task = asyncio.create_task(
                self._run_session_realtime_monitor(session),
                name="strategy-pilot-us-condition-monitor",
            )
            self._session_monitor_tasks[session.session_token] = task
        for monitor_key, monitor_state in self._monitor_states.items():
            if monitor_key[0] == session.session_token:
                monitor_state.task = task
        self._sync_legacy_state(state)
        if not state.ready.is_set():
            try:
                await asyncio.wait_for(state.ready.wait(), timeout=12)
            except asyncio.TimeoutError as exc:
                raise UsConditionSearchError("Kiwoom condition search websocket timed out") from exc
        self._sync_legacy_state(state)
        return state

    async def stop_realtime_monitor(self) -> None:
        tasks = list(self._session_monitor_tasks.values())
        self._monitor_states.clear()
        self._session_monitor_tasks.clear()
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task
        self._monitor_task = None
        self._monitor_key = None
        self._monitor_ready = None
        self._monitor_error = None
        self._entry_signal.clear()

    async def wait_for_entry_signal(self, timeout: float) -> bool:
        if self._entry_signal.is_set():
            self._entry_signal.clear()
            return True
        try:
            await asyncio.wait_for(self._entry_signal.wait(), timeout=max(float(timeout), 0.01))
        except asyncio.TimeoutError:
            return False
        self._entry_signal.clear()
        return True

    async def stop_condition_monitor(self, seq: str | None) -> None:
        normalized_seq = _normalized_condition_seq(seq)
        keys = [key for key in self._monitor_states if key[1] == normalized_seq]
        session_tokens: set[str] = set()
        for key in keys:
            self._monitor_states.pop(key)
            session_tokens.add(key[0])
        tasks: list[asyncio.Task[None]] = []
        for session_token in session_tokens:
            if any(key[0] == session_token for key in self._monitor_states):
                continue
            task = self._session_monitor_tasks.pop(session_token, None)
            if task is not None:
                task.cancel()
                tasks.append(task)
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task
        if self._monitor_key in keys:
            self._monitor_task = None
            self._monitor_key = None
            self._monitor_ready = None
            self._monitor_error = None

    def monitor_status(self, seq: str | None) -> dict[str, object]:
        normalized_seq = _normalized_condition_seq(seq)
        states = [
            state
            for key, state in self._monitor_states.items()
            if key[1] == normalized_seq
        ]
        state = next((item for item in states if item.response is not None), states[0] if states else None)
        response = state.response if state is not None else None
        return {
            "active": bool(
                state
                and state.task
                and not state.task.done()
                and state.registered
                and response is not None
                and state.error is None
            ),
            "registered": bool(state and state.registered),
            "selectedSeq": response.selectedSeq if response else normalized_seq,
            "selectedName": response.selectedName if response else None,
            "matchCount": len(response.matches) if response else 0,
            "error": state.error if state else None,
            "errorType": state.error_type if state else None,
            "lastConnectedAt": state.last_connected_at if state else None,
            "lastReceivedAt": state.last_received_at if state else None,
            "reconnectCount": state.reconnect_count if state else 0,
            "nextRetrySeconds": state.next_retry_seconds if state else None,
        }

    def monitor_matches(self, seq: str | None) -> list[UsConditionSearchMatch]:
        normalized_seq = _normalized_condition_seq(seq)
        state = next(
            (
                state
                for key, state in self._monitor_states.items()
                if key[1] == normalized_seq and state.response is not None
            ),
            None,
        )
        return list(state.response.matches) if state and state.response else []

    async def _stop_other_session_monitors(self, session_token: str) -> None:
        stale_keys = [key for key in self._monitor_states if key[0] != session_token]
        stale_session_tokens = {key[0] for key in stale_keys}
        if self._quote_session_token and self._quote_session_token != session_token:
            stale_session_tokens.add(self._quote_session_token)
        for key in stale_keys:
            self._monitor_states.pop(key)
        tasks: list[asyncio.Task[None]] = []
        for stale_session_token in stale_session_tokens:
            task = self._session_monitor_tasks.pop(stale_session_token, None)
            if task is not None:
                task.cancel()
                tasks.append(task)
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task
        if self._quote_session_token and self._quote_session_token != session_token:
            self._quote_session_token = None
            self._quote_symbols = ()
            self._quote_exchanges = {}
            self._quote_connected = False
            self._quote_next_retry_seconds = None

    async def _run_session_realtime_monitor(self, session: KiwoomSession) -> None:
        import websockets

        url = KIWOOM_US_WEBSOCKET_URL
        while True:
            registered: dict[str | None, UsConditionItem] = {}
            registered_quotes: tuple[str, ...] = ()
            websocket: Any = None
            for key, state in self._monitor_states.items():
                if key[0] == session.session_token:
                    state.registered = False
            try:
                try:
                    async with websockets.connect(
                        url,
                        ping_interval=None,
                        open_timeout=10,
                        close_timeout=3,
                        ssl=kiwoom_websocket_ssl_context(),
                    ) as websocket:
                        await websocket.send(json.dumps(build_kiwoom_login_packet(session.access_token)))
                        login_response = await _receive_condition_message(websocket, timeout=10)
                        if login_response.get("trnm") == "LOGIN" and login_response.get("return_code") not in (0, "0", None):
                            raise UsConditionSearchError("Kiwoom condition search login failed")

                        await websocket.send(json.dumps(build_condition_list_request().body))
                        list_response = await _receive_condition_message(websocket, timeout=10)
                        conditions = _map_conditions(list_response)
                        schema_keys = {str(key) for key in list_response.keys()}
                        if not conditions:
                            await websocket.send(json.dumps(build_condition_list_request().body))
                            retry_list_response = await _receive_condition_message(websocket, timeout=10)
                            conditions = _map_conditions(retry_list_response)
                            schema_keys.update(str(key) for key in retry_list_response.keys())
                        if (
                            not conditions
                            and self._condition_catalog_key == session.session_token
                            and self._condition_catalog is not None
                            and self._condition_catalog.conditions
                        ):
                            conditions = list(self._condition_catalog.conditions)
                        if not conditions:
                            raise UsConditionSearchError("Kiwoom condition search response was not received")
                        self._condition_catalog = UsConditionSearchResponse(
                            source="kiwoom-us-condition-list",
                            listTrId="usa20280",
                            searchTrId="usa20281",
                            realtimeTrId="usa20290",
                            clearTrId="usa20291",
                            updatedAt=now_iso(),
                            conditions=conditions,
                            selectedSeq=None,
                            selectedName=None,
                            matches=[],
                            schemaKeys=sorted(schema_keys),
                        )
                        self._condition_catalog_key = session.session_token
                        self._condition_catalog_at = time.monotonic()

                        cleanup_seqs = {
                            selected.seq
                            for key, _state in self._monitor_states.items()
                            if key[0] == session.session_token
                            for selected in [_select_condition(conditions, key[1])]
                            if selected is not None
                        }
                        for cleanup_seq in sorted(cleanup_seqs):
                            await websocket.send(json.dumps(build_condition_clear_request(cleanup_seq).body))
                            try:
                                await _receive_condition_message(websocket, timeout=2)
                            except (asyncio.TimeoutError, UsConditionSearchError):
                                pass

                        while True:
                            active_states = {
                                key[1]: state
                                for key, state in self._monitor_states.items()
                                if key[0] == session.session_token
                            }
                            desired_quotes = (
                                self._quote_symbols
                                if self._quote_session_token == session.session_token
                                else ()
                            )
                            if not active_states and not desired_quotes:
                                return

                            removed = [requested_seq for requested_seq in registered if requested_seq not in active_states]
                            for requested_seq in removed:
                                selected = registered.pop(requested_seq)
                                await websocket.send(json.dumps(build_condition_clear_request(selected.seq).body))

                            pending = [
                                (requested_seq, state)
                                for requested_seq, state in active_states.items()
                                if requested_seq not in registered
                            ]
                            if registered and pending:
                                raise _ConditionMonitorRefresh
                            for index, (requested_seq, state) in enumerate(pending):
                                selected = _select_condition(conditions, requested_seq)
                                if selected is None:
                                    state.error = "Kiwoom condition search sequence was not found"
                                    state.ready.set()
                                    continue
                                await websocket.send(
                                    json.dumps(build_condition_search_request(selected.seq, realtime=False).body)
                                )
                                general_response = await _receive_condition_message(websocket, timeout=10)
                                matches = _map_matches(general_response)
                                response_schema_keys = set(schema_keys)
                                response_schema_keys.update(str(key) for key in general_response.keys())
                                self._store_monitor_response(
                                    state,
                                    requested_seq,
                                    conditions,
                                    selected,
                                    matches,
                                    response_schema_keys,
                                )
                                await websocket.send(
                                    json.dumps(build_condition_search_request(selected.seq, realtime=True).body)
                                )
                                registered[requested_seq] = selected
                                state.registered = True
                                state.last_connected_at = now_iso()
                                state.next_retry_seconds = None
                                state.ready.set()
                                if index < len(pending) - 1:
                                    try:
                                        registration_response = await _receive_condition_message(websocket, timeout=2)
                                    except asyncio.TimeoutError:
                                        registration_response = {}
                                    if registration_response:
                                        response_schema_keys = set(
                                            state.response.schemaKeys if state.response else schema_keys
                                        )
                                        response_schema_keys.update(str(key) for key in registration_response.keys())
                                        registration_matches = _merge_condition_matches(
                                            list(state.response.matches if state.response else []),
                                            _map_matches(registration_response),
                                        )
                                        self._store_monitor_response(
                                            state,
                                            requested_seq,
                                            conditions,
                                            selected,
                                            registration_matches,
                                            response_schema_keys,
                                        )

                            if desired_quotes and desired_quotes != registered_quotes:
                                await websocket.send(
                                    json.dumps(
                                        build_kiwoom_quote_reg_packet(
                                            list(desired_quotes),
                                            exchanges=self._quote_exchanges,
                                        )
                                    )
                                )
                                registered_quotes = tuple(desired_quotes)
                                connected_at = now_iso()
                                if not self._quote_connected:
                                    self._quote_last_connected_at = connected_at
                                self._quote_connected = True
                                self._quote_last_heartbeat_at = connected_at
                                self._quote_last_error = None
                                self._quote_next_retry_seconds = None

                            try:
                                message = await _receive_condition_message(websocket, timeout=1)
                            except asyncio.TimeoutError:
                                if registered_quotes:
                                    self._quote_connected = True
                                    self._quote_last_heartbeat_at = now_iso()
                                continue
                            if _is_quote_realtime_message(message):
                                event_time = now_iso()
                                for event in normalize_kiwoom_realtime_message(message):
                                    realtime_window_store.record(event)
                                self._quote_connected = True
                                self._quote_last_heartbeat_at = event_time
                                self._quote_last_error = None
                                self._quote_next_retry_seconds = None
                                continue
                            requested_seq = _condition_message_requested_seq(message, registered)
                            state = active_states.get(requested_seq)
                            selected = registered.get(requested_seq)
                            if state is None or selected is None:
                                continue
                            response_schema_keys = set(state.response.schemaKeys if state.response else schema_keys)
                            response_schema_keys.update(str(key) for key in message.keys())
                            matches = _apply_realtime_condition_message(
                                list(state.response.matches if state.response else []),
                                message,
                            )
                            self._store_monitor_response(
                                state,
                                requested_seq,
                                conditions,
                                selected,
                                matches,
                                response_schema_keys,
                            )
                finally:
                    if websocket is not None:
                        for selected in registered.values():
                            with suppress(Exception):
                                await websocket.send(json.dumps(build_condition_clear_request(selected.seq).body))
            except asyncio.CancelledError:
                raise
            except _ConditionMonitorRefresh:
                self._quote_connected = False
                continue
            except Exception as exc:
                if self._quote_session_token == session.session_token and self._quote_symbols:
                    self._quote_connected = False
                    self._quote_last_error = _safe_condition_error(exc)
                    self._quote_reconnect_count += 1
                    self._quote_next_retry_seconds = 2
                for key, state in self._monitor_states.items():
                    if key[0] != session.session_token:
                        continue
                    state.registered = False
                    state.error = _safe_condition_error(exc)
                    state.error_type = exc.__class__.__name__
                    state.reconnect_count += 1
                    state.next_retry_seconds = 2
                    state.ready.set()
                    self._sync_legacy_state(state)
                await asyncio.sleep(2)
                self._quote_next_retry_seconds = None
                for key, state in self._monitor_states.items():
                    if key[0] == session.session_token:
                        state.next_retry_seconds = None

    def _store_monitor_response(
        self,
        state: _ConditionMonitorState,
        seq: str | None,
        conditions: list[UsConditionItem],
        selected: UsConditionItem,
        matches: list[UsConditionSearchMatch],
        schema_keys: set[str],
    ) -> None:
        previous_codes = {
            item.code
            for item in (state.response.matches if state.response is not None else [])
            if item.code
        }
        current_codes = {item.code for item in matches if item.code}
        state.response = UsConditionSearchResponse(
            source="kiwoom-us-condition-search-realtime",
            listTrId="usa20280",
            searchTrId="usa20281",
            realtimeTrId="usa20290",
            clearTrId="usa20291",
            updatedAt=now_iso(),
            conditions=conditions,
            selectedSeq=selected.seq,
            selectedName=selected.name,
            matches=list(matches),
            schemaKeys=sorted(schema_keys),
        )
        state.error = None
        state.error_type = None
        state.last_received_at = state.response.updatedAt
        self._last_good_responses[state.key] = state.response
        self._cached_response = state.response
        self._cached_seq = seq
        self._cached_at = time.monotonic()
        self._sync_legacy_state(state)
        if current_codes - previous_codes:
            self._entry_signal.set()

    def _sync_legacy_state(self, state: _ConditionMonitorState) -> None:
        self._monitor_task = state.task
        self._monitor_key = state.key
        self._monitor_ready = state.ready
        self._monitor_error = state.error
        if state.response is not None:
            self._cached_response = state.response
            self._cached_seq = state.key[1]

    def reset_for_tests(self) -> None:
        for state in self._monitor_states.values():
            if state.task is not None and not state.task.done():
                state.task.cancel()
        self._monitor_states.clear()
        self._session_monitor_tasks.clear()
        self._last_good_responses.clear()
        self._cached_response = None
        self._cached_seq = None
        self._cached_at = 0.0
        self._monitor_task = None
        self._monitor_key = None
        self._monitor_ready = None
        self._monitor_error = None
        self._entry_signal = asyncio.Event()


async def _send_condition_strategy_sequence(
    access_token: str,
    mode: str,
    requested_seq: str | None,
) -> tuple[list[UsConditionItem], UsConditionItem | None, list[UsConditionSearchMatch], list[str]]:
    import websockets

    url = KIWOOM_US_WEBSOCKET_URL
    schema_keys: set[str] = set()
    try:
        async with websockets.connect(url, ping_interval=None, open_timeout=10, close_timeout=3, ssl=kiwoom_websocket_ssl_context()) as websocket:
            await websocket.send(json.dumps(build_kiwoom_login_packet(access_token)))
            login_response = await _receive_condition_message(websocket, timeout=10)
            if login_response.get("trnm") == "LOGIN" and login_response.get("return_code") not in (0, "0", None):
                raise UsConditionSearchError("Kiwoom condition search login failed")

            await websocket.send(json.dumps(build_condition_list_request().body))
            list_response = await _receive_condition_message(websocket, timeout=10)
            schema_keys.update(str(key) for key in list_response.keys())
            conditions = _map_conditions(list_response)
            selected = _select_condition(conditions, requested_seq)
            if selected is None:
                return conditions, None, [], sorted(schema_keys)

            await websocket.send(json.dumps(build_condition_search_request(selected.seq, realtime=False).body))
            general_response = await _receive_condition_message(websocket, timeout=10)
            schema_keys.update(str(key) for key in general_response.keys())
            matches = _map_matches(general_response)

            await websocket.send(json.dumps(build_condition_search_request(selected.seq, realtime=True).body))
            try:
                realtime_response = await _receive_condition_message(websocket, timeout=5)
            except asyncio.TimeoutError:
                realtime_response = {}
            schema_keys.update(str(key) for key in realtime_response.keys())
            matches = _merge_condition_matches(matches, _map_matches(realtime_response))
            await websocket.send(json.dumps(build_condition_clear_request(selected.seq).body))
            return conditions, selected, matches, sorted(schema_keys)
    except UsConditionSearchError:
        raise
    except (asyncio.TimeoutError, json.JSONDecodeError, OSError, ssl.SSLError) as exc:
        raise UsConditionSearchError(_safe_condition_error(exc)) from exc
    except Exception as exc:
        raise UsConditionSearchError(_safe_condition_error(exc)) from exc


async def _send_condition_request(access_token: str, mode: str, packet: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    import websockets

    url = KIWOOM_US_WEBSOCKET_URL
    try:
        async with websockets.connect(url, ping_interval=None, open_timeout=10, close_timeout=3, ssl=kiwoom_websocket_ssl_context()) as websocket:
            await websocket.send(json.dumps(build_kiwoom_login_packet(access_token)))
            login_response = await _receive_condition_message(websocket, timeout=10)
            if login_response.get("trnm") == "LOGIN" and login_response.get("return_code") not in (0, "0", None):
                raise UsConditionSearchError("Kiwoom condition search login failed")

            await websocket.send(json.dumps(packet))
            message = await _receive_condition_message(websocket, timeout=10)
            return message, sorted(str(key) for key in message.keys())
    except UsConditionSearchError:
        raise
    except (asyncio.TimeoutError, json.JSONDecodeError, OSError, ssl.SSLError) as exc:
        raise UsConditionSearchError(_safe_condition_error(exc)) from exc
    except Exception as exc:
        raise UsConditionSearchError(_safe_condition_error(exc)) from exc
    return {}, []


async def _receive_condition_message(websocket: Any, *, timeout: float) -> dict[str, Any]:
    for _ in range(8):
        raw = await asyncio.wait_for(websocket.recv(), timeout=timeout)
        message = json.loads(raw)
        if message.get("trnm") == "PING":
            await websocket.send(json.dumps(message))
            continue
        if message.get("return_code") not in (0, "0", None):
            raw_code = str(message.get("return_code", ""))
            safe_code = raw_code if re.fullmatch(r"-?\d{1,10}", raw_code) else "unknown"
            raise UsConditionSearchError(f"Kiwoom condition search request failed (code {safe_code})")
        return message
    raise UsConditionSearchError("Kiwoom condition search response was not received")


def _map_conditions(payload: dict[str, Any]) -> list[UsConditionItem]:
    rows = _extract_rows(payload)
    conditions: list[UsConditionItem] = []
    for index, row in enumerate(rows, start=1):
        seq = _first_text(row, "seq", "condition_seq", "cond_seq", "search_seq", "scrn_no", "id") or str(index).zfill(3)
        name = _first_text(row, "name", "condition_name", "cond_nm", "search_name", "cnd_nm", "title") or f"조건식 {seq}"
        conditions.append(UsConditionItem(seq=seq, name=name))
    return conditions


def _normalized_condition_seq(seq: str | None) -> str | None:
    cleaned = str(seq or "").strip()
    return cleaned or None


def _is_quote_realtime_message(payload: dict[str, Any]) -> bool:
    trnm = str(payload.get("trnm") or "").upper()
    if trnm in {"FE", "FT"}:
        return True
    data = payload.get("data")
    if not isinstance(data, list):
        return False
    return any(
        isinstance(row, dict)
        and str(row.get("type") or row.get("trnm") or "").upper() in {"FE", "FT"}
        for row in data
    )


def _safe_exchange(value: object) -> str:
    exchange = str(value or "").upper().strip()
    return exchange if exchange in {"ND", "NY", "NA"} else "ND"


def _condition_message_requested_seq(
    payload: dict[str, Any],
    registered: dict[str | None, UsConditionItem],
) -> str | None:
    message_seq = _first_text(
        payload,
        "seq",
        "condition_seq",
        "cond_seq",
        "search_seq",
        "scrn_no",
    )
    if message_seq is None:
        for row in _extract_rows(payload):
            message_seq = _first_text(
                row,
                "seq",
                "condition_seq",
                "cond_seq",
                "search_seq",
                "scrn_no",
            )
            if message_seq is not None:
                break
    if message_seq is not None:
        for requested_seq, selected in registered.items():
            if message_seq in {requested_seq, selected.seq}:
                return requested_seq
    if len(registered) == 1:
        return next(iter(registered))
    return "__unrouted__"


def _map_matches(payload: dict[str, Any]) -> list[UsConditionSearchMatch]:
    rows = _extract_rows(payload)
    matches: list[UsConditionSearchMatch] = []
    for row in rows:
        code = _first_text(row, "stk_cd", "stk_code", "jmcode", "symbol", "code", "item", "9001")
        if not code:
            continue
        matches.append(
            UsConditionSearchMatch(
                code=code,
                name=_first_text(row, "stk_nm", "stk_enm", "name", "302"),
                exchange=_first_text(row, "stex_tp", "exchange"),
                price=_optional_float(_row_value(row, "cur_prc", "curr_pric", "price", "10")),
                changeRate=_optional_float(_row_value(row, "flu_rt", "changeRate", "diff_rate_for_gjga", "12")),
                volume=_optional_int(_row_value(row, "acc_trde_qty", "trde_qty", "volume", "13")),
            )
        )
    return matches


def _merge_condition_matches(
    current: list[UsConditionSearchMatch],
    incoming: list[UsConditionSearchMatch],
) -> list[UsConditionSearchMatch]:
    merged = {item.code: item for item in current if item.code}
    for item in incoming:
        if item.code:
            merged[item.code] = _merge_condition_match(merged.get(item.code), item)
    return list(merged.values())


def _apply_realtime_condition_message(
    current: list[UsConditionSearchMatch],
    payload: dict[str, Any],
) -> list[UsConditionSearchMatch]:
    merged = {item.code: item for item in current if item.code}
    for row in _extract_rows(payload):
        code = _first_text(row, "stk_cd", "stk_code", "jmcode", "symbol", "code", "item", "9001")
        if not code:
            continue
        action = (_first_text(row, "843", "action", "event_type") or "I").upper()
        if action == "D":
            merged.pop(code, None)
            continue
        mapped = _map_matches({"data": [row]})
        if mapped:
            merged[code] = _merge_condition_match(merged.get(code), mapped[0])
    return list(merged.values())


def _merge_condition_match(
    existing: UsConditionSearchMatch | None,
    incoming: UsConditionSearchMatch,
) -> UsConditionSearchMatch:
    if existing is None:
        return incoming
    return existing.model_copy(
        update={
            "name": incoming.name or existing.name,
            "exchange": incoming.exchange or existing.exchange,
            "price": incoming.price if incoming.price is not None else existing.price,
            "changeRate": incoming.changeRate if incoming.changeRate is not None else existing.changeRate,
            "volume": incoming.volume if incoming.volume is not None else existing.volume,
        }
    )


async def kiwoom_condition_stream(session: KiwoomSession, seq: str | None = None) -> AsyncIterator[dict[str, object]]:
    selected_seq = seq
    yield {
        "type": "CONDITION_STATUS",
        "provider": "kiwoom",
        "status": "CONNECTING",
        "seq": selected_seq,
        "trId": "usa20290",
        "timestamp": now_iso(),
    }
    import websockets

    url = KIWOOM_US_WEBSOCKET_URL
    try:
        async with websockets.connect(url, ping_interval=None, open_timeout=10, close_timeout=3, ssl=kiwoom_websocket_ssl_context()) as websocket:
            await websocket.send(json.dumps(build_kiwoom_login_packet(session.access_token)))
            login_response = await _receive_condition_message(websocket, timeout=10)
            if login_response.get("trnm") == "LOGIN" and login_response.get("return_code") not in (0, "0", None):
                yield {"type": "ERROR", "provider": "kiwoom", "errorType": "KIWOOM_CONDITION_LOGIN_FAILED", "timestamp": now_iso()}
                return

            await websocket.send(json.dumps(build_condition_list_request().body))
            list_response = await _receive_condition_message(websocket, timeout=10)
            conditions = _map_conditions(list_response)
            selected = _select_condition(conditions, selected_seq)
            if selected is None:
                yield {"type": "ERROR", "provider": "kiwoom", "errorType": "KIWOOM_CONDITION_LIST_EMPTY", "timestamp": now_iso()}
                return
            selected_seq = selected.seq

            await websocket.send(json.dumps(build_condition_search_request(selected_seq, realtime=False).body))
            general_response = await _receive_condition_message(websocket, timeout=10)
            index = 0
            for match in _map_matches(general_response):
                index += 1
                yield _condition_match_event(match, index=index, provider="kiwoom", condition_name=selected.name)

            await websocket.send(json.dumps(build_condition_search_request(selected_seq, realtime=True).body))
            yield {
                "type": "CONDITION_STATUS",
                "provider": "kiwoom",
                "status": "CONNECTED",
                "seq": selected_seq,
                "trId": "usa20290",
                "timestamp": now_iso(),
            }
            try:
                while True:
                    message = await _receive_condition_message(websocket, timeout=30)
                    matches = _map_matches(message)
                    if not matches:
                        yield {
                            "type": "CONDITION_SCHEMA",
                            "provider": "kiwoom",
                            "trId": "usa20290",
                            "schemaKeys": sorted(str(key) for key in message.keys()),
                            "timestamp": now_iso(),
                        }
                        continue
                    for match in matches:
                        index += 1
                        yield _condition_match_event(match, index=index, provider="kiwoom", condition_name=None)
            finally:
                try:
                    await websocket.send(json.dumps(build_condition_clear_request(selected_seq).body))
                except Exception:
                    pass
    except (asyncio.TimeoutError, json.JSONDecodeError, OSError, ssl.SSLError, Exception):
        yield {"type": "ERROR", "provider": "kiwoom", "errorType": "KIWOOM_CONDITION_STREAM_UNAVAILABLE", "timestamp": now_iso()}


def _condition_match_event(match: UsConditionSearchMatch, *, index: int, provider: str, condition_name: str | None) -> dict[str, object]:
    return {
        "type": "CONDITION_MATCH",
        "provider": provider,
        "trId": "usa20290",
        "rank": index,
        "conditionName": condition_name,
        "code": match.code,
        "name": match.name or match.code,
        "exchange": match.exchange,
        "price": match.price,
        "changeRate": match.changeRate,
        "volume": match.volume,
        "timestamp": now_iso(),
    }


def _safe_condition_error(exc: Exception) -> str:
    if isinstance(exc, UsConditionSearchError):
        known_messages = {
            "Kiwoom condition search login failed",
            "Kiwoom condition search request failed",
            "Kiwoom condition search response was not received",
            "Kiwoom condition search sequence was not found",
        }
        message = str(exc)
        if re.fullmatch(r"Kiwoom condition search request failed \(code (?:-?\d{1,10}|unknown)\)", message):
            return message
        return message if message in known_messages else "Kiwoom condition search websocket unavailable"
    if isinstance(exc, ssl.SSLError):
        return "Kiwoom condition search websocket SSL verification failed"
    if isinstance(exc, asyncio.TimeoutError):
        return "Kiwoom condition search websocket timed out"
    return "Kiwoom condition search websocket unavailable"


def _extract_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = [
        payload.get("result_list"),
        payload.get("condition_list"),
        payload.get("conditions"),
        payload.get("items"),
        payload.get("data"),
        payload.get("list"),
    ]
    for candidate in candidates:
        if isinstance(candidate, list):
            rows: list[dict[str, Any]] = []
            for row in candidate:
                if isinstance(row, dict):
                    rows.append(row)
                elif isinstance(row, (list, tuple)) and len(row) >= 2:
                    rows.append({"seq": row[0], "name": row[1]})
            if rows:
                return rows
        if isinstance(candidate, dict):
            nested = _extract_rows(candidate)
            if nested:
                return nested
    return []


def _select_condition(conditions: list[UsConditionItem], seq: str | None) -> UsConditionItem | None:
    if not conditions:
        return None
    if seq:
        for condition in conditions:
            if condition.seq == seq:
                return condition
        return None
    return conditions[0]


def _first_text(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = _row_value(row, key)
        if value not in (None, ""):
            return str(value).strip()
    return None


def _row_value(row: dict[str, Any], *keys: str) -> Any:
    values = row.get("values") if isinstance(row.get("values"), dict) else {}
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
        value = values.get(key)
        if value not in (None, ""):
            return value
    return None


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


us_condition_service = UsConditionService()
