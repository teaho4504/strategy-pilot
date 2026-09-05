from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
import sys
from types import SimpleNamespace

import pytest

from app.services.kiwoom_session import KiwoomSession
from app.services import us_order_state_monitor as monitor_module
from trading_engine.providers.kiwoom_us.order_event_mapper import (
    map_us_order_realtime_payload,
)
from trading_engine.risk.allocation_store import CapitalAllocationStore
from trading_engine.risk.capital_allocator import (
    CapitalAllocationState,
    evaluate_capital_allocation,
)

def _session() -> KiwoomSession:
    return KiwoomSession(
        session_token="safe-session",
        mode="live",
        account_no="configured",
        base_url="https://api.kiwoom.com",
        access_token="TOKEN-MUST-NOT-LEAK",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )


def _submitted_allocation(tmp_path):
    store = CapitalAllocationStore(tmp_path / "allocation.sqlite3")
    cycle = store.ensure_cycle(
        account_scope="profile-a",
        market_date="2026-07-30",
        orderable_cash=4_000,
    )
    decision = evaluate_capital_allocation(
        state=CapitalAllocationState(
            cycle_capital=4_000,
            orderable_cash=4_000,
        ),
        symbol="NVDA",
        reference_price=100,
        max_quantity=1,
    )
    reservation = store.reserve(
        cycle=cycle,
        decision=decision,
        strategy="strategy-a",
        exchange="ND",
        reference_price=100,
    )
    store.mark_submitted(reservation.id, "order-a")
    return store, cycle


def _enable_monitor(monkeypatch) -> None:
    monkeypatch.setenv("KIWOOM_US_ORDER_STATE_MONITOR_ENABLED", "true")
    monkeypatch.setenv(
        "KIWOOM_US_ORDER_STATE_MONITOR_CONFIRM",
        monitor_module.ORDER_STATE_MONITOR_CONFIRM,
    )


def _full_fill_payload() -> dict[str, object]:
    return {
        "trnm": "REAL",
        "data": [
            {
                "type": "F5",
                "item": "NVDA",
                "values": {
                    "9201": "ACCOUNT-MUST-NOT-LEAK",
                    "9203": "order-a",
                    "9001": "NVDA",
                    "907": "02",
                    "908": "101501",
                    "913": "체결완료",
                    "900": "1",
                    "902": "0",
                    "909": "fill-a",
                    "910": "100.25",
                    "911": "1",
                    "8043": "USD",
                },
            }
        ],
    }


def test_order_state_monitor_is_disabled_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("KIWOOM_US_ORDER_STATE_MONITOR_ENABLED", raising=False)
    monkeypatch.delenv(
        "KIWOOM_US_ORDER_STATE_MONITOR_CONFIRM",
        raising=False,
    )
    store, cycle = _submitted_allocation(tmp_path)
    monitor = monitor_module.KiwoomOrderStateMonitor()

    async def scenario():
        await monitor.ensure(
            session=_session(),
            cycle=cycle,
            store=store,
            symbols=["NVDA"],
            exchanges={"NVDA": "ND"},
        )
        return monitor.status()

    status = asyncio.run(scenario())

    assert status["enabled"] is False
    assert status["running"] is False
    assert status["connected"] is False


def test_order_state_registration_contains_only_symbols_and_f4_f5():
    packet = monitor_module.build_order_state_registration_packet(
        ["nvda", "MSFT"],
        {"NVDA": "ND", "MSFT": "NY"},
    )

    assert packet == {
        "trnm": "REG",
        "grp_no": "91",
        "refresh": "1",
        "data": [
            {
                "item": [
                    {"jmcode": "NVDA", "stex_tp": "ND"},
                    {"jmcode": "MSFT", "stex_tp": "NY"},
                ],
                "type": ["F4", "F5"],
            }
        ],
    }
    assert "token" not in str(packet).lower()
    assert "account" not in str(packet).lower()


def test_order_state_stream_logs_in_registers_and_strips_account(
    monkeypatch,
):
    _enable_monitor(monkeypatch)

    class FakeSocket:
        def __init__(self):
            self.sent: list[dict[str, object]] = []
            self.responses = [
                {"trnm": "LOGIN", "return_code": 0},
                {"trnm": "PING", "timestamp": "fixture"},
                _full_fill_payload(),
            ]

        async def send(self, payload: str):
            self.sent.append(json.loads(payload))

        async def recv(self):
            return json.dumps(self.responses.pop(0))

    socket = FakeSocket()

    class FakeContext:
        async def __aenter__(self):
            return socket

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeWebsockets:
        @staticmethod
        def connect(*args, **kwargs):
            assert kwargs.get("ssl") is not None
            return FakeContext()

    monkeypatch.setitem(sys.modules, "websockets", FakeWebsockets)

    async def collect():
        batches = []
        async for batch in monitor_module.kiwoom_order_state_stream(
            _session(),
            ["NVDA"],
            {"NVDA": "ND"},
        ):
            batches.append(batch)
            if batch.events:
                break
        return batches

    batches = asyncio.run(collect())

    assert socket.sent[0]["trnm"] == "LOGIN"
    assert socket.sent[1]["data"][0]["type"] == ["F4", "F5"]
    assert socket.sent[2] == {"trnm": "PING", "timestamp": "fixture"}
    assert batches[0].connected is True
    assert batches[1].events[0].order_no == "order-a"
    assert "ACCOUNT-MUST-NOT-LEAK" not in repr(batches[1].events)


def test_order_state_stream_rejects_unexpected_login_response(
    monkeypatch,
):
    _enable_monitor(monkeypatch)

    class FakeSocket:
        def __init__(self):
            self.sent: list[dict[str, object]] = []

        async def send(self, payload: str):
            self.sent.append(json.loads(payload))

        async def recv(self):
            return json.dumps({"trnm": "REAL", "return_code": 0})

    socket = FakeSocket()

    class FakeContext:
        async def __aenter__(self):
            return socket

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeWebsockets:
        @staticmethod
        def connect(*args, **kwargs):
            return FakeContext()

    monkeypatch.setitem(sys.modules, "websockets", FakeWebsockets)

    async def scenario():
        stream = monitor_module.kiwoom_order_state_stream(
            _session(),
            ["NVDA"],
            {"NVDA": "ND"},
        )
        with pytest.raises(
            monitor_module.UsOrderStateMonitorError,
            match="login failed",
        ):
            await anext(stream)

    asyncio.run(scenario())

    assert len(socket.sent) == 1
    assert socket.sent[0]["trnm"] == "LOGIN"


def test_order_state_reconnect_delay_is_bounded():
    assert [
        monitor_module.order_state_reconnect_delay(index)
        for index in (0, 1, 2, 3, 4, 5, 20)
    ] == [1, 2, 4, 8, 16, 30, 30]


def test_monitor_reconnects_with_backoff_and_resets_after_connect(
    monkeypatch,
    tmp_path,
):
    _enable_monitor(monkeypatch)
    store, cycle = _submitted_allocation(tmp_path)
    attempts = 0
    delays: list[float] = []
    connected = asyncio.Event()

    async def fake_sleep(delay: float):
        delays.append(delay)

    async def flaky_stream(session, symbols, exchanges):
        nonlocal attempts
        attempts += 1
        if attempts <= 2:
            raise OSError("temporary failure")
        yield monitor_module.OrderStateStreamBatch(
            connected=True,
            events=(),
            received_at="2026-07-30T12:00:00+00:00",
        )
        await connected.wait()

    monkeypatch.setattr(
        monitor_module,
        "kiwoom_order_state_stream",
        flaky_stream,
    )
    monitor = monitor_module.KiwoomOrderStateMonitor(sleep=fake_sleep)

    async def scenario():
        await monitor.ensure(
            session=_session(),
            cycle=cycle,
            store=store,
            symbols=["NVDA"],
            exchanges={"NVDA": "ND"},
        )
        for _ in range(20):
            if monitor.status()["connected"]:
                break
            await asyncio.sleep(0)
        status = monitor.status()
        await monitor.stop()
        return status

    status = asyncio.run(scenario())

    assert attempts == 3
    assert delays == [1, 2]
    assert status["connected"] is True
    assert status["reconnectCount"] == 2
    assert status["nextRetrySeconds"] is None
    assert status["lastConnectedAt"] == "2026-07-30T12:00:00+00:00"
    assert status["lastHeartbeatAt"] == "2026-07-30T12:00:00+00:00"


def test_monitor_applies_fill_and_runs_rest_reconcile_callback(
    monkeypatch,
    tmp_path,
):
    _enable_monitor(monkeypatch)
    store, cycle = _submitted_allocation(tmp_path)
    events = tuple(map_us_order_realtime_payload(_full_fill_payload()))
    reconciled = 0

    async def fake_stream(session, symbols, exchanges):
        yield monitor_module.OrderStateStreamBatch(
            connected=True,
            events=events,
            received_at="2026-07-30T12:00:00+00:00",
        )
        await asyncio.sleep(60)

    async def reconcile():
        nonlocal reconciled
        reconciled += 1

    monkeypatch.setattr(
        monitor_module,
        "kiwoom_order_state_stream",
        fake_stream,
    )
    monitor = monitor_module.KiwoomOrderStateMonitor()

    async def scenario():
        await monitor.ensure(
            session=_session(),
            cycle=cycle,
            store=store,
            symbols=["NVDA"],
            exchanges={"NVDA": "ND"},
            reconcile=reconcile,
        )
        await asyncio.sleep(0)
        status = monitor.status()
        await monitor.stop()
        return status

    status = asyncio.run(scenario())
    reservation = CapitalAllocationStore(
        tmp_path / "allocation.sqlite3"
    ).list_reservations(cycle.id)[0]

    assert reservation.status == "filled"
    assert reservation.filled_quantity == 1
    assert reconciled == 1
    assert status["connected"] is True
    assert status["updatedCount"] == 1
    assert status["lastReconcileError"] is None


def test_monitor_reports_stream_failure_without_sensitive_error(
    monkeypatch,
    tmp_path,
):
    _enable_monitor(monkeypatch)
    store, cycle = _submitted_allocation(tmp_path)

    async def failed_stream(session, symbols, exchanges):
        raise OSError("TOKEN-MUST-NOT-LEAK")
        yield

    monkeypatch.setattr(
        monitor_module,
        "kiwoom_order_state_stream",
        failed_stream,
    )
    monitor = monitor_module.KiwoomOrderStateMonitor()

    async def scenario():
        await monitor.ensure(
            session=_session(),
            cycle=cycle,
            store=store,
            symbols=["NVDA"],
            exchanges={"NVDA": "ND"},
        )
        await asyncio.sleep(0)
        status = monitor.status()
        await monitor.stop()
        return status

    status = asyncio.run(scenario())

    assert status["connected"] is False
    assert status["lastError"] == "OSError"
    assert "TOKEN-MUST-NOT-LEAK" not in str(status)


def test_monitor_sanitizes_rest_reconcile_failure(
    monkeypatch,
    tmp_path,
):
    _enable_monitor(monkeypatch)
    store, cycle = _submitted_allocation(tmp_path)
    events = tuple(map_us_order_realtime_payload(_full_fill_payload()))

    async def fake_stream(session, symbols, exchanges):
        yield monitor_module.OrderStateStreamBatch(
            connected=True,
            events=events,
            received_at="2026-07-30T12:00:00+00:00",
        )
        await asyncio.sleep(60)

    async def failed_reconcile():
        raise RuntimeError("TOKEN-MUST-NOT-LEAK")

    monkeypatch.setattr(
        monitor_module,
        "kiwoom_order_state_stream",
        fake_stream,
    )
    monitor = monitor_module.KiwoomOrderStateMonitor()

    async def scenario():
        await monitor.ensure(
            session=_session(),
            cycle=cycle,
            store=store,
            symbols=["NVDA"],
            exchanges={"NVDA": "ND"},
            reconcile=failed_reconcile,
        )
        await asyncio.sleep(0)
        status = monitor.status()
        await monitor.stop()
        return status

    status = asyncio.run(scenario())

    assert status["lastReconcileError"] == "RuntimeError"
    assert "TOKEN-MUST-NOT-LEAK" not in str(status)


def test_order_service_wires_submitted_reservations_to_rest_reconcile(
    monkeypatch,
    tmp_path,
):
    from app.services import us_order_service as order_module

    db_path = tmp_path / "allocation.sqlite3"
    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(db_path))
    session = _session()
    account_scope = order_module._allocation_account_scope(
        session.mode,
        session.safe_account_label,
    )
    store = CapitalAllocationStore(db_path)
    cycle = store.ensure_cycle(
        account_scope=account_scope,
        market_date=order_module.market_time_context().us_market_date,
        orderable_cash=4_000,
    )
    decision = evaluate_capital_allocation(
        state=CapitalAllocationState(
            cycle_capital=4_000,
            orderable_cash=4_000,
        ),
        symbol="NVDA",
        reference_price=100,
        max_quantity=1,
    )
    reservation = store.reserve(
        cycle=cycle,
        decision=decision,
        strategy="strategy-a",
        exchange="ND",
        reference_price=100,
    )
    store.mark_submitted(reservation.id, "order-a")
    captured: dict[str, object] = {}
    reconciled = 0

    async def fake_ensure(**kwargs):
        captured.update(kwargs)
        await kwargs["reconcile"]()

    async def fake_reconcile(
        *,
        session_mode,
        safe_account_label,
        force=False,
    ):
        nonlocal reconciled
        reconciled += 1
        assert session_mode == "live"
        assert safe_account_label == session.safe_account_label
        assert force is True
        return 0

    monkeypatch.setattr(
        order_module,
        "get_active_kiwoom_session",
        lambda: session,
    )
    monkeypatch.setattr(
        order_module,
        "_reconcile_submitted_allocation_reservations",
        fake_reconcile,
    )
    monkeypatch.setattr(
        order_module.kiwoom_order_state_monitor,
        "ensure",
        fake_ensure,
    )
    monkeypatch.setattr(
        order_module.kiwoom_order_state_monitor,
        "status",
        lambda: {
            "enabled": True,
            "running": True,
            "connected": True,
            "symbols": ["NVDA"],
        },
    )

    status = asyncio.run(
        order_module.us_order_service.ensure_order_state_monitor()
    )

    assert captured["symbols"] == ["NVDA"]
    assert captured["exchanges"] == {"NVDA": "ND"}
    assert captured["cycle"].id == cycle.id
    assert reconciled == 1
    assert status["connected"] is True


def test_order_service_exposes_safe_monitor_diagnostics(monkeypatch):
    from app.services import us_order_service as order_module

    monkeypatch.setattr(
        order_module.kiwoom_order_state_monitor,
        "status",
        lambda: {
            "enabled": True,
            "running": True,
            "connected": False,
            "symbols": ["NVDA", "MSFT"],
            "channels": ["F4", "F5"],
            "lastEventAt": "2026-07-30T12:00:00+00:00",
            "lastError": "ConnectionError",
            "lastReconcileError": None,
            "updatedCount": 3,
            "duplicateCount": 1,
        },
    )

    status = asyncio.run(
        order_module.us_order_service.get_order_state_monitor_status()
    )
    payload = status.model_dump()

    assert payload["enabled"] is True
    assert payload["running"] is True
    assert payload["connected"] is False
    assert payload["monitoredSymbolCount"] == 2
    assert payload["channels"] == ["F4", "F5"]
    assert payload["lastError"] == "ConnectionError"
    assert payload["updatedCount"] == 3
    assert payload["duplicateCount"] == 1
    assert "symbols" not in payload
    assert "token" not in str(payload).lower()
    assert "account" not in str(payload).lower()


def test_order_service_redacts_sensitive_monitor_error(monkeypatch):
    from app.services import us_order_service as order_module

    monkeypatch.setattr(
        order_module.kiwoom_order_state_monitor,
        "status",
        lambda: {
            "enabled": True,
            "running": False,
            "connected": False,
            "symbols": [],
            "channels": ["F4", "F5"],
            "lastError": "token leaked in error",
            "lastReconcileError": "account lookup failed",
            "updatedCount": "invalid",
            "duplicateCount": -1,
        },
    )

    status = asyncio.run(
        order_module.us_order_service.get_order_state_monitor_status()
    )

    assert status.lastError == "REDACTED"
    assert status.lastReconcileError == "REDACTED"
    assert status.updatedCount == 0
    assert status.duplicateCount == 0


def test_order_state_preflight_reports_safe_blockers(
    monkeypatch,
    tmp_path,
):
    from app.services import us_order_service as order_module

    monkeypatch.delenv(
        "KIWOOM_US_ORDER_STATE_MONITOR_ENABLED",
        raising=False,
    )
    monkeypatch.delenv(
        "KIWOOM_US_ORDER_STATE_MONITOR_CONFIRM",
        raising=False,
    )
    monkeypatch.setenv(
        "KIWOOM_US_ORDER_RUNTIME_LOCK_FILE",
        str(tmp_path / "missing.lock"),
    )
    monkeypatch.setattr(
        order_module,
        "get_active_kiwoom_session",
        lambda: None,
    )

    status = asyncio.run(
        order_module.us_order_service.get_order_state_monitor_preflight()
    )

    assert status.readyForObservation is False
    assert status.observationState == "blocked"
    assert status.requiredActionCode == "RESTORE_SESSION"
    assert status.sessionPresent is False
    assert status.runtimeOrderLocked is False
    assert status.submittedReservationCount == 0
    assert status.blockerReasons == [
        "ORDER_STATE_MONITOR_DISABLED",
        "KIWOOM_SESSION_REQUIRED",
        "RUNTIME_ORDER_LOCK_REQUIRED",
        "NO_SUBMITTED_ORDERS",
    ]


def test_order_state_preflight_reports_no_target_for_valid_session(
    monkeypatch,
    tmp_path,
):
    from app.services import us_order_service as order_module

    monkeypatch.delenv("KIWOOM_US_ORDER_STATE_MONITOR_ENABLED", raising=False)
    lock_path = tmp_path / "runtime.lock"
    lock_path.touch()
    monkeypatch.setenv("KIWOOM_US_ORDER_RUNTIME_LOCK_FILE", str(lock_path))
    monkeypatch.setattr(order_module, "get_active_kiwoom_session", _session)
    monkeypatch.setattr(
        order_module,
        "get_engine_settings",
        lambda: SimpleNamespace(db_path=tmp_path / "no-target.sqlite3"),
    )

    status = asyncio.run(
        order_module.us_order_service.get_order_state_monitor_preflight()
    )

    assert status.readyForObservation is False
    assert status.observationState == "no_target"
    assert status.requiredActionCode == "WAIT_FOR_SUBMITTED_ORDER"
    assert status.sessionValid is True
    assert status.submittedReservationCount == 0


def test_order_state_preflight_is_ready_without_network_call(
    monkeypatch,
    tmp_path,
):
    from app.services import us_order_service as order_module

    _enable_monitor(monkeypatch)
    lock_path = tmp_path / "runtime.lock"
    lock_path.touch()
    monkeypatch.setenv(
        "KIWOOM_US_ORDER_RUNTIME_LOCK_FILE",
        str(lock_path),
    )
    session = _session()
    monkeypatch.setattr(
        order_module,
        "get_active_kiwoom_session",
        lambda: session,
    )
    db_path = tmp_path / "preflight.sqlite3"
    monkeypatch.setattr(
        order_module,
        "get_engine_settings",
        lambda: SimpleNamespace(db_path=db_path),
    )
    store = CapitalAllocationStore(db_path)
    cycle = store.ensure_cycle(
        account_scope=order_module._allocation_account_scope(
            session.mode,
            session.safe_account_label,
        ),
        market_date=order_module.market_time_context().us_market_date,
        orderable_cash=4_000,
    )
    decision = evaluate_capital_allocation(
        state=CapitalAllocationState(
            cycle_capital=4_000,
            orderable_cash=4_000,
        ),
        symbol="NVDA",
        reference_price=100,
        max_quantity=1,
    )
    reservation = store.reserve(
        cycle=cycle,
        decision=decision,
        strategy="strategy-a",
        exchange="ND",
        reference_price=100,
    )
    store.mark_submitted(reservation.id, "order-a")

    async def connection_must_not_start(**kwargs):
        raise AssertionError("preflight must not start WebSocket")

    monkeypatch.setattr(
        order_module.kiwoom_order_state_monitor,
        "ensure",
        connection_must_not_start,
    )

    status = asyncio.run(
        order_module.us_order_service.get_order_state_monitor_preflight()
    )
    payload = status.model_dump()

    assert status.readyForObservation is True
    assert status.observationState == "ready"
    assert status.requiredActionCode == "START_OBSERVATION"
    assert status.monitorConfigured is True
    assert status.sessionValid is True
    assert status.runtimeOrderLocked is True
    assert status.submittedReservationCount == 1
    assert status.eligibleSymbolCount == 1
    assert status.blockerReasons == []
    assert "NVDA" not in str(payload)
    assert "order-a" not in str(payload)
    assert "account" not in str(payload).lower()
    assert "token" not in str(payload).lower()


def test_login_resume_reuses_monitor_lifecycle(monkeypatch):
    from app.api import auth as auth_api
    from app.services import us_order_service as order_module

    calls = 0

    async def ensure_monitor():
        nonlocal calls
        calls += 1
        return {"running": False}

    monkeypatch.setattr(
        order_module.us_order_service,
        "ensure_order_state_monitor",
        ensure_monitor,
    )

    asyncio.run(auth_api._resume_order_state_monitor())

    assert calls == 1


def test_login_resume_failure_does_not_break_login(monkeypatch):
    from app.api import auth as auth_api
    from app.services import us_order_service as order_module

    async def fail_monitor():
        raise RuntimeError("safe fixture failure")

    monkeypatch.setattr(
        order_module.us_order_service,
        "ensure_order_state_monitor",
        fail_monitor,
    )

    asyncio.run(auth_api._resume_order_state_monitor())


def test_auto_entry_blocks_while_configured_order_monitor_is_disconnected(
    monkeypatch,
):
    from app.services import us_order_service as order_module

    session = _session()

    async def no_reconciliation(**kwargs):
        return 0

    async def disconnected_status():
        return {
            "enabled": True,
            "running": True,
            "connected": False,
            "symbols": ["NVDA"],
        }

    monkeypatch.setattr(
        order_module,
        "_auto_trade_runtime_enabled",
        True,
    )
    monkeypatch.setattr(
        order_module,
        "get_active_kiwoom_session",
        lambda: session,
    )
    monkeypatch.setattr(
        order_module,
        "_reconcile_submitted_allocation_reservations",
        no_reconciliation,
    )
    monkeypatch.setattr(
        order_module.us_order_service,
        "ensure_order_state_monitor",
        disconnected_status,
    )

    result = asyncio.run(
        order_module.us_order_service.run_auto_entry_tick()
    )

    assert result.action == "waiting"
    assert result.blockedReasons == [
        "ORDER_STATE_MONITOR_UNAVAILABLE"
    ]


def test_auto_entry_blocks_after_rest_reconciliation_failure(
    monkeypatch,
):
    from app.services import us_order_service as order_module

    async def no_reconciliation(**kwargs):
        return 0

    async def failed_status():
        return {
            "enabled": True,
            "running": True,
            "connected": True,
            "symbols": ["NVDA"],
            "lastReconcileError": "RuntimeError",
        }

    monkeypatch.setattr(
        order_module,
        "_auto_trade_runtime_enabled",
        True,
    )
    monkeypatch.setattr(
        order_module,
        "get_active_kiwoom_session",
        _session,
    )
    monkeypatch.setattr(
        order_module,
        "_reconcile_submitted_allocation_reservations",
        no_reconciliation,
    )
    monkeypatch.setattr(
        order_module.us_order_service,
        "ensure_order_state_monitor",
        failed_status,
    )

    result = asyncio.run(
        order_module.us_order_service.run_auto_entry_tick()
    )

    assert result.action == "waiting"
    assert result.blockedReasons == [
        "ORDER_STATE_RECONCILIATION_FAILED"
    ]


def test_auto_entry_blocks_while_submitted_order_is_unconfirmed(
    monkeypatch,
):
    from app.services import us_order_service as order_module

    async def no_reconciliation(**kwargs):
        return 0

    async def monitor_disabled():
        return {
            "enabled": False,
            "running": False,
            "connected": False,
            "symbols": [],
        }

    async def candidate_scan_must_not_start(*args, **kwargs):
        raise AssertionError("candidate scan must wait for order state")

    monkeypatch.setattr(
        order_module,
        "_auto_trade_runtime_enabled",
        True,
    )
    monkeypatch.setattr(
        order_module,
        "get_active_kiwoom_session",
        _session,
    )
    monkeypatch.setattr(
        order_module,
        "_reconcile_submitted_allocation_reservations",
        no_reconciliation,
    )
    monkeypatch.setattr(
        order_module.us_order_service,
        "ensure_order_state_monitor",
        monitor_disabled,
    )
    monkeypatch.setattr(
        order_module,
        "_submitted_order_state_blocker",
        lambda **kwargs: "ORDER_STATE_PENDING_CONFIRMATION",
    )
    monkeypatch.setattr(
        order_module,
        "_auto_entry_candidate_plans",
        candidate_scan_must_not_start,
    )

    result = asyncio.run(
        order_module.us_order_service.run_auto_entry_tick()
    )

    assert result.action == "waiting"
    assert result.blockedReasons == [
        "ORDER_STATE_PENDING_CONFIRMATION"
    ]
