from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services import realtime_quote_service as quote_module
from app.services import us_order_service as order_module
from app.services.kiwoom_session import KiwoomSession
from trading_engine.providers.kiwoom_us.schemas import UsReadOnlyTrResponse


def _session() -> KiwoomSession:
    return KiwoomSession(
        session_token="safe-session",
        mode="live",
        account_no="masked",
        base_url="https://api.kiwoom.com",
        access_token="not-logged",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )


def test_quote_reconnect_delay_is_bounded() -> None:
    assert [
        quote_module.quote_reconnect_delay(index)
        for index in (0, 1, 2, 3, 4, 5, 20)
    ] == [1, 2, 4, 8, 16, 30, 30]


def test_quote_stream_error_types_are_safe_and_actionable() -> None:
    class ConnectionClosedError(Exception):
        pass

    assert quote_module._safe_websocket_error_type(asyncio.TimeoutError()) == "KIWOOM_WEBSOCKET_TIMEOUT"
    assert quote_module._safe_websocket_error_type(OSError("token=must-not-leak")) == "KIWOOM_WEBSOCKET_CONNECTION_ERROR"
    assert quote_module._safe_websocket_error_type(ConnectionClosedError("secret payload")) == "KIWOOM_WEBSOCKET_CONNECTION_CLOSED"


def test_quote_monitor_reconnects_and_resubscribes(monkeypatch) -> None:
    attempts = 0
    subscriptions: list[tuple[tuple[str, ...], dict[str, str]]] = []
    delays: list[float] = []
    keep_connected = asyncio.Event()

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    async def flaky_stream(session, symbols, exchanges=None):
        nonlocal attempts
        attempts += 1
        subscriptions.append((tuple(symbols), dict(exchanges or {})))
        yield {
            "type": "STATUS",
            "status": "CONNECTED",
            "timestamp": f"2026-07-31T12:00:0{attempts}+00:00",
        }
        if attempts == 1:
            yield {
                "type": "ERROR",
                "errorType": "KIWOOM_WEBSOCKET_UNAVAILABLE",
                "timestamp": "2026-07-31T12:00:01+00:00",
            }
            return
        await keep_connected.wait()

    monkeypatch.setattr(quote_module, "kiwoom_quote_stream", flaky_stream)
    monitor = quote_module.KiwoomQuoteMonitor(sleep=fake_sleep)

    async def scenario():
        await monitor.ensure(_session(), ["NVDA", "MSFT"], {"NVDA": "ND", "MSFT": "NY"})
        for _ in range(30):
            if attempts >= 2 and monitor.status()["connected"]:
                break
            await asyncio.sleep(0)
        status = monitor.status()
        await monitor.stop()
        return status

    status = asyncio.run(scenario())

    assert attempts == 2
    assert subscriptions == [
        (("NVDA", "MSFT"), {"NVDA": "ND", "MSFT": "NY"}),
        (("NVDA", "MSFT"), {"NVDA": "ND", "MSFT": "NY"}),
    ]
    assert delays == [1]
    assert status["connected"] is True
    assert status["reconnectCount"] == 1
    assert status["nextRetrySeconds"] is None


def test_quote_monitor_union_prioritizes_requested_symbols(monkeypatch) -> None:
    monitor = quote_module.KiwoomQuoteMonitor()
    monitor._symbols = tuple(f"OLD{index}" for index in range(20))
    monitor._exchanges = {symbol: "ND" for symbol in monitor._symbols}
    captured: dict[str, object] = {}

    async def fake_ensure(session, symbols, exchanges=None):
        captured["symbols"] = symbols
        captured["exchanges"] = exchanges

    monkeypatch.setattr(monitor, "ensure", fake_ensure)

    asyncio.run(monitor.ensure_union(_session(), ["IBM", "NVDA"], {"IBM": "NY", "NVDA": "ND"}))

    assert captured["symbols"][:2] == ["IBM", "NVDA"]
    assert len(captured["symbols"]) == 20
    assert captured["exchanges"]["IBM"] == "NY"


def test_latest_quote_ignores_stale_realtime_and_uses_readonly_rest(monkeypatch) -> None:
    stale_at = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
    monkeypatch.setattr(
        order_module.realtime_window_store,
        "summary",
        lambda symbol: SimpleNamespace(latestPrice=10.0, lastEventAt=stale_at),
    )

    async def fake_execute(tr_id, body):
        assert tr_id == "usa10100"
        return UsReadOnlyTrResponse(
            tr_id="usa10100",
            return_code="0",
            return_msg="OK",
            data={"cur_prc": "11.2500"},
            unknown_fields={},
        )

    monkeypatch.setattr(order_module.us_account_service, "_execute", fake_execute)
    monkeypatch.setattr(order_module, "_record_rest_poll_tick", lambda *args, **kwargs: None)

    price, source = asyncio.run(order_module._latest_quote_price("NVDA", "ND"))

    assert price == 11.25
    assert source == "usa10100"


def test_realtime_freshness_rejects_delayed_source_event() -> None:
    summary = SimpleNamespace(
        lastEventAt=datetime.now(timezone.utc).isoformat(),
        receiveDelayMs=11_000,
    )

    assert quote_module.realtime_summary_is_fresh(summary, max_age_seconds=10) is False
