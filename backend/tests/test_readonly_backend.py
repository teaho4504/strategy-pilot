from __future__ import annotations

import asyncio
import os
import ssl
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core import auth as auth_module
from app.core.auth import AuthenticatedUser, SupabaseAuthError, _email_from_claims, _get_jwk_client
from app.core.config import get_settings
from app.core.security import reset_security_state
from app.main import app
from app.services import kiwoom_client as kiwoom_module
from app.services.account_service import (
    map_account_response,
    map_cash_response,
    map_holdings_response,
    map_performance_response,
    map_portfolio_response,
    parse_float,
    parse_int,
)
from app.services.kiwoom_client import KiwoomConfigurationError, KiwoomResponse, TR_SPECS
from app.services.kiwoom_session import (
    KiwoomSession,
    kiwoom_session_manager,
    set_active_kiwoom_session,
)
from app.services.us_order_state_monitor import kiwoom_order_state_monitor
from app.services.realtime_quote_service import (
    RealtimeWindowStore,
    _receive_delay_ms,
    build_kiwoom_quote_reg_packet,
    normalize_kiwoom_realtime_message,
    realtime_window_store,
    safe_quote_symbols,
)
from app.services.realtime_event_store import realtime_db_window_metrics, realtime_event_counts
from app.services.token_manager import TOKEN_PATH, TOKEN_REQUEST_BODY_KEYS, TokenManager, TokenManagerError, token_manager
from app.services.us_condition_service import UsConditionSearchError, _send_condition_request
from scripts.verify_live_readonly import (
    CONFIRM_VALUE,
    LiveVerifyBlocked,
    load_backend_env_file,
    print_token_request_diagnostics,
    sanitize_return_msg,
    print_safe_failure,
    print_safe_step_result,
    validate_live_verify_environment,
)


@pytest.fixture(autouse=True)
def reset_settings_and_token(monkeypatch, tmp_path):
    for key in (
        "KIWOOM_MODE",
        "KIWOOM_APP_KEY",
        "KIWOOM_SECRET_KEY",
        "KIWOOM_APP_SECRET",
        "KIWOOM_ACCOUNT_NO",
        "KIWOOM_BASE_URL",
        "KIWOOM_TOKEN_URL",
        "KIWOOM_READ_ONLY",
        "KIWOOM_ENABLE_ORDER",
        "SUPABASE_URL",
        "SUPABASE_JWT_ISSUER",
        "SUPABASE_JWT_AUDIENCE",
        "ALLOWED_USER_EMAILS",
        "DASHBOARD_ACCESS_PIN",
        "BACKEND_ALLOWED_CLIENT_IPS",
        "BACKEND_TRUST_PROXY_HEADERS",
        "BACKEND_AUTH_RATE_LIMIT",
        "BACKEND_ORDER_RATE_LIMIT",
        "KIWOOM_US_CREDENTIAL_SOURCE",
        "KIWOOM_US_PROFILE",
        "KIWOOM_US_READ_ONLY",
        "KIWOOM_US_ENABLE_ORDER",
        "KIWOOM_US_LIVE_PROVIDER",
        "KIWOOM_US_HTTP_SENDER_ENABLED",
        "KIWOOM_US_HTTP_SENDER_CONFIRM",
        "KIWOOM_US_ACCESS_TOKEN",
        "KIWOOM_US_ORDER_CONFIRM",
        "KIWOOM_US_LIVE_ORDER_UNLOCK",
        "KIWOOM_US_AUTOTRADE_RUNNER_ENABLED",
        "KIWOOM_US_AUTOTRADE_RUNNER_INTERVAL_SECONDS",
        "KIWOOM_US_PREMARKET_ENTRY_ENABLED",
        "KIWOOM_US_CONDITION_SEQ",
        "KIWOOM_US_PULLBACK_MIN_PASSED_CRITERIA",
        "KIWOOM_US_ALLOWED_SYMBOLS",
        "KIWOOM_US_MAX_ORDER_QUANTITY",
        "KIWOOM_US_MAX_ORDER_NOTIONAL",
        "KIWOOM_US_CAPITAL_USAGE_PCT",
        "KIWOOM_US_ORDER_RUNTIME_LOCK_FILE",
        "KIWOOM_US_ORDER_RECONCILE_INTERVAL_SECONDS",
        "KIWOOM_US_ORDER_CONFIRMATION_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(tmp_path / "realtime-events.sqlite3"))
    monkeypatch.setenv("KIWOOM_US_ORDER_RUNTIME_LOCK_FILE", str(tmp_path / "us-order-runtime.lock"))
    get_settings.cache_clear()
    token_manager._access_token = None
    token_manager._expires_at = None
    kiwoom_session_manager._sessions.clear()
    kiwoom_session_manager._latest_session_token = None
    set_active_kiwoom_session(None)
    realtime_window_store.clear()
    from app.services import us_order_service as order_module
    from app.services.market_ranking_service import market_ranking_service
    from app.services.us_condition_service import us_condition_service

    order_module._auto_trade_strategy_condition_errors.clear()
    us_condition_service.reset_for_tests()
    market_ranking_service.clear_pullback_plan_cache()
    reset_security_state()
    yield
    get_settings.cache_clear()
    token_manager._access_token = None
    token_manager._expires_at = None
    kiwoom_session_manager._sessions.clear()
    kiwoom_session_manager._latest_session_token = None
    set_active_kiwoom_session(None)
    realtime_window_store.clear()
    order_module._auto_trade_strategy_condition_errors.clear()
    us_condition_service.reset_for_tests()
    market_ranking_service.clear_pullback_plan_cache()
    reset_security_state()


def _patch_us_condition_matches(monkeypatch, *codes: str) -> None:
    from app.schemas.market import UsConditionItem, UsConditionSearchMatch, UsConditionSearchResponse
    from app.services.market_ranking_service import us_condition_service

    async def fake_condition_search(seq: str | None = None):
        return UsConditionSearchResponse(
            source="fixture",
            listTrId="usa20280",
            searchTrId="usa20281",
            realtimeTrId="usa20290",
            clearTrId="usa20291",
            updatedAt="2026-07-15T12:00:00+00:00",
            conditions=[UsConditionItem(seq=seq or "001", name="US_COMMON_LIQUID_LONG")],
            selectedSeq=seq or "001",
            selectedName="US_COMMON_LIQUID_LONG",
            matches=[UsConditionSearchMatch(code=code) for code in codes],
            schemaKeys=["data", "trnm"],
        )

    monkeypatch.setattr(us_condition_service, "get_condition_search", fake_condition_search)


def test_live_mode_is_default_and_health_loads():
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "live"
    assert body["kiwoom"]["readOnly"] is True
    assert body["kiwoom"]["orderEnabled"] is False
    for path in ("/api/kiwoom/status", "/"):
        assert client.get(path).status_code == 200


def test_protected_account_api_requires_authentication():
    response = TestClient(app).get("/api/accounts")

    assert response.status_code == 401


def test_basic_authorization_header_returns_401():
    response = TestClient(app).get("/api/accounts", headers={"Authorization": "Basic abc"})

    assert response.status_code == 401


def test_empty_bearer_authorization_header_returns_401():
    response = TestClient(app).get("/api/accounts", headers={"Authorization": "Bearer"})

    assert response.status_code == 401


def test_removed_mock_watchlist_returns_not_found():
    response = TestClient(app).get("/api/market/watchlist")

    assert response.status_code == 404


def test_realtime_exchange_map_accepts_only_safe_us_pairs():
    from app.api.market import _safe_exchange_map

    assert _safe_exchange_map("ibm:ny,NVDA:ND,bad:XX,../x:NA") == {
        "IBM": "NY",
        "NVDA": "ND",
    }


def test_us_quote_endpoint_maps_readonly_usa10100_response(monkeypatch):
    from app.api import market as market_module
    from app.schemas.us_account import UsReadOnlyTrSummary

    monkeypatch.setenv("ALLOWED_USER_EMAILS", "allowed@example.com")
    get_settings.cache_clear()

    def verify(token: str):
        return AuthenticatedUser(email="allowed@example.com", subject="user-id")

    async def fake_quote(exchange: str, symbol: str) -> UsReadOnlyTrSummary:
        assert (exchange, symbol) == ("ND", "NVDA")
        return UsReadOnlyTrSummary(
            trId="usa10100",
            returnCode="0",
            returnMessage="OK",
            schemaKeys=["cur_prc", "flu_rt", "acc_trde_qty", "stk_nm"],
            data={
                "cur_prc": "123.4500",
                "flu_rt": "+2.10",
                "acc_trde_qty": "1,234,567",
                "stk_nm": "NVIDIA",
            },
            source="kiwoom-us-rest",
            updatedAt="2026-08-12T00:00:00+00:00",
        )

    monkeypatch.setattr(auth_module, "verify_supabase_jwt", verify)
    monkeypatch.setattr(market_module.us_account_service, "get_current_quote", fake_quote)

    response = TestClient(app).get(
        "/api/market/us/quote?symbol=nvda&exchange=nd",
        headers={"Authorization": "Bearer valid-token"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "trId": "usa10100",
        "symbol": "NVDA",
        "exchange": "ND",
        "name": "NVIDIA",
        "price": 123.45,
        "changeRate": 2.1,
        "volume": 1234567,
        "source": "kiwoom-us-security-info",
        "updatedAt": "2026-08-12T00:00:00+00:00",
    }


def test_protected_us_account_api_requires_authentication():
    response = TestClient(app).get("/api/us/account/cash")

    assert response.status_code == 401


def test_protected_us_order_api_requires_authentication():
    response = TestClient(app).post(
        "/api/us/orders",
        json={
            "side": "buy",
            "exchange": "ND",
            "symbol": "NVDA",
            "quantity": 1,
            "orderPrice": "",
            "tradeType": "03",
            "confirmText": "I_UNDERSTAND_LIVE_US_ORDER",
        },
    )

    assert response.status_code == 401


def test_kiwoom_profile_auth_requires_dashboard_pin(monkeypatch):
    monkeypatch.setenv("DASHBOARD_ACCESS_PIN", "123456")
    get_settings.cache_clear()
    client = TestClient(app)

    missing = client.get("/api/auth/kiwoom/profiles")
    wrong = client.get("/api/auth/kiwoom/profiles", headers={"X-Dashboard-Pin": "wrong"})

    assert missing.status_code == 403
    assert wrong.status_code == 403


def test_kiwoom_profile_auth_is_disabled_when_dashboard_pin_is_not_configured():
    response = TestClient(app).get("/api/auth/kiwoom/profiles", headers={"X-Dashboard-Pin": "123456"})

    assert response.status_code == 503


def test_kiwoom_logout_requires_authentication():
    response = TestClient(app).post("/api/auth/kiwoom/logout")

    assert response.status_code == 401


def test_kiwoom_logout_revokes_session_and_stops_order_monitor(monkeypatch):
    session = KiwoomSession(
        session_token="local-session",
        mode="live",
        account_no="configured",
        base_url="https://api.kiwoom.com",
        access_token="TOKEN-MUST-NOT-LEAK",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    kiwoom_session_manager._sessions[session.session_token] = session
    kiwoom_session_manager._latest_session_token = session.session_token
    stop = AsyncMock()
    monkeypatch.setattr(kiwoom_order_state_monitor, "stop", stop)

    response = TestClient(app).post(
        "/api/auth/kiwoom/logout",
        headers={"Authorization": "Bearer local-session"},
    )

    assert response.status_code == 204
    assert kiwoom_session_manager.get_session("local-session") is None
    stop.assert_awaited_once()


def test_backend_ip_allowlist_blocks_unknown_client(monkeypatch):
    monkeypatch.setenv("BACKEND_ALLOWED_CLIENT_IPS", "203.0.113.10")
    get_settings.cache_clear()

    response = TestClient(app).get("/api/health")

    assert response.status_code == 403


def test_backend_ip_allowlist_allows_configured_client(monkeypatch):
    monkeypatch.setenv("BACKEND_ALLOWED_CLIENT_IPS", "testclient")
    get_settings.cache_clear()

    response = TestClient(app).get("/api/health")

    assert response.status_code == 200


def test_backend_ip_allowlist_supports_cidr_when_proxy_headers_are_trusted(monkeypatch):
    monkeypatch.setenv("BACKEND_ALLOWED_CLIENT_IPS", "27.35.61.0/24")
    monkeypatch.setenv("BACKEND_TRUST_PROXY_HEADERS", "true")
    get_settings.cache_clear()

    allowed = TestClient(app).get("/api/health", headers={"X-Forwarded-For": "27.35.61.240"})
    blocked = TestClient(app).get("/api/health", headers={"X-Forwarded-For": "198.51.100.10"})

    assert allowed.status_code == 200
    assert blocked.status_code == 403


def test_auth_rate_limit_blocks_repeated_profile_requests(monkeypatch):
    monkeypatch.setenv("DASHBOARD_ACCESS_PIN", "123456")
    monkeypatch.setenv("BACKEND_AUTH_RATE_LIMIT", "2/60")
    get_settings.cache_clear()
    client = TestClient(app)

    assert client.get("/api/auth/kiwoom/profiles", headers={"X-Dashboard-Pin": "wrong"}).status_code == 403
    assert client.get("/api/auth/kiwoom/profiles", headers={"X-Dashboard-Pin": "wrong"}).status_code == 403
    blocked = client.get("/api/auth/kiwoom/profiles", headers={"X-Dashboard-Pin": "wrong"})

    assert blocked.status_code == 429


def test_us_order_api_is_disabled_by_default(monkeypatch):
    monkeypatch.setenv("ALLOWED_USER_EMAILS", "allowed@example.com")
    get_settings.cache_clear()

    def verify(token: str):
        return AuthenticatedUser(email="allowed@example.com", subject="user-id")

    monkeypatch.setattr(auth_module, "verify_supabase_jwt", verify)

    response = TestClient(app).post(
        "/api/us/orders",
        headers={"Authorization": "Bearer valid-token"},
        json={
            "side": "buy",
            "exchange": "ND",
            "symbol": "NVDA",
            "quantity": 1,
            "orderPrice": "",
            "tradeType": "03",
            "confirmText": "I_UNDERSTAND_LIVE_US_ORDER",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "LIVE_ORDER_EXECUTION_NOT_IMPLEMENTED"


def test_us_cash_and_valuation_responses_include_normalized_display_fields(monkeypatch):
    monkeypatch.setenv("ALLOWED_USER_EMAILS", "allowed@example.com")
    get_settings.cache_clear()

    def verify(token: str):
        return AuthenticatedUser(email="allowed@example.com", subject="user-id")

    monkeypatch.setattr(auth_module, "verify_supabase_jwt", verify)
    client = TestClient(app)

    cash_response = client.get("/api/us/account/cash", headers={"Authorization": "Bearer valid-token"})
    valuation_response = client.get("/api/us/account/valuation", headers={"Authorization": "Bearer valid-token"})

    assert cash_response.status_code == 400
    assert valuation_response.status_code == 400
    return
    cash = cash_response.json()
    valuation = valuation_response.json()
    assert cash["trId"] == "ust21110"
    assert {"cashAmount", "orderableAmount", "cashField", "orderableField"}.issubset(cash["normalized"])
    assert valuation["trId"] == "ust21120"
    assert {"valuationAmount", "profitLossAmount", "valuationField", "profitLossField"}.issubset(valuation["normalized"])


def test_us_holdings_response_includes_ust21070_normalized_display_fields(monkeypatch):
    monkeypatch.setenv("ALLOWED_USER_EMAILS", "allowed@example.com")
    get_settings.cache_clear()

    def verify(token: str):
        return AuthenticatedUser(email="allowed@example.com", subject="user-id")

    monkeypatch.setattr(auth_module, "verify_supabase_jwt", verify)

    response = TestClient(app).get("/api/us/account/holdings", headers={"Authorization": "Bearer valid-token"})

    assert response.status_code == 400
    return
    body = response.json()
    assert body["trId"] == "ust21070"
    assert body["normalized"]["holdingRows"] == 1
    assert body["normalized"]["sellableRows"] == 1
    assert body["normalized"]["totalSellableQuantity"] == 1
    assert body["normalized"]["quantityField"] == "sell_alowq"
    assert body["normalized"]["exchangeField"] == "stex_nm"
    assert body["normalized"]["priceField"] == "now_pric"


def test_us_order_status_exposes_readiness_checklist(monkeypatch):
    monkeypatch.setenv("ALLOWED_USER_EMAILS", "allowed@example.com")
    monkeypatch.setenv("KIWOOM_READ_ONLY", "false")
    monkeypatch.setenv("KIWOOM_US_ENABLE_ORDER", "true")
    monkeypatch.setenv("KIWOOM_US_ORDER_CONFIRM", "I_UNDERSTAND_LIVE_US_ORDER")
    monkeypatch.setenv("KIWOOM_US_ALLOWED_SYMBOLS", "NVDA")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_QUANTITY", "1")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_NOTIONAL", "500")
    monkeypatch.setenv("KIWOOM_US_CAPITAL_USAGE_PCT", "50")
    get_settings.cache_clear()

    def verify(token: str):
        return AuthenticatedUser(email="allowed@example.com", subject="user-id")

    monkeypatch.setattr(auth_module, "verify_supabase_jwt", verify)

    response = TestClient(app).get("/api/us/orders/status", headers={"Authorization": "Bearer valid-token"})

    assert response.status_code == 200
    body = response.json()
    checklist = {item["key"]: item for item in body["readinessChecklist"]}
    assert list(checklist) == ["final_order_boundary"]
    assert checklist["final_order_boundary"]["passed"] is False
    assert body["capitalUsagePct"] == 50
    assert body["sessionMode"] is None
    assert body["accountLabel"] is None
    assert body["blockedReasons"] == ["LIVE_ORDER_EXECUTION_NOT_IMPLEMENTED"]


def test_us_order_runtime_lock_blocks_policy_and_sender(monkeypatch, tmp_path):
    from datetime import timedelta
    from types import SimpleNamespace

    from app.schemas.us_order import UsOrderRequest
    from app.services.kiwoom_session import KiwoomSession, set_active_kiwoom_session
    from app.services import us_order_service as order_module

    monkeypatch.setenv("ALLOWED_USER_EMAILS", "allowed@example.com")
    monkeypatch.setenv("KIWOOM_READ_ONLY", "false")
    monkeypatch.setenv("KIWOOM_US_ENABLE_ORDER", "true")
    monkeypatch.setenv("KIWOOM_US_ORDER_CONFIRM", "I_UNDERSTAND_LIVE_US_ORDER")
    monkeypatch.setenv("KIWOOM_US_LIVE_ORDER_UNLOCK", "I_ACCEPT_REAL_US_ORDER_RISK")
    monkeypatch.setenv("KIWOOM_US_ALLOWED_SYMBOLS", "NVDA")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_QUANTITY", "1")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_NOTIONAL", "500")
    monkeypatch.setenv("KIWOOM_US_CAPITAL_USAGE_PCT", "50")
    monkeypatch.setenv("KIWOOM_US_ORDER_RUNTIME_LOCK_FILE", str(tmp_path / "runtime.lock"))
    get_settings.cache_clear()

    def verify(token: str):
        return AuthenticatedUser(email="allowed@example.com", subject="user-id")

    monkeypatch.setattr(auth_module, "verify_supabase_jwt", verify)
    set_active_kiwoom_session(
        KiwoomSession(
            session_token="safe-session",
            mode="live",
            account_no="masked-account",
            base_url="https://api.kiwoom.com",
            access_token="token-never-printed",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    )

    async def fake_orderability(*args, **kwargs):
        return SimpleNamespace(data={"min_ord_alowq": "1", "min_ord_alowa": "500", "crnc_code": "USD", "aplc_rt": "100%"})

    monkeypatch.setattr(order_module.us_account_service, "_execute", fake_orderability)

    client = TestClient(app)
    lock_response = client.post("/api/us/orders/runtime-lock", headers={"Authorization": "Bearer valid-token"})
    assert lock_response.status_code == 200
    assert lock_response.json()["runtimeOrderLocked"] is True

    status_response = client.get("/api/us/orders/status", headers={"Authorization": "Bearer valid-token"})
    assert status_response.status_code == 200
    status_body = status_response.json()
    assert status_body["runtimeOrderLocked"] is True
    assert status_body["blockedReasons"] == ["LIVE_ORDER_EXECUTION_NOT_IMPLEMENTED"]

    payload = UsOrderRequest(
        side="buy",
        exchange="ND",
        symbol="NVDA",
        quantity=1,
        referencePrice="100",
        tradeType="03",
        confirmText="I_UNDERSTAND_LIVE_US_ORDER",
    )
    precheck = asyncio.run(order_module.us_order_service.precheck_order(payload))
    assert precheck.canSubmit is True
    assert precheck.blockedReasons == []
    assert "CAPITAL_USAGE_LIMIT_EXCEEDED" not in precheck.blockedReasons
    assert precheck.capitalUsagePct == 50
    assert precheck.managedOrderableAmount == 250
    assert precheck.cashReserveAmount == 250
    with pytest.raises(order_module.UsOrderBlocked) as exc_info:
        asyncio.run(order_module.us_order_service.place_order(payload))
    assert str(exc_info.value) == "LIVE_ORDER_EXECUTION_NOT_IMPLEMENTED"
    assert "token-never-printed" not in str(exc_info.value)
    set_active_kiwoom_session(None)


def test_us_order_common_stock_policy_uses_usa10100_is_etf(monkeypatch):
    from types import SimpleNamespace

    from app.schemas.us_order import UsOrderRequest
    from app.services import us_order_service as order_module

    monkeypatch.setenv("KIWOOM_READ_ONLY", "false")
    monkeypatch.setenv("KIWOOM_US_ENABLE_ORDER", "true")
    monkeypatch.setenv("KIWOOM_US_ORDER_CONFIRM", "I_UNDERSTAND_LIVE_US_ORDER")
    monkeypatch.setenv("KIWOOM_US_LIVE_ORDER_UNLOCK", "I_ACCEPT_REAL_US_ORDER_RISK")
    monkeypatch.setenv("KIWOOM_US_ALLOW_ALL_COMMON_STOCKS", "true")
    monkeypatch.setenv("KIWOOM_US_COMMON_STOCK_ONLY", "true")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_QUANTITY", "1")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_NOTIONAL", "500")

    calls: list[tuple[str, dict[str, object] | None]] = []

    async def fake_execute(tr_id, body=None):
        calls.append((tr_id, body))
        if tr_id == "usa10100":
            return SimpleNamespace(data={"isEtf": "Y", "stk_cd": "SOXL", "stex_tp": "NY"})
        if tr_id == "ust31490":
            return SimpleNamespace(data={"min_ord_alowq": "1", "min_ord_alowa": "500", "crnc_code": "USD", "aplc_rt": "100%"})
        raise AssertionError(f"unexpected TR: {tr_id}")

    monkeypatch.setattr(order_module.us_account_service, "_execute", fake_execute)

    payload = UsOrderRequest(
        side="buy",
        exchange="NY",
        symbol="SOXL",
        quantity=1,
        referencePrice="10",
        tradeType="03",
        confirmText="I_UNDERSTAND_LIVE_US_ORDER",
    )

    precheck = asyncio.run(order_module.us_order_service.precheck_order(payload))

    assert precheck.canSubmit is False
    assert "COMMON_STOCK_ONLY" in precheck.blockedReasons
    assert [step["trId"] for step in precheck.model_dump()["trSteps"]] == ["usa10100", "ust31490", "ust20000"]
    assert calls[0] == ("usa10100", {"stk_cd": "SOXL"})
    assert calls[1] == ("ust31490", {"stex_tp": "NY", "stk_cd": "SOXL", "uv": "10"})


def test_us_order_common_stock_policy_takes_precedence_over_legacy_allowlist(monkeypatch):
    from types import SimpleNamespace

    from app.schemas.us_order import UsOrderRequest
    from app.services import us_order_service as order_module

    monkeypatch.setenv("KIWOOM_READ_ONLY", "false")
    monkeypatch.setenv("KIWOOM_US_ENABLE_ORDER", "true")
    monkeypatch.setenv("KIWOOM_US_ORDER_CONFIRM", "I_UNDERSTAND_LIVE_US_ORDER")
    monkeypatch.setenv("KIWOOM_US_LIVE_ORDER_UNLOCK", "I_ACCEPT_REAL_US_ORDER_RISK")
    monkeypatch.setenv("KIWOOM_US_ALLOWED_SYMBOLS", "NVDA")
    monkeypatch.setenv("KIWOOM_US_ALLOW_ALL_COMMON_STOCKS", "true")
    monkeypatch.setenv("KIWOOM_US_COMMON_STOCK_ONLY", "true")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_QUANTITY", "1")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_NOTIONAL", "500")

    async def fake_execute(tr_id, body=None):
        if tr_id == "usa10100":
            return SimpleNamespace(data={"isEtf": "N", "stk_cd": "LIMN", "stex_tp": "ND"})
        if tr_id == "ust31490":
            return SimpleNamespace(data={"min_ord_alowq": "1", "min_ord_alowa": "500", "crnc_code": "USD", "aplc_rt": "100%"})
        raise AssertionError(f"unexpected TR: {tr_id}")

    monkeypatch.setattr(order_module.us_account_service, "_execute", fake_execute)

    status = asyncio.run(order_module.us_order_service.get_status())
    assert status.allowedSymbols == ["COMMON_STOCK_ONLY"]

    payload = UsOrderRequest(
        side="buy",
        exchange="ND",
        symbol="LIMN",
        quantity=1,
        referencePrice="0.15",
        tradeType="03",
        confirmText="I_UNDERSTAND_LIVE_US_ORDER",
    )

    precheck = asyncio.run(order_module.us_order_service.precheck_order(payload))

    assert "SYMBOL_NOT_ALLOWED" not in precheck.blockedReasons
    assert "COMMON_STOCK_ONLY" not in precheck.blockedReasons
    assert [step["trId"] for step in precheck.model_dump()["trSteps"]] == ["usa10100", "ust31490", "ust20000"]


def test_us_order_common_stock_policy_blocks_warrant_name_from_usa10100(monkeypatch):
    from types import SimpleNamespace

    from app.schemas.us_order import UsOrderRequest
    from app.services import us_order_service as order_module

    monkeypatch.setenv("KIWOOM_READ_ONLY", "false")
    monkeypatch.setenv("KIWOOM_US_ENABLE_ORDER", "true")
    monkeypatch.setenv("KIWOOM_US_ORDER_CONFIRM", "I_UNDERSTAND_LIVE_US_ORDER")
    monkeypatch.setenv("KIWOOM_US_LIVE_ORDER_UNLOCK", "I_ACCEPT_REAL_US_ORDER_RISK")
    monkeypatch.setenv("KIWOOM_US_ALLOW_ALL_COMMON_STOCKS", "true")
    monkeypatch.setenv("KIWOOM_US_COMMON_STOCK_ONLY", "true")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_QUANTITY", "1")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_NOTIONAL", "500")

    async def fake_execute(tr_id, body=None):
        if tr_id == "usa10100":
            return SimpleNamespace(data={"isEtf": "N", "stk_cd": "EVLVW", "stk_nm": "테스트 콜 워런트", "stk_enm": "TEST C/WTS"})
        if tr_id == "ust31490":
            return SimpleNamespace(data={"min_ord_alowq": "1", "min_ord_alowa": "500", "crnc_code": "USD", "aplc_rt": "100%"})
        raise AssertionError(f"unexpected TR: {tr_id}")

    monkeypatch.setattr(order_module.us_account_service, "_execute", fake_execute)

    payload = UsOrderRequest(
        side="buy",
        exchange="ND",
        symbol="EVLVW",
        quantity=1,
        referencePrice="0.01",
        tradeType="03",
        confirmText="I_UNDERSTAND_LIVE_US_ORDER",
    )

    precheck = asyncio.run(order_module.us_order_service.precheck_order(payload))

    assert precheck.canSubmit is False
    assert "NON_COMMON_STOCK_NAME" in precheck.blockedReasons
    assert precheck.model_dump()["trSteps"][0]["status"] == "block"


@pytest.mark.parametrize(
    ("orderability", "expected_reason"),
    [
        (
            {"min_ord_alowa": "500", "crnc_code": "USD"},
            "ORDERABLE_QUANTITY_UNAVAILABLE",
        ),
        (
            {"min_ord_alowq": "1", "crnc_code": "USD"},
            "ORDERABLE_AMOUNT_UNAVAILABLE",
        ),
        (
            {"min_ord_alowq": "1", "min_ord_alowa": "500", "crnc_code": "KRW"},
            "ORDERABLE_CURRENCY_UNSUPPORTED",
        ),
        (
            {"min_ord_alowq": "1", "min_ord_alowa": "50", "crnc_code": "USD"},
            "ORDERABLE_AMOUNT_EXCEEDED",
        ),
    ],
)
def test_us_buy_precheck_requires_documented_ust31490_cash_fields(
    monkeypatch,
    tmp_path,
    orderability,
    expected_reason,
):
    from types import SimpleNamespace

    from app.schemas.us_order import UsOrderRequest
    from app.services import us_order_service as order_module

    monkeypatch.setenv("KIWOOM_READ_ONLY", "false")
    monkeypatch.setenv("KIWOOM_US_ENABLE_ORDER", "true")
    monkeypatch.setenv("KIWOOM_US_ORDER_CONFIRM", "I_UNDERSTAND_LIVE_US_ORDER")
    monkeypatch.setenv("KIWOOM_US_LIVE_ORDER_UNLOCK", "I_ACCEPT_REAL_US_ORDER_RISK")
    monkeypatch.setenv("KIWOOM_US_ALLOWED_SYMBOLS", "NVDA")
    monkeypatch.setenv("KIWOOM_US_ALLOW_ALL_COMMON_STOCKS", "false")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_QUANTITY", "1")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_NOTIONAL", "500")
    monkeypatch.setenv("KIWOOM_US_ORDER_RUNTIME_LOCK_FILE", str(tmp_path / "runtime.lock"))
    monkeypatch.setattr(order_module, "_runtime_order_locked", lambda: False)
    monkeypatch.setattr(order_module, "_auto_trade_runtime_enabled", True)
    monkeypatch.setattr(
        order_module,
        "get_active_kiwoom_session",
        lambda: SimpleNamespace(mode="live", safe_account_label="****-0000"),
    )

    async def fake_execute(tr_id, body=None):
        assert tr_id == "ust31490"
        return SimpleNamespace(data=orderability)

    monkeypatch.setattr(order_module.us_account_service, "_execute", fake_execute)

    precheck = asyncio.run(
        order_module.us_order_service.precheck_order(
            UsOrderRequest(
                side="buy",
                exchange="ND",
                symbol="NVDA",
                quantity=1,
                referencePrice="100",
                tradeType="03",
                confirmText="",
            )
        )
    )

    assert precheck.canSubmit is False
    assert expected_reason in precheck.blockedReasons
    orderability_step = next(step for step in precheck.trSteps if step.trId == "ust31490")
    assert orderability_step.status == "block"


def test_us_order_history_uses_temp_db(monkeypatch, tmp_path):
    monkeypatch.setenv("ALLOWED_USER_EMAILS", "allowed@example.com")
    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(tmp_path / "orders.sqlite3"))
    get_settings.cache_clear()

    def verify(token: str):
        return AuthenticatedUser(email="allowed@example.com", subject="user-id")

    monkeypatch.setattr(auth_module, "verify_supabase_jwt", verify)

    response = TestClient(app).get("/api/us/orders", headers={"Authorization": "Bearer valid-token"})

    assert response.status_code == 200


def test_existing_order_attempt_database_gets_allocation_link_column(
    monkeypatch,
    tmp_path,
):
    import sqlite3

    from app.services import us_order_service as order_module

    db_path = tmp_path / "legacy-orders.sqlite3"
    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(db_path))
    get_settings.cache_clear()
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            CREATE TABLE us_order_attempts (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              tr_id TEXT NOT NULL,
              side TEXT NOT NULL,
              symbol TEXT NOT NULL,
              exchange TEXT NOT NULL,
              quantity INTEGER NOT NULL,
              order_price TEXT NOT NULL,
              reference_price TEXT NOT NULL DEFAULT '',
              trade_type TEXT NOT NULL,
              strategy TEXT,
              reason TEXT,
              return_code TEXT NOT NULL,
              return_msg TEXT NOT NULL,
              order_no TEXT,
              auto_exit_armed INTEGER NOT NULL DEFAULT 0,
              auto_exit_completed INTEGER NOT NULL DEFAULT 0,
              auto_exit_reason TEXT,
              auto_exit_order_no TEXT,
              created_at TEXT NOT NULL
            )
            """
        )
        connection.commit()
    finally:
        connection.close()

    migrated = order_module._connect_order_db()
    try:
        columns = {
            str(row["name"])
            for row in migrated.execute(
                "PRAGMA table_info(us_order_attempts)"
            ).fetchall()
        }
    finally:
        migrated.close()

    assert "allocation_reservation_id" in columns


def test_us_take_profit_plan_uses_latest_successful_buy_reference(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from app.schemas.us_order import UsOrderRequest, UsOrderResponse
    from app.services import us_order_service as order_module

    monkeypatch.setenv("ALLOWED_USER_EMAILS", "allowed@example.com")
    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(tmp_path / "orders.sqlite3"))
    get_settings.cache_clear()

    def verify(token: str):
        return AuthenticatedUser(email="allowed@example.com", subject="user-id")

    monkeypatch.setattr(auth_module, "verify_supabase_jwt", verify)

    payload = UsOrderRequest(
        side="buy",
        exchange="ND",
        symbol="LIMN",
        quantity=1,
        referencePrice="0.15",
        tradeType="03",
        confirmText="I_UNDERSTAND_LIVE_US_ORDER",
    )
    result = UsOrderResponse(
        trId="ust20000",
        side="buy",
        code="LIMN",
        exchange="ND",
        returnCode="0",
        returnMessage="OK",
        orderNo="order-no-not-secret",
        source="fixture",
        updatedAt="2026-07-16T12:00:00+09:00",
    )
    order_module._record_order_attempt(payload, result)

    async def fake_order_fills(*, symbol=None, exchange=None, side="0"):
        assert symbol == "LIMN"
        assert exchange == "ND"
        assert side == "2"
        return SimpleNamespace(
            data={
                "result_list": [
                    {
                        "ord_no": "order-no-not-secret",
                        "stk_cd": "LIMN",
                        "slby_tp_nm": "매수",
                        "cntr_qty": "000000000001",
                        "cntr_uv": "0.1600",
                        "ord_stat": "체결완료",
                    }
                ]
            }
        )

    async def fake_precheck(request):
        assert request.side == "sell"
        assert request.symbol == "LIMN"
        assert request.tradeType == "30"
        assert request.orderPrice == "0.1632"
        return order_module.UsOrderPrecheckResponse(
            canSubmit=False,
            blockedReasons=["CONFIRM_TEXT_REQUIRED"],
            requestSummary={"side": "sell", "exchange": "ND", "symbol": "LIMN", "quantity": 1, "tradeType": "30"},
            trSteps=[],
            source="fixture",
            updatedAt="2026-07-16T12:00:00+09:00",
        )

    monkeypatch.setattr(order_module.us_order_service, "precheck_order", fake_precheck)
    monkeypatch.setattr(order_module.us_account_service, "get_today_order_fills", fake_order_fills)

    response = TestClient(app).get(
        "/api/us/orders/take-profit-plan",
        headers={"Authorization": "Bearer valid-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["hasOpenBuy"] is True
    assert body["symbol"] == "LIMN"
    assert body["entryReferencePrice"] == 0.15
    assert body["actualFillPrice"] == 0.16
    assert body["filledQuantity"] == 1
    assert body["fillStatus"] == "체결완료"
    assert body["fillTrId"] == "ust21510"
    assert body["targetPrice"] == 0.1632
    assert body["sellTradeType"] == "30"
    assert body["blockedReasons"] == ["CONFIRM_TEXT_REQUIRED"]


def test_us_sell_precheck_uses_holdings_for_quantity(monkeypatch):
    from types import SimpleNamespace

    from app.schemas.us_order import UsOrderRequest
    from app.services import us_order_service as order_module

    monkeypatch.setenv("KIWOOM_US_ENABLE_ORDER", "true")
    monkeypatch.setenv("KIWOOM_READ_ONLY", "false")
    monkeypatch.setenv("KIWOOM_US_ORDER_CONFIRM", "I_UNDERSTAND_LIVE_US_ORDER")
    monkeypatch.setenv("KIWOOM_US_LIVE_ORDER_UNLOCK", "I_ACCEPT_REAL_US_ORDER_RISK")
    monkeypatch.setenv("KIWOOM_US_ALLOW_ALL_COMMON_STOCKS", "true")
    monkeypatch.setenv("KIWOOM_US_COMMON_STOCK_ONLY", "true")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_QUANTITY", "1")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_KRW", "30000")
    monkeypatch.setenv("KIWOOM_US_ORDER_USD_KRW_RATE", "1400")

    monkeypatch.setattr(order_module, "get_active_kiwoom_session", lambda: SimpleNamespace(mode="live", safe_account_label="****-0000"))
    monkeypatch.setattr(order_module, "_runtime_order_locked", lambda: False)

    async def fake_execute(tr_id, body=None):
        assert tr_id == "usa10100"
        return SimpleNamespace(data={"isEtf": "N", "stk_nm": "LIMN", "stk_enm": "LIMINATUS PHARMA"})

    async def fake_holdings_for_order(*args, **kwargs):
        return [SimpleNamespace(symbol="LIMN", exchange="ND", sellableQuantity=1, price=0.1632, blockedReasons=[])]

    monkeypatch.setattr(order_module.us_account_service, "_execute", fake_execute)
    monkeypatch.setattr(order_module.us_account_service, "get_holdings_for_order", fake_holdings_for_order)

    payload = UsOrderRequest(
        side="sell",
        exchange="ND",
        symbol="LIMN",
        quantity=1,
        orderPrice="0.1632",
        referencePrice="0.1632",
        tradeType="30",
        confirmText="I_UNDERSTAND_LIVE_US_ORDER",
    )

    precheck = asyncio.run(order_module.us_order_service.precheck_order(payload))

    assert "SELL_HOLDINGS_NOT_VERIFIED" not in precheck.blockedReasons
    assert "SELL_HOLDINGS_LOOKUP_FAILED" not in precheck.blockedReasons
    assert any(step.trId == "ust21070" and step.status == "pass" for step in precheck.trSteps)


def test_us_sell_precheck_falls_back_to_today_fills_when_holdings_lookup_fails(monkeypatch):
    from types import SimpleNamespace

    from app.schemas.us_order import UsOrderRequest
    from app.services import us_order_service as order_module

    monkeypatch.setenv("KIWOOM_US_ENABLE_ORDER", "true")
    monkeypatch.setenv("KIWOOM_READ_ONLY", "false")
    monkeypatch.setenv("KIWOOM_US_ORDER_CONFIRM", "I_UNDERSTAND_LIVE_US_ORDER")
    monkeypatch.setenv("KIWOOM_US_LIVE_ORDER_UNLOCK", "I_ACCEPT_REAL_US_ORDER_RISK")
    monkeypatch.setenv("KIWOOM_US_ALLOW_ALL_COMMON_STOCKS", "true")
    monkeypatch.setenv("KIWOOM_US_COMMON_STOCK_ONLY", "true")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_QUANTITY", "1")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_KRW", "30000")
    monkeypatch.setenv("KIWOOM_US_ORDER_USD_KRW_RATE", "1400")

    monkeypatch.setattr(order_module, "get_active_kiwoom_session", lambda: SimpleNamespace(mode="live", safe_account_label="****-0000"))
    monkeypatch.setattr(order_module, "_runtime_order_locked", lambda: False)

    async def fake_execute(tr_id, body=None):
        assert tr_id == "usa10100"
        return SimpleNamespace(data={"isEtf": "N", "stk_nm": "LIMN", "stk_enm": "LIMINATUS PHARMA"})

    async def fake_holdings_for_order(*args, **kwargs):
        raise order_module.US_READONLY_SERVICE_ERRORS[0]("holdings failed")

    async def fake_order_fills(*, symbol=None, exchange=None, side="0"):
        assert symbol == "LIMN"
        assert exchange == "ND"
        assert side == "0"
        return SimpleNamespace(
            data={
                "result_list": [
                    {"stk_cd": "LIMN", "slby_tp": "2", "cntr_qty": "1", "cntr_uv": "0.1600"},
                ]
            }
        )

    monkeypatch.setattr(order_module.us_account_service, "_execute", fake_execute)
    monkeypatch.setattr(order_module.us_account_service, "get_holdings_for_order", fake_holdings_for_order)
    monkeypatch.setattr(order_module.us_account_service, "get_today_order_fills", fake_order_fills)

    payload = UsOrderRequest(
        side="sell",
        exchange="ND",
        symbol="LIMN",
        quantity=1,
        orderPrice="0.1632",
        referencePrice="0.1632",
        tradeType="30",
        confirmText="I_UNDERSTAND_LIVE_US_ORDER",
    )

    precheck = asyncio.run(order_module.us_order_service.precheck_order(payload))

    assert "SELL_HOLDINGS_NOT_VERIFIED" not in precheck.blockedReasons
    assert "SELL_HOLDINGS_LOOKUP_FAILED" not in precheck.blockedReasons
    assert any(step.trId == "ust21070" and step.status == "error" for step in precheck.trSteps)
    assert any(step.trId == "ust21510" and step.status == "pass" for step in precheck.trSteps)


def test_us_take_profit_monitor_compares_latest_quote_to_target(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from app.schemas.us_order import UsOrderRequest, UsOrderResponse
    from app.services import us_order_service as order_module

    monkeypatch.setenv("ALLOWED_USER_EMAILS", "allowed@example.com")
    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(tmp_path / "orders.sqlite3"))
    get_settings.cache_clear()

    def verify(token: str):
        return AuthenticatedUser(email="allowed@example.com", subject="user-id")

    monkeypatch.setattr(auth_module, "verify_supabase_jwt", verify)

    payload = UsOrderRequest(
        side="buy",
        exchange="ND",
        symbol="LIMN",
        quantity=1,
        referencePrice="0.15",
        tradeType="03",
        confirmText="I_UNDERSTAND_LIVE_US_ORDER",
    )
    result = UsOrderResponse(
        trId="ust20000",
        side="buy",
        code="LIMN",
        exchange="ND",
        returnCode="0",
        returnMessage="OK",
        orderNo="order-no-not-secret",
        source="fixture",
        updatedAt="2026-07-16T12:00:00+09:00",
    )
    order_module._record_order_attempt(payload, result)

    async def fake_order_fills(*, symbol=None, exchange=None, side="0"):
        return SimpleNamespace(
            data={
                "result_list": [
                    {
                        "ord_no": "order-no-not-secret",
                        "stk_cd": "LIMN",
                        "cntr_qty": "1",
                        "cntr_uv": "0.1600",
                        "ord_stat": "체결완료",
                    }
                ]
            }
        )

    async def fake_precheck(request):
        return order_module.UsOrderPrecheckResponse(
            canSubmit=True,
            blockedReasons=[],
            requestSummary={"side": "sell", "exchange": "ND", "symbol": "LIMN", "quantity": 1, "tradeType": "30"},
            trSteps=[],
            source="fixture",
            updatedAt="2026-07-16T12:00:00+09:00",
        )

    async def fake_latest_quote_price(symbol: str, exchange: str):
        assert symbol == "LIMN"
        assert exchange == "ND"
        return 0.1640, "realtime-window"

    monkeypatch.setattr(order_module.us_account_service, "get_today_order_fills", fake_order_fills)
    monkeypatch.setattr(order_module.us_order_service, "precheck_order", fake_precheck)
    monkeypatch.setattr(order_module, "_latest_quote_price", fake_latest_quote_price)

    response = TestClient(app).get(
        "/api/us/orders/take-profit-monitor",
        headers={"Authorization": "Bearer valid-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["hasOpenBuy"] is True
    assert body["symbol"] == "LIMN"
    assert body["quoteTrId"] == "realtime-window"
    assert body["latestPrice"] == 0.164
    assert body["targetPrice"] == 0.1632
    assert body["stopLossPrice"] == 0.1568
    assert body["targetReached"] is True
    assert body["stopLossTriggered"] is False
    assert body["exitReason"] == "take_profit"
    assert body["sellTicketReady"] is True
    assert body["blockedReasons"] == []


def test_us_latest_quote_price_falls_back_to_holdings_price(monkeypatch):
    from types import SimpleNamespace

    from app.services import us_order_service as order_module

    realtime_window_store.clear()

    async def fake_execute(tr_id, body=None):
        assert tr_id == "usa10100"
        raise order_module.US_READONLY_SERVICE_ERRORS[0]("quote failed")

    async def fake_holdings_for_order(*args, **kwargs):
        return [SimpleNamespace(symbol="LIMN", exchange="ND", sellableQuantity=1, price=0.1568, blockedReasons=[])]

    monkeypatch.setattr(order_module.us_account_service, "_execute", fake_execute)
    monkeypatch.setattr(order_module.us_account_service, "get_holdings_for_order", fake_holdings_for_order)

    price, source = asyncio.run(order_module._latest_quote_price("LIMN", "ND"))

    assert price == 0.1568
    assert source == "ust21070"


def test_us_take_profit_monitor_triggers_stop_loss(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from app.schemas.us_order import UsOrderRequest, UsOrderResponse
    from app.services import us_order_service as order_module

    monkeypatch.setenv("ALLOWED_USER_EMAILS", "allowed@example.com")
    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(tmp_path / "orders.sqlite3"))
    get_settings.cache_clear()

    def verify(token: str):
        return AuthenticatedUser(email="allowed@example.com", subject="user-id")

    monkeypatch.setattr(auth_module, "verify_supabase_jwt", verify)

    payload = UsOrderRequest(
        side="buy",
        exchange="ND",
        symbol="LIMN",
        quantity=1,
        referencePrice="0.15",
        tradeType="03",
        confirmText="I_UNDERSTAND_LIVE_US_ORDER",
    )
    result = UsOrderResponse(
        trId="ust20000",
        side="buy",
        code="LIMN",
        exchange="ND",
        returnCode="0",
        returnMessage="OK",
        orderNo="order-no-not-secret",
        source="fixture",
        updatedAt="2026-07-16T12:00:00+09:00",
    )
    order_module._record_order_attempt(payload, result)

    async def fake_order_fills(*, symbol=None, exchange=None, side="0"):
        return SimpleNamespace(
            data={
                "result_list": [
                    {
                        "ord_no": "order-no-not-secret",
                        "stk_cd": "LIMN",
                        "slby_tp": "2",
                        "cntr_qty": "1",
                        "cntr_uv": "0.1600",
                        "ord_stat": "체결완료",
                    }
                ]
            }
        )

    async def fake_precheck(request):
        return order_module.UsOrderPrecheckResponse(
            canSubmit=True,
            blockedReasons=[],
            requestSummary={"side": "sell", "exchange": "ND", "symbol": "LIMN", "quantity": 1, "tradeType": "30"},
            trSteps=[],
            source="fixture",
            updatedAt="2026-07-16T12:00:00+09:00",
        )

    async def fake_latest_quote_price(symbol: str, exchange: str):
        assert symbol == "LIMN"
        assert exchange == "ND"
        return 0.1560, "realtime-window"

    monkeypatch.setattr(order_module.us_account_service, "get_today_order_fills", fake_order_fills)
    monkeypatch.setattr(order_module.us_order_service, "precheck_order", fake_precheck)
    monkeypatch.setattr(order_module, "_latest_quote_price", fake_latest_quote_price)

    response = TestClient(app).get(
        "/api/us/orders/take-profit-monitor",
        headers={"Authorization": "Bearer valid-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["targetReached"] is False
    assert body["stopLossTriggered"] is True
    assert body["exitReason"] == "stop_loss"
    assert body["sellTicketReady"] is True
    assert body["stopLossPrice"] == 0.1568


def test_us_auto_exit_tick_submits_sell_after_armed_buy(monkeypatch, tmp_path):
    from app.schemas.us_order import UsOrderRequest, UsOrderResponse
    from app.services import us_order_service as order_module

    monkeypatch.setenv("KIWOOM_US_AUTO_EXIT_ENABLED", "true")
    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(tmp_path / "orders.sqlite3"))
    get_settings.cache_clear()
    monkeypatch.setattr(order_module, "_auto_trade_runtime_enabled", True)

    buy_payload = UsOrderRequest(
        side="buy",
        exchange="ND",
        symbol="LIMN",
        quantity=1,
        referencePrice="0.15",
        tradeType="03",
        confirmText="I_UNDERSTAND_LIVE_US_ORDER",
    )
    buy_result = UsOrderResponse(
        trId="ust20000",
        side="buy",
        code="LIMN",
        exchange="ND",
        returnCode="0",
        returnMessage="OK",
        orderNo="buy-order-no",
        source="fixture",
        updatedAt="2026-07-16T12:00:00+09:00",
    )
    order_module._record_order_attempt(buy_payload, buy_result)

    async def fake_monitor(**kwargs):
        return order_module.UsTakeProfitMonitorResponse(
            hasOpenBuy=True,
            sourceOrderId=1,
            symbol="LIMN",
            exchange="ND",
            targetProfitPct=2.0,
            stopLossPct=2.0,
            entryReferencePrice=0.15,
            actualFillPrice=0.16,
            targetPrice=0.1632,
            stopLossPrice=0.1568,
            latestPrice=0.156,
            targetReached=False,
            stopLossTriggered=True,
            spreadToTargetPct=4.4118,
            spreadToStopLossPct=-0.5102,
            exitReason="stop_loss",
            quoteTrId="realtime-window",
            sellTicketReady=True,
            blockedReasons=[],
            source="fixture",
            updatedAt="2026-07-16T12:01:00+09:00",
        )

    placed: dict[str, object] = {}

    async def fake_place_order(payload):
        placed["payload"] = payload
        return UsOrderResponse(
            trId="ust20001",
            side="sell",
            code=payload.symbol,
            exchange=payload.exchange,
            returnCode="0",
            returnMessage="OK",
            orderNo="sell-order-no",
            source="fixture",
            updatedAt="2026-07-16T12:01:01+09:00",
        )

    monkeypatch.setattr(order_module.us_order_service, "get_take_profit_monitor", fake_monitor)
    monkeypatch.setattr(order_module.us_order_service, "place_order", fake_place_order)

    result = asyncio.run(order_module.us_order_service.run_auto_exit_tick())

    assert result.action == "submitted"
    assert result.exitReason == "stop_loss"
    assert result.trId == "ust20001"
    assert result.exitOrderNo == "sell-order-no"
    sell_payload = placed["payload"]
    assert sell_payload.side == "sell"
    assert sell_payload.tradeType == "03"
    assert sell_payload.confirmText == "I_UNDERSTAND_LIVE_US_ORDER"


def test_us_auto_exit_tick_monitors_each_position_and_exits_matching_order(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from app.schemas.us_order import UsOrderRequest, UsOrderResponse
    from app.services import us_order_service as order_module
    from trading_engine.risk.allocation_store import CapitalAllocationStore
    from trading_engine.risk.capital_allocator import (
        CapitalAllocationState,
        evaluate_capital_allocation,
    )

    monkeypatch.setenv("KIWOOM_US_AUTO_EXIT_ENABLED", "true")
    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(tmp_path / "orders.sqlite3"))
    get_settings.cache_clear()
    monkeypatch.setattr(order_module, "_auto_trade_runtime_enabled", True)

    for symbol, order_no in (("FIRST", "buy-first"), ("SECOND", "buy-second")):
        payload = UsOrderRequest(
            side="buy",
            exchange="ND",
            symbol=symbol,
            quantity=1,
            referencePrice="10.00",
            tradeType="03",
            confirmText="",
        )
        result = UsOrderResponse(
            trId="ust20000",
            side="buy",
            code=symbol,
            exchange="ND",
            returnCode="0",
            returnMessage="OK",
            orderNo=order_no,
            source="fixture",
            updatedAt="2026-07-16T12:00:00+09:00",
        )
        order_module._record_order_attempt(payload, result)

    allocation_store = CapitalAllocationStore(tmp_path / "orders.sqlite3")
    allocation_cycle = allocation_store.ensure_cycle(
        account_scope="profile-a",
        market_date="2026-07-31",
        orderable_cash=4_000,
    )
    allocation_reservations = {}
    for symbol, order_no in (("FIRST", "buy-first"), ("SECOND", "buy-second")):
        allocation_state = allocation_store.load_state(
            cycle=allocation_cycle,
            orderable_cash=4_000,
        )
        allocation_decision = evaluate_capital_allocation(
            state=allocation_state,
            symbol=symbol,
            reference_price=10,
            max_quantity=1,
        )
        allocation_reservation = allocation_store.reserve(
            cycle=allocation_cycle,
            decision=allocation_decision,
            strategy="strategy-a",
            exchange="ND",
            reference_price=10,
        )
        allocation_store.mark_submitted(
            allocation_reservation.id,
            order_no,
        )
        allocation_store.mark_filled(allocation_reservation.id)
        assert order_module._link_order_attempt_allocation(
            order_no=order_no,
            symbol=symbol,
            exchange="ND",
            reservation_id=allocation_reservation.id,
        )
        allocation_reservations[symbol] = allocation_reservation.id

    monitored_order_ids: list[int] = []

    async def fake_monitor(*, source_order_id=None, **kwargs):
        monitored_order_ids.append(source_order_id)
        is_second = source_order_id == 2
        return order_module.UsTakeProfitMonitorResponse(
            hasOpenBuy=True,
            sourceOrderId=source_order_id,
            symbol="SECOND" if is_second else "FIRST",
            exchange="ND",
            quantity=1,
            targetProfitPct=2.0,
            stopLossPct=2.0,
            entryReferencePrice=10.0,
            actualFillPrice=10.0,
            targetPrice=10.2,
            stopLossPrice=9.8,
            latestPrice=9.7 if is_second else 10.0,
            targetReached=False,
            stopLossTriggered=is_second,
            exitReason="stop_loss" if is_second else None,
            quoteTrId="fixture",
            sellTicketReady=is_second,
            blockedReasons=[] if is_second else ["TARGET_PRICE_NOT_REACHED"],
            source="fixture",
            updatedAt="2026-07-16T12:01:00+09:00",
        )

    placed: dict[str, object] = {}

    async def fake_place_order(payload):
        placed["payload"] = payload
        return UsOrderResponse(
            trId="ust20001",
            side="sell",
            code=payload.symbol,
            exchange=payload.exchange,
            returnCode="0",
            returnMessage="OK",
            orderNo="sell-second",
            source="fixture",
            updatedAt="2026-07-16T12:01:01+09:00",
        )

    monkeypatch.setattr(order_module.us_order_service, "get_take_profit_monitor", fake_monitor)
    monkeypatch.setattr(order_module.us_order_service, "place_order", fake_place_order)

    result = asyncio.run(order_module.us_order_service.run_auto_exit_tick())

    assert monitored_order_ids == [1, 2]
    assert result.action == "submitted"
    assert result.monitoredPositionCount == 2
    assert result.sourceOrderId == 2
    assert result.symbol == "SECOND"
    assert placed["payload"].symbol == "SECOND"

    pending = asyncio.run(order_module.us_order_service.run_auto_exit_tick())

    assert pending.action == "pending_fill"
    assert pending.sourceOrderId == 2
    assert pending.exitOrderNo == "sell-second"
    assert monitored_order_ids == [1, 2, 1]
    pending_reservations = allocation_store.list_reservations(
        allocation_cycle.id
    )
    assert {
        item.symbol: item.status
        for item in pending_reservations
    } == {"FIRST": "filled", "SECOND": "filled"}

    async def filled_exit(*, symbol=None, exchange=None, side="0"):
        assert side == "1"
        return SimpleNamespace(data={
            "result_list": [
                {
                    "ord_no": "sell-second",
                    "stk_cd": "SECOND",
                    "cntr_qty": "1",
                    "cntr_uv": "9.70",
                }
            ]
        })

    monkeypatch.setattr(order_module.us_account_service, "get_today_order_fills", filled_exit)
    after_fill = asyncio.run(order_module.us_order_service.run_auto_exit_tick())

    assert after_fill.action == "monitoring"
    assert after_fill.sourceOrderId == 1
    remaining = order_module._armed_buy_rows()
    assert [int(row["id"]) for row in remaining] == [1]
    restarted_store = CapitalAllocationStore(tmp_path / "orders.sqlite3")
    restored_reservations = restarted_store.list_reservations(
        allocation_cycle.id
    )
    assert {
        item.symbol: item.status
        for item in restored_reservations
    } == {"FIRST": "filled", "SECOND": "closed"}
    assert next(
        item
        for item in restored_reservations
        if item.id == allocation_reservations["SECOND"]
    ).closed_at is not None
    restored_state = restarted_store.load_state(
        cycle=allocation_cycle,
        orderable_cash=4_000,
    )
    assert restored_state.open_symbols == frozenset({"FIRST"})


def test_us_take_profit_plan_aggregates_partial_fills_for_source_order(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from app.schemas.us_order import UsOrderRequest, UsOrderResponse
    from app.services import us_order_service as order_module

    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(tmp_path / "orders.sqlite3"))
    get_settings.cache_clear()

    payload = UsOrderRequest(
        side="buy",
        exchange="ND",
        symbol="PART",
        quantity=3,
        referencePrice="10.00",
        tradeType="03",
        confirmText="I_UNDERSTAND_LIVE_US_ORDER",
    )
    result = UsOrderResponse(
        trId="ust20000",
        side="buy",
        code="PART",
        exchange="ND",
        returnCode="0",
        returnMessage="OK",
        orderNo="partial-order",
        source="fixture",
        updatedAt="2026-07-16T12:00:00+09:00",
    )
    order_module._record_order_attempt(payload, result)

    async def fake_order_fills(*, symbol=None, exchange=None, side="0"):
        return SimpleNamespace(data={
            "result_list": [
                {
                    "ord_no": "partial-order",
                    "stk_cd": "PART",
                    "cntr_qty": "1",
                    "cntr_uv": "10.00",
                    "ord_stat": "부분체결",
                },
                {
                    "ord_no": "partial-order",
                    "stk_cd": "PART",
                    "cntr_qty": "1",
                    "cntr_uv": "12.00",
                    "ord_stat": "부분체결",
                },
            ]
        })

    async def fake_precheck(request):
        assert request.quantity == 2
        return order_module.UsOrderPrecheckResponse(
            canSubmit=True,
            blockedReasons=[],
            requestSummary={
                "side": "sell",
                "exchange": "ND",
                "symbol": "PART",
                "quantity": 2,
                "tradeType": "30",
            },
            trSteps=[],
            source="fixture",
            updatedAt="2026-07-16T12:00:00+09:00",
        )

    monkeypatch.setattr(order_module.us_account_service, "get_today_order_fills", fake_order_fills)
    monkeypatch.setattr(order_module.us_order_service, "precheck_order", fake_precheck)

    plan = asyncio.run(
        order_module.us_order_service.get_take_profit_plan(
            target_profit_pct=2.0,
            source_order_id=1,
        )
    )

    assert plan.sourceOrderId == 1
    assert plan.filledQuantity == 2
    assert plan.quantity == 2
    assert plan.actualFillPrice == 11.0
    assert plan.targetPrice == 11.22


def test_us_auto_exit_tick_returns_retry_pending_when_sell_fails(monkeypatch, tmp_path):
    from app.schemas.us_order import UsOrderRequest, UsOrderResponse
    from app.services import us_order_service as order_module

    monkeypatch.setenv("KIWOOM_US_AUTO_EXIT_ENABLED", "true")
    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(tmp_path / "orders.sqlite3"))
    get_settings.cache_clear()
    monkeypatch.setattr(order_module, "_auto_trade_runtime_enabled", True)

    buy_payload = UsOrderRequest(
        side="buy",
        exchange="ND",
        symbol="LIMN",
        quantity=1,
        referencePrice="0.15",
        tradeType="03",
        confirmText="I_UNDERSTAND_LIVE_US_ORDER",
    )
    buy_result = UsOrderResponse(
        trId="ust20000",
        side="buy",
        code="LIMN",
        exchange="ND",
        returnCode="0",
        returnMessage="OK",
        orderNo="buy-order-no",
        source="fixture",
        updatedAt="2026-07-16T12:00:00+09:00",
    )
    order_module._record_order_attempt(buy_payload, buy_result)

    async def fake_monitor(**kwargs):
        return order_module.UsTakeProfitMonitorResponse(
            hasOpenBuy=True,
            sourceOrderId=1,
            symbol="LIMN",
            exchange="ND",
            targetProfitPct=2.0,
            stopLossPct=2.0,
            entryReferencePrice=0.15,
            actualFillPrice=0.16,
            targetPrice=0.1632,
            stopLossPrice=0.1568,
            latestPrice=0.156,
            targetReached=False,
            stopLossTriggered=True,
            spreadToTargetPct=4.4118,
            spreadToStopLossPct=-0.5102,
            exitReason="stop_loss",
            quoteTrId="realtime-window",
            sellTicketReady=True,
            blockedReasons=[],
            source="fixture",
            updatedAt="2026-07-16T12:01:00+09:00",
        )

    async def fake_place_order(payload):
        raise order_module.UsOrderTransportError("AUTO_EXIT_SELL_FAILED")

    monkeypatch.setattr(order_module.us_order_service, "get_take_profit_monitor", fake_monitor)
    monkeypatch.setattr(order_module.us_order_service, "place_order", fake_place_order)

    result = asyncio.run(order_module.us_order_service.run_auto_exit_tick())

    assert result.action == "retry_pending"
    assert result.retryPlanned is True
    assert result.retryCount == 1
    assert result.warning == "AUTO_EXIT_SELL_FAILED_RETRY_NEXT_TICK"
    assert "AUTO_EXIT_SELL_FAILED" in result.blockedReasons
    events = asyncio.run(order_module.us_order_service.list_auto_trade_events(5))
    assert events[0].action == "auto_exit"
    assert events[0].status == "blocked"
    assert events[0].symbol == "LIMN"
    assert events[0].exchange == "ND"
    assert events[0].side == "sell"
    assert events[0].trId == "ust20001"
    assert "AUTO_EXIT_SELL_FAILED" in events[0].blockedReasons


def test_us_sell_precheck_uses_today_fill_fallback_when_holdings_lag(monkeypatch, tmp_path):
    from app.schemas.us_order import UsOrderRequest
    from app.services import us_order_service as order_module

    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(tmp_path / "orders.sqlite3"))
    monkeypatch.setenv("KIWOOM_US_ENABLE_ORDER", "true")
    monkeypatch.setenv("KIWOOM_READ_ONLY", "false")
    monkeypatch.setenv("KIWOOM_US_ORDER_CONFIRM", "I_UNDERSTAND_LIVE_US_ORDER")
    monkeypatch.setenv("KIWOOM_US_LIVE_ORDER_UNLOCK", "I_ACCEPT_REAL_US_ORDER_RISK")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_QUANTITY", "1")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_KRW", "30000")
    monkeypatch.setenv("KIWOOM_US_ALLOWED_SYMBOLS", "ZYBT")
    get_settings.cache_clear()

    class Session:
        mode = "real"
        safe_account_label = "real-account"

    async def fake_sellable_quantity(symbol, exchange):
        return 0

    async def fake_today_net_quantity(symbol, exchange):
        return 1

    monkeypatch.setattr(order_module, "get_active_kiwoom_session", lambda: Session())
    monkeypatch.setattr(order_module, "_sellable_holding_quantity", fake_sellable_quantity)
    monkeypatch.setattr(order_module, "_today_net_filled_quantity", fake_today_net_quantity)

    result = asyncio.run(order_module.us_order_service.precheck_order(UsOrderRequest(
        side="sell",
        exchange="ND",
        symbol="ZYBT",
        quantity=1,
        referencePrice="1.35",
        tradeType="03",
        confirmText="I_UNDERSTAND_LIVE_US_ORDER",
    )))

    assert result.canSubmit is True
    assert "SELL_HOLDINGS_NOT_VERIFIED" not in result.blockedReasons
    fill_step = next(step for step in result.trSteps if step.trId == "ust21510")
    assert fill_step.status == "pass"


def test_us_latest_quote_price_records_rest_poll_tick(monkeypatch, tmp_path):
    from app.services import us_order_service as order_module
    from app.services.realtime_event_store import realtime_event_counts
    from trading_engine.providers.kiwoom_us.schemas import UsReadOnlyTrResponse

    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(tmp_path / "orders.sqlite3"))
    order_module.realtime_window_store.clear()

    async def fake_execute(tr_id, body):
        assert tr_id == "usa10100"
        return UsReadOnlyTrResponse(
            tr_id="usa10100",
            return_code="0",
            return_msg="OK",
            data={"cur_prc": "1.2500", "flu_rt": "+3.20", "acc_trde_qty": "100000"},
            unknown_fields={},
        )

    monkeypatch.setattr(order_module.us_account_service, "_execute", fake_execute)

    price, source = asyncio.run(order_module._latest_quote_price("ZYBT", "ND"))

    assert price == 1.25
    assert source == "usa10100"
    assert realtime_event_counts(["ZYBT"])["ZYBT"] == 1


def test_us_auto_exit_tick_auto_arms_latest_buy_when_autotrade_on(monkeypatch, tmp_path):
    from app.schemas.us_order import UsOrderRequest, UsOrderResponse
    from app.services import us_order_service as order_module

    monkeypatch.setenv("KIWOOM_US_AUTO_EXIT_ENABLED", "true")
    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(tmp_path / "orders.sqlite3"))
    get_settings.cache_clear()
    monkeypatch.setattr(order_module, "_auto_trade_runtime_enabled", True)

    buy_payload = UsOrderRequest(
        side="buy",
        exchange="ND",
        symbol="LIMN",
        quantity=1,
        referencePrice="0.15",
        tradeType="03",
        confirmText="",
    )
    buy_result = UsOrderResponse(
        trId="ust20000",
        side="buy",
        code="LIMN",
        exchange="ND",
        returnCode="0",
        returnMessage="OK",
        orderNo="buy-order-no",
        source="fixture",
        updatedAt="2026-07-16T12:00:00+09:00",
    )
    order_module._record_order_attempt(buy_payload, buy_result)

    async def fake_monitor(**kwargs):
        return order_module.UsTakeProfitMonitorResponse(
            hasOpenBuy=True,
            sourceOrderId=1,
            symbol="LIMN",
            exchange="ND",
            targetProfitPct=2.0,
            stopLossPct=2.0,
            entryReferencePrice=0.15,
            actualFillPrice=0.16,
            targetPrice=0.1632,
            stopLossPrice=0.1568,
            latestPrice=0.158,
            targetReached=False,
            stopLossTriggered=False,
            spreadToTargetPct=3.1863,
            spreadToStopLossPct=0.7653,
            quoteTrId="realtime-window",
            sellTicketReady=False,
            blockedReasons=["TARGET_PRICE_NOT_REACHED"],
            source="fixture",
            updatedAt="2026-07-16T12:01:00+09:00",
        )

    monkeypatch.setattr(order_module.us_order_service, "get_take_profit_monitor", fake_monitor)

    result = asyncio.run(order_module.us_order_service.run_auto_exit_tick())

    assert result.enabled is True
    assert result.action == "monitoring"
    assert result.sourceOrderId == 1
    row = order_module._latest_armed_buy_row()
    assert row is not None
    assert int(row["auto_exit_armed"]) == 1


def test_us_auto_exit_tick_reconciles_old_buy_missing_from_holdings(monkeypatch, tmp_path):
    from app.schemas.us_order import UsOrderRequest, UsOrderResponse
    from app.services import us_order_service as order_module

    monkeypatch.setenv("KIWOOM_MODE", "live")
    monkeypatch.setenv("KIWOOM_US_AUTO_EXIT_ENABLED", "true")
    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(tmp_path / "orders.sqlite3"))
    get_settings.cache_clear()
    monkeypatch.setattr(order_module, "_auto_trade_runtime_enabled", True)

    buy_payload = UsOrderRequest(
        side="buy",
        exchange="ND",
        symbol="OLDX",
        quantity=1,
        referencePrice="1.00",
        tradeType="03",
        confirmText="",
    )
    buy_result = UsOrderResponse(
        trId="ust20000",
        side="buy",
        code="OLDX",
        exchange="ND",
        returnCode="0",
        returnMessage="OK",
        orderNo="old-buy-order",
        source="fixture",
        updatedAt="2026-07-16T12:00:00+09:00",
    )
    order_module._record_order_attempt(buy_payload, buy_result)
    connection = order_module._connect_order_db()
    try:
        connection.execute("UPDATE us_order_attempts SET created_at = ?", ("2026-07-16T00:00:00+00:00",))
        connection.commit()
    finally:
        connection.close()

    async def no_holdings(**kwargs):
        return []

    async def monitor_must_not_run(**kwargs):
        raise AssertionError("stale buy should be reconciled before quote monitoring")

    monkeypatch.setattr(order_module.us_account_service, "get_holdings_for_order", no_holdings)
    monkeypatch.setattr(order_module.us_order_service, "get_take_profit_monitor", monitor_must_not_run)

    result = asyncio.run(order_module.us_order_service.run_auto_exit_tick())

    assert result.action == "idle"
    assert "NO_ARMED_BUY_ORDER" in result.blockedReasons
    assert order_module._latest_armed_buy_row() is None
    events = asyncio.run(order_module.us_order_service.list_auto_trade_events(5))
    assert events[0].action == "auto_exit"
    assert events[0].status == "reconciled"
    assert "HOLDING_NOT_FOUND" in events[0].blockedReasons


def test_us_armed_buy_reconciliation_respects_actual_sellable_quantity(monkeypatch, tmp_path):
    from app.schemas.us_account import UsHoldingForOrder
    from app.schemas.us_order import UsOrderRequest, UsOrderResponse
    from app.services import us_order_service as order_module

    monkeypatch.setenv("KIWOOM_MODE", "live")
    monkeypatch.setenv("KIWOOM_US_AUTO_EXIT_ENABLED", "true")
    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(tmp_path / "orders.sqlite3"))
    get_settings.cache_clear()

    for order_no in ("buy-one", "buy-two"):
        payload = UsOrderRequest(
            side="buy",
            exchange="ND",
            symbol="SAFE",
            quantity=1,
            referencePrice="1.00",
            tradeType="03",
            confirmText="I_UNDERSTAND_LIVE_US_ORDER",
        )
        result = UsOrderResponse(
            trId="ust20000",
            side="buy",
            code="SAFE",
            exchange="ND",
            returnCode="0",
            returnMessage="OK",
            orderNo=order_no,
            source="fixture",
            updatedAt="2026-07-16T12:00:00+09:00",
        )
        order_module._record_order_attempt(payload, result)

    connection = order_module._connect_order_db()
    try:
        connection.execute("UPDATE us_order_attempts SET created_at = ?", ("2026-07-16T00:00:00+00:00",))
        connection.commit()
    finally:
        connection.close()

    async def one_share_holding(**kwargs):
        return [UsHoldingForOrder(symbol="SAFE", exchange="ND", sellableQuantity=1, blockedReasons=[])]

    monkeypatch.setattr(order_module.us_account_service, "get_holdings_for_order", one_share_holding)

    reconciled = asyncio.run(order_module._reconcile_stale_armed_buy_rows())
    remaining = order_module._armed_buy_rows()

    assert reconciled == 1
    assert len(remaining) == 1
    assert int(remaining[0]["id"]) == 2


def test_us_autotrade_enable_allows_confirm_bypass_for_entry_precheck(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from app.schemas.us_order import UsOrderRequest
    from app.services import us_order_service as order_module

    monkeypatch.setenv("KIWOOM_US_ENABLE_ORDER", "true")
    monkeypatch.setenv("KIWOOM_READ_ONLY", "false")
    monkeypatch.setenv("KIWOOM_US_ORDER_CONFIRM", "I_UNDERSTAND_LIVE_US_ORDER")
    monkeypatch.setenv("KIWOOM_US_LIVE_ORDER_UNLOCK", "I_ACCEPT_REAL_US_ORDER_RISK")
    monkeypatch.setenv("KIWOOM_US_ALLOW_ALL_COMMON_STOCKS", "true")
    monkeypatch.setenv("KIWOOM_US_COMMON_STOCK_ONLY", "true")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_QUANTITY", "1")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_KRW", "30000")
    monkeypatch.setenv("KIWOOM_US_ORDER_USD_KRW_RATE", "1400")
    monkeypatch.setenv("KIWOOM_US_ORDER_RUNTIME_LOCK_FILE", str(tmp_path / "runtime.lock"))

    monkeypatch.setattr(order_module, "get_active_kiwoom_session", lambda: SimpleNamespace(mode="live", safe_account_label="****-0000"))
    monkeypatch.setattr(order_module, "_runtime_order_locked", lambda: False)

    async def fake_execute(tr_id, body=None):
        if tr_id == "usa10100":
            return SimpleNamespace(data={"isEtf": "N", "stk_nm": "LIMN", "stk_enm": "LIMINATUS PHARMA"})
        if tr_id == "ust31490":
            return SimpleNamespace(data={"min_ord_alowq": "1", "min_ord_alowa": "10", "crnc_code": "USD"})
        raise AssertionError(tr_id)

    monkeypatch.setattr(order_module.us_account_service, "_execute", fake_execute)
    monkeypatch.setattr(order_module, "_auto_trade_runtime_enabled", False)

    enable_status = asyncio.run(order_module.us_order_service.enable_auto_trade())
    assert enable_status.enabled is True
    assert enable_status.entryConfirmBypassEnabled is True

    payload = UsOrderRequest(
        side="buy",
        exchange="ND",
        symbol="LIMN",
        quantity=1,
        referencePrice="0.15",
        tradeType="03",
        confirmText="",
    )
    precheck = asyncio.run(order_module.us_order_service.precheck_order(payload))

    assert "CONFIRM_TEXT_REQUIRED" not in precheck.blockedReasons
    assert precheck.canSubmit is True


def test_us_autotrade_status_exposes_backend_runner_state(monkeypatch, tmp_path):
    from app.services import us_order_service as order_module

    monkeypatch.setenv("KIWOOM_US_AUTOTRADE_RUNNER_ENABLED", "true")
    monkeypatch.setenv("KIWOOM_US_AUTOTRADE_RUNNER_INTERVAL_SECONDS", "7")
    monkeypatch.setenv("KIWOOM_US_ORDER_RUNTIME_LOCK_FILE", str(tmp_path / "runtime.lock"))
    monkeypatch.setattr(order_module, "_auto_trade_runtime_enabled", False)

    status = asyncio.run(order_module.us_order_service.get_auto_trade_status())

    assert status.enabled is False
    assert status.runnerEnabled is True
    assert status.runnerMode == "observe"
    assert status.runnerIntervalSeconds == 7
    assert status.runnerRunning is False
    assert status.runnerTickCount >= 0

    asyncio.run(order_module.us_order_service.disable_auto_trade())


def test_us_autotrade_single_toggle_unlocks_on_enable_and_locks_on_disable(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from app.services import us_order_service as order_module

    lock_file = tmp_path / "runtime.lock"
    lock_file.write_text("locked\n", encoding="utf-8")
    monkeypatch.setenv("KIWOOM_US_ORDER_RUNTIME_LOCK_FILE", str(lock_file))
    monkeypatch.setenv("KIWOOM_US_ENABLE_ORDER", "true")
    monkeypatch.setenv("KIWOOM_READ_ONLY", "false")
    monkeypatch.setenv("KIWOOM_US_ORDER_CONFIRM", "I_UNDERSTAND_LIVE_US_ORDER")
    monkeypatch.setenv("KIWOOM_US_LIVE_ORDER_UNLOCK", "I_ACCEPT_REAL_US_ORDER_RISK")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_QUANTITY", "1")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_KRW", "30000")
    monkeypatch.setenv("KIWOOM_US_ORDER_USD_KRW_RATE", "1400")
    monkeypatch.setattr(
        order_module,
        "get_active_kiwoom_session",
        lambda: SimpleNamespace(mode="live", safe_account_label="****-0000"),
    )
    monkeypatch.setattr(order_module, "_auto_trade_runtime_enabled", False)

    enabled = asyncio.run(order_module.us_order_service.enable_auto_trade())

    assert enabled.enabled is True
    assert enabled.blockedReasons == []
    assert lock_file.exists() is False

    disabled = asyncio.run(order_module.us_order_service.disable_auto_trade())

    assert disabled.enabled is False
    assert disabled.blockedReasons == []
    assert lock_file.exists() is True


def test_us_autotrade_observation_keeps_runtime_locked_and_never_places_order(monkeypatch, tmp_path):
    from app.services import us_order_service as order_module

    lock_file = tmp_path / "runtime.lock"
    monkeypatch.setenv("KIWOOM_US_ORDER_RUNTIME_LOCK_FILE", str(lock_file))
    monkeypatch.setattr(order_module, "_auto_trade_runtime_enabled", False)
    monkeypatch.setattr(order_module, "_auto_trade_observation_enabled", False)

    async def no_plans(_service):
        return []

    async def unexpected_order(_payload):
        raise AssertionError("observation mode must never place an order")

    monkeypatch.setattr(order_module, "_auto_entry_candidate_plans", no_plans)
    monkeypatch.setattr(order_module.us_order_service, "place_order", unexpected_order)

    status = asyncio.run(order_module.us_order_service.enable_auto_trade_observation())
    tick = asyncio.run(order_module.us_order_service.run_auto_entry_observation_tick())

    assert status.enabled is False
    assert status.observationEnabled is True
    assert status.mode == "observe"
    assert lock_file.exists() is True
    assert tick.enabled is True
    assert tick.action == "waiting"
    assert tick.blockedReasons == ["AUTO_TRADE_PLAN_EMPTY"]


def test_us_autotrade_runner_evaluates_observation_without_order_stages(monkeypatch):
    from types import SimpleNamespace

    from app.services import autotrade_runner as runner_module

    monkeypatch.setenv("KIWOOM_US_AUTOTRADE_RUNNER_ENABLED", "true")
    monkeypatch.setenv("KIWOOM_US_ENABLE_ORDER", "false")
    monkeypatch.setenv("KIWOOM_READ_ONLY", "true")

    calls = {"observe": 0, "entry": 0, "exit": 0}
    recorded = []
    monkeypatch.setattr(runner_module, "_runner_last_observation_signature", None)

    class ObservationStatus:
        enabled = False
        observationEnabled = True

    async def observation_status():
        return ObservationStatus()

    async def observation_tick():
        calls["observe"] += 1
        return SimpleNamespace(
            action="waiting",
            strategy="observe-test",
            symbol="SAFE",
            exchange="ND",
            failedCriteria=["pullback_depth"],
            blockedReasons=["ENTRY_CONDITIONS_NOT_READY"],
            updatedAt="2026-07-31T22:00:00+09:00",
        )

    async def unexpected_entry():
        calls["entry"] += 1

    async def unexpected_exit():
        calls["exit"] += 1

    def record_observation(result):
        recorded.append(result.strategy)

    async def stop_after_tick(_timeout: float):
        raise asyncio.CancelledError

    monkeypatch.setattr(runner_module.us_order_service, "get_auto_trade_status", observation_status)
    monkeypatch.setattr(runner_module.us_order_service, "run_auto_entry_observation_tick", observation_tick)
    monkeypatch.setattr(runner_module.us_order_service, "run_auto_entry_tick", unexpected_entry)
    monkeypatch.setattr(runner_module.us_order_service, "run_auto_exit_tick", unexpected_exit)
    monkeypatch.setattr(runner_module.us_order_service, "record_observation_result", record_observation)
    monkeypatch.setattr(runner_module.us_condition_service, "wait_for_entry_signal", stop_after_tick)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(runner_module._autotrade_runner_loop())

    assert calls == {"observe": 1, "entry": 0, "exit": 0}
    assert recorded == ["observe-test"]
    snapshot = runner_module.autotrade_runner_status()
    assert snapshot["runnerLastObservationStrategy"] == "observe-test"
    assert snapshot["runnerLastObservationBlockedReasons"] == ["ENTRY_CONDITIONS_NOT_READY"]
    assert snapshot["runnerLastObservationFailedCriteria"] == ["pullback_depth"]


def test_us_autotrade_observation_history_records_safe_change_only(monkeypatch, tmp_path):
    from app.schemas.us_order import UsAutoEntryTickResponse
    from app.services import us_order_service as order_module

    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(tmp_path / "observation.sqlite3"))
    result = UsAutoEntryTickResponse(
        enabled=True,
        action="waiting",
        strategy="safe-observation",
        symbol="SAFE",
        exchange="ND",
        failedCriteria=["pullback_depth"],
        blockedReasons=["ENTRY_CONDITIONS_NOT_READY"],
        source="test",
        updatedAt="2026-08-01T00:00:00+09:00",
    )

    order_module.us_order_service.record_observation_result(result)
    events = asyncio.run(order_module.us_order_service.list_auto_trade_events(limit=5))

    assert events[0].action == "entry_observation"
    assert events[0].status == "waiting"
    assert events[0].strategy == "safe-observation"
    assert events[0].blockedReasons == [
        "ENTRY_CONDITIONS_NOT_READY",
        "CRITERION_PULLBACK_DEPTH",
    ]


def test_us_autotrade_observation_stats_group_safe_state_changes(monkeypatch, tmp_path):
    from app.schemas.us_order import UsAutoEntryTickResponse
    from app.services import us_order_service as order_module

    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(tmp_path / "observation-stats.sqlite3"))
    results = [
        UsAutoEntryTickResponse(
            enabled=True,
            action="waiting",
            strategy="strategy-a",
            symbol="AAA",
            exchange="ND",
            failedCriteria=["pullback_depth"],
            blockedReasons=["ENTRY_CONDITIONS_NOT_READY"],
            source="test",
            updatedAt="2026-08-01T00:00:00+09:00",
        ),
        UsAutoEntryTickResponse(
            enabled=True,
            action="waiting",
            strategy="strategy-a",
            symbol="BBB",
            exchange="NY",
            failedCriteria=["pullback_depth", "volume"],
            blockedReasons=["ENTRY_CONDITIONS_NOT_READY"],
            source="test",
            updatedAt="2026-08-01T00:00:01+09:00",
        ),
        UsAutoEntryTickResponse(
            enabled=True,
            action="ready",
            strategy="strategy-a",
            symbol="AAA",
            exchange="ND",
            failedCriteria=[],
            blockedReasons=[],
            source="test",
            updatedAt="2026-08-01T00:00:02+09:00",
        ),
    ]
    for result in results:
        order_module.us_order_service.record_observation_result(result)

    stats = asyncio.run(order_module.us_order_service.get_observation_stats())

    assert stats.totalStateChanges == 3
    assert len(stats.strategies) == 1
    strategy = stats.strategies[0]
    assert strategy.strategy == "strategy-a"
    assert strategy.readyChanges == 1
    assert strategy.waitingChanges == 2
    assert strategy.uniqueCandidateCount == 2
    assert [(item.criterion, item.count) for item in strategy.topFailedCriteria] == [
        ("pullback_depth", 2),
        ("volume", 1),
    ]


def test_readonly_runner_uses_observation_mode_and_does_not_execute_orders(monkeypatch):
    from app.services import autotrade_runner as runner_module

    monkeypatch.setenv("KIWOOM_US_AUTOTRADE_RUNNER_ENABLED", "true")
    monkeypatch.setenv("KIWOOM_READ_ONLY", "true")
    monkeypatch.setenv("KIWOOM_US_ENABLE_ORDER", "false")
    async def unexpected_order_call():
        raise AssertionError("disabled runner must not call order execution")

    monkeypatch.setattr(runner_module.us_order_service, "run_auto_entry_tick", unexpected_order_call)
    monkeypatch.setattr(runner_module.us_order_service, "run_auto_exit_tick", unexpected_order_call)

    assert runner_module.autotrade_runner_mode() == "observe"


def test_readonly_runner_restores_opt_in_observation_on_start(monkeypatch, tmp_path):
    from app.services import autotrade_runner as runner_module
    from app.services import us_order_service as order_module

    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(tmp_path / "observation-autostart.sqlite3"))
    monkeypatch.setenv("KIWOOM_US_AUTOTRADE_RUNNER_ENABLED", "true")
    monkeypatch.setenv("KIWOOM_US_AUTOTRADE_OBSERVATION_ENABLED", "true")
    monkeypatch.setenv("KIWOOM_READ_ONLY", "true")
    monkeypatch.setenv("KIWOOM_US_ENABLE_ORDER", "false")
    monkeypatch.setattr(order_module, "_auto_trade_runtime_enabled", False)
    monkeypatch.setattr(order_module, "_auto_trade_observation_enabled", False)
    monkeypatch.setattr(runner_module, "_runner_task", None)

    async def dormant_loop():
        await asyncio.Event().wait()

    monkeypatch.setattr(runner_module, "_autotrade_runner_loop", dormant_loop)

    async def scenario():
        await runner_module.start_autotrade_runner()
        status = await order_module.us_order_service.get_auto_trade_status()
        await runner_module.stop_autotrade_runner()
        return status

    status = asyncio.run(scenario())

    assert runner_module.autotrade_observation_autostart_configured() is True
    assert status.observationEnabled is True
    assert status.enabled is False
    assert status.runnerMode == "observe"
    assert order_module._runtime_order_locked() is True


def test_live_runner_never_autostarts_observation(monkeypatch):
    from app.services import autotrade_runner as runner_module

    monkeypatch.setenv("KIWOOM_US_AUTOTRADE_RUNNER_ENABLED", "true")
    monkeypatch.setenv("KIWOOM_US_AUTOTRADE_OBSERVATION_ENABLED", "true")
    monkeypatch.setenv("KIWOOM_READ_ONLY", "false")
    monkeypatch.setenv("KIWOOM_US_ENABLE_ORDER", "true")

    assert runner_module.autotrade_runner_mode() == "live"
    assert runner_module.autotrade_observation_autostart_configured() is False


def test_us_auto_entry_tick_submits_second_symbol_while_first_is_monitored(
    monkeypatch,
    tmp_path,
):
    from types import SimpleNamespace

    from app.schemas.market import (
        MarketRankItem,
        UsAutoTradeOrderTicket,
        UsAutoTradePlanResponse,
    )
    from app.schemas.us_order import UsOrderResponse
    from app.services import us_order_service as order_module
    from app.services import market_ranking_service as ranking_module
    from trading_engine.risk.allocation_store import CapitalAllocationStore
    from trading_engine.risk.capital_allocator import (
        CapitalAllocationState,
        evaluate_capital_allocation,
    )
    from trading_engine.services.market_time import market_time_context

    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(tmp_path / "orders.sqlite3"))
    monkeypatch.setenv("KIWOOM_US_AUTO_EXIT_ENABLED", "true")
    monkeypatch.setenv("KIWOOM_US_ENABLE_ORDER", "true")
    monkeypatch.setenv("KIWOOM_READ_ONLY", "false")
    monkeypatch.setenv("KIWOOM_US_ORDER_CONFIRM", "I_UNDERSTAND_LIVE_US_ORDER")
    monkeypatch.setenv("KIWOOM_US_LIVE_ORDER_UNLOCK", "I_ACCEPT_REAL_US_ORDER_RISK")
    monkeypatch.setenv("KIWOOM_US_ALLOW_ALL_COMMON_STOCKS", "true")
    monkeypatch.setenv("KIWOOM_US_COMMON_STOCK_ONLY", "true")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_QUANTITY", "1")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_KRW", "30000")
    monkeypatch.setenv("KIWOOM_US_ORDER_USD_KRW_RATE", "1400")
    get_settings.cache_clear()

    monkeypatch.setattr(order_module, "get_active_kiwoom_session", lambda: SimpleNamespace(mode="live", safe_account_label="****-0000"))
    monkeypatch.setattr(order_module, "_runtime_order_locked", lambda: False)
    monkeypatch.setattr(order_module, "_auto_trade_runtime_enabled", True)

    first_buy_payload = order_module.UsOrderRequest(
        side="buy",
        exchange="ND",
        symbol="FIRST",
        quantity=1,
        referencePrice="0.15",
        tradeType="03",
        confirmText="",
        reason="auto_entry_kiwoom-condition-001",
    )
    first_buy_result = UsOrderResponse(
        trId="ust20000",
        side="buy",
        code="FIRST",
        exchange="ND",
        returnCode="0",
        returnMessage="OK",
        orderNo="first-entry-order",
        source="fixture",
        updatedAt=datetime.now(timezone.utc).isoformat(),
    )
    order_module._record_order_attempt(
        first_buy_payload,
        first_buy_result,
    )
    allocation_store = CapitalAllocationStore(
        tmp_path / "orders.sqlite3"
    )
    allocation_cycle = allocation_store.ensure_cycle(
        account_scope=order_module._allocation_account_scope(
            "live",
            "****-0000",
        ),
        market_date=market_time_context().us_market_date,
        orderable_cash=10,
    )
    first_allocation = evaluate_capital_allocation(
        state=CapitalAllocationState(
            cycle_capital=10,
            orderable_cash=10,
        ),
        symbol="FIRST",
        reference_price=0.15,
        max_quantity=1,
    )
    first_reservation = allocation_store.reserve(
        cycle=allocation_cycle,
        decision=first_allocation,
        strategy="kiwoom-condition-001",
        exchange="ND",
        reference_price=0.15,
    )
    allocation_store.mark_submitted(
        first_reservation.id,
        "first-entry-order",
    )
    allocation_store.mark_filled(first_reservation.id)
    assert order_module._link_order_attempt_allocation(
        order_no="first-entry-order",
        symbol="FIRST",
        exchange="ND",
        reservation_id=first_reservation.id,
    )

    async def fake_execute(tr_id, body=None):
        if tr_id == "usa10100":
            return SimpleNamespace(data={"isEtf": "N", "stk_nm": "LIMN", "stk_enm": "LIMINATUS PHARMA"})
        if tr_id == "ust31490":
            return SimpleNamespace(data={"min_ord_alowq": "1", "min_ord_alowa": "10", "crnc_code": "USD"})
        raise AssertionError(tr_id)

    async def fake_plan():
        ticket = UsAutoTradeOrderTicket(
            side="buy",
            exchange="ND",
            symbol="LIMN",
            quantity=1,
            tradeType="03",
            referencePrice=0.15,
            targetProfitPct=2.0,
            takeProfitPrice=0.153,
            submitEndpoint="/api/us/orders",
            submitBlocked=False,
            submitBlockReason="",
        )
        return UsAutoTradePlanResponse(
            source="fixture",
            strategy="kiwoom-condition-003",
            rankingTrId="usa20910",
            chartTrId="usa06011",
            orderPrecheckTrId="ust31490",
            updatedAt="2026-07-16T12:00:00+09:00",
            targetRank=3,
            target=MarketRankItem(rank=3, code="LIMN", name="LIMN", price=0.15, changeRate=10.0, volume=200000, exchange="ND", reason="fixture"),
            criteria=[],
            readyForEntry=True,
            orderTicket=ticket,
            oneShareProcessReady=True,
            liveOrderBlockedReasons=[],
            executionState="entry_ready",
            nextAction="fixture",
        )

    placed: dict[str, object] = {}

    async def fake_place_order(payload):
        placed["payload"] = payload
        result = UsOrderResponse(
            trId="ust20000",
            side="buy",
            code=payload.symbol,
            exchange=payload.exchange,
            returnCode="0",
            returnMessage="OK",
            orderNo="entry-order-no",
            source="fixture",
            updatedAt="2026-07-16T12:00:01+09:00",
        )
        order_module._record_order_attempt(payload, result)
        return result

    monkeypatch.setattr(order_module.us_account_service, "_execute", fake_execute)
    monkeypatch.setattr(ranking_module.market_ranking_service, "get_us_pullback_auto_trade_plan", fake_plan)
    monkeypatch.setattr(order_module.us_order_service, "place_order", fake_place_order)

    result = asyncio.run(order_module.us_order_service.run_auto_entry_tick())

    assert result.enabled is True
    assert result.action == "submitted"
    assert result.trId == "ust20000"
    assert result.entryOrderNo == "entry-order-no"
    assert result.allocationCycleId is not None
    assert result.allocationReservationId is not None
    assert result.positionSlot == 2
    assert result.tranche == 1
    assert result.reservedNotional == 0.15
    payload = placed["payload"]
    assert payload.side == "buy"
    assert payload.symbol == "LIMN"
    assert payload.quantity == 1
    assert payload.confirmText == ""
    reservations = CapitalAllocationStore(tmp_path / "orders.sqlite3").list_reservations(
        result.allocationCycleId
    )
    assert len(reservations) == 2
    assert {
        item.symbol: item.status
        for item in reservations
    } == {"FIRST": "filled", "LIMN": "submitted"}
    assert next(
        item
        for item in reservations
        if item.symbol == "LIMN"
    ).order_no == "entry-order-no"
    connection = order_module._connect_order_db()
    try:
        linked_row = connection.execute(
            """
            SELECT allocation_reservation_id
            FROM us_order_attempts
            WHERE order_no = 'entry-order-no'
            LIMIT 1
            """
        ).fetchone()
    finally:
        connection.close()
    assert int(linked_row["allocation_reservation_id"]) == int(
        result.allocationReservationId
    )


def test_submitted_allocation_reservation_is_filled_only_after_matching_fill(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from app.services import us_order_service as order_module
    from trading_engine.risk.allocation_store import CapitalAllocationStore
    from trading_engine.risk.capital_allocator import (
        CapitalAllocationState,
        evaluate_capital_allocation,
    )
    from trading_engine.services.market_time import market_time_context

    db_path = tmp_path / "orders.sqlite3"
    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(db_path))
    account_scope = order_module._allocation_account_scope("live", "****-0000")
    store = CapitalAllocationStore(db_path)
    cycle = store.ensure_cycle(
        account_scope=account_scope,
        market_date=market_time_context().us_market_date,
        orderable_cash=4_000,
    )
    decision = evaluate_capital_allocation(
        state=CapitalAllocationState(cycle_capital=4_000, orderable_cash=4_000),
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
    store.mark_submitted(reservation.id, "matching-order")

    async def fake_fills(*, symbol=None, exchange=None, side="0"):
        assert symbol == "NVDA"
        assert exchange == "ND"
        assert side == "2"
        return SimpleNamespace(
            data={
                "result_list": [
                    {
                        "ord_no": "other-order",
                        "stk_code": "NVDA",
                        "cntr_qty": "1",
                    },
                    {
                        "ord_no": "matching-order",
                        "stk_code": "NVDA",
                        "cntr_qty": "1",
                    },
                ]
            }
        )

    monkeypatch.setattr(order_module.us_account_service, "get_today_order_fills", fake_fills)

    reconciled = asyncio.run(
        order_module._reconcile_submitted_allocation_reservations(
            session_mode="live",
            safe_account_label="****-0000",
        )
    )
    restored = CapitalAllocationStore(db_path)
    reservations = restored.list_reservations(cycle.id)
    state = restored.load_state(cycle=cycle, orderable_cash=3_900)

    assert reconciled == 1
    assert reservations[0].status == "filled"
    assert state.pending_symbols == frozenset()
    assert state.filled_tranches == {"NVDA": 1}


def test_canceled_allocation_reservation_releases_cash_after_ust21050_confirmation(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from app.services import us_order_service as order_module
    from trading_engine.risk.allocation_store import CapitalAllocationStore
    from trading_engine.risk.capital_allocator import (
        CapitalAllocationState,
        evaluate_capital_allocation,
    )
    from trading_engine.services.market_time import market_time_context

    db_path = tmp_path / "orders.sqlite3"
    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(db_path))
    store = CapitalAllocationStore(db_path)
    cycle = store.ensure_cycle(
        account_scope=order_module._allocation_account_scope("live", "****-0000"),
        market_date=market_time_context().us_market_date,
        orderable_cash=4_000,
    )
    decision = evaluate_capital_allocation(
        state=CapitalAllocationState(cycle_capital=4_000, orderable_cash=4_000),
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
    store.mark_submitted(reservation.id, "original-order")

    async def no_fills(**kwargs):
        return SimpleNamespace(data={"result_list": []})

    async def canceled_order(**kwargs):
        return SimpleNamespace(
            data={
                "result_list": [
                    {
                        "ord_cntr_tp": "12",
                        "ord_no": "cancel-order",
                        "orig_ord_no": "original-order",
                        "stk_code": "NVDA",
                        "cntr_qty": "0",
                        "cncl_qty": "1",
                        "ord_remnq": "0",
                        "ord_stat": "취소완료",
                    }
                ]
            }
        )

    monkeypatch.setattr(order_module.us_account_service, "get_today_order_fills", no_fills)
    monkeypatch.setattr(order_module.us_account_service, "get_open_orders", canceled_order)

    reconciled = asyncio.run(
        order_module._reconcile_submitted_allocation_reservations(
            session_mode="live",
            safe_account_label="****-0000",
        )
    )
    reservations = store.list_reservations(cycle.id)
    state = store.load_state(cycle=cycle, orderable_cash=4_000)

    assert reconciled == 1
    assert reservations[0].status == "released"
    assert state.reserved_cash == 0
    assert state.open_symbols == frozenset()


def test_missing_ust21050_row_keeps_allocation_reserved(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from app.services import us_order_service as order_module
    from trading_engine.risk.allocation_store import CapitalAllocationStore
    from trading_engine.risk.capital_allocator import (
        CapitalAllocationState,
        evaluate_capital_allocation,
    )
    from trading_engine.services.market_time import market_time_context

    db_path = tmp_path / "orders.sqlite3"
    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(db_path))
    store = CapitalAllocationStore(db_path)
    cycle = store.ensure_cycle(
        account_scope=order_module._allocation_account_scope("live", "****-0000"),
        market_date=market_time_context().us_market_date,
        orderable_cash=4_000,
    )
    decision = evaluate_capital_allocation(
        state=CapitalAllocationState(cycle_capital=4_000, orderable_cash=4_000),
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
    store.mark_submitted(reservation.id, "uncertain-order")

    async def empty_summary(**kwargs):
        return SimpleNamespace(data={"result_list": []})

    monkeypatch.setattr(order_module.us_account_service, "get_today_order_fills", empty_summary)
    monkeypatch.setattr(order_module.us_account_service, "get_open_orders", empty_summary)

    reconciled = asyncio.run(
        order_module._reconcile_submitted_allocation_reservations(
            session_mode="live",
            safe_account_label="****-0000",
        )
    )
    reservations = store.list_reservations(cycle.id)
    state = store.load_state(cycle=cycle, orderable_cash=4_000)

    assert reconciled == 0
    assert reservations[0].status == "submitted"
    assert state.reserved_cash == 100
    assert state.pending_symbols == frozenset({"NVDA"})


def test_submitted_order_reconciliation_is_rate_limited(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from app.services import us_order_service as order_module
    from trading_engine.risk.allocation_store import CapitalAllocationStore
    from trading_engine.risk.capital_allocator import (
        CapitalAllocationState,
        evaluate_capital_allocation,
    )
    from trading_engine.services.market_time import market_time_context

    db_path = tmp_path / "orders.sqlite3"
    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(db_path))
    monkeypatch.setenv(
        "KIWOOM_US_ORDER_RECONCILE_INTERVAL_SECONDS",
        "5",
    )
    store = CapitalAllocationStore(db_path)
    cycle = store.ensure_cycle(
        account_scope=order_module._allocation_account_scope(
            "live",
            "****-0000",
        ),
        market_date=market_time_context().us_market_date,
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
    store.mark_submitted(reservation.id, "pending-order")
    calls = {"fills": 0, "open": 0}

    async def empty_fills(**kwargs):
        calls["fills"] += 1
        return SimpleNamespace(data={"result_list": []})

    async def empty_open_orders(**kwargs):
        calls["open"] += 1
        return SimpleNamespace(data={"result_list": []})

    monkeypatch.setattr(
        order_module.us_account_service,
        "get_today_order_fills",
        empty_fills,
    )
    monkeypatch.setattr(
        order_module.us_account_service,
        "get_open_orders",
        empty_open_orders,
    )
    first = asyncio.run(
        order_module._reconcile_submitted_allocation_reservations(
            session_mode="live",
            safe_account_label="****-0000",
        )
    )
    second = asyncio.run(
        order_module._reconcile_submitted_allocation_reservations(
            session_mode="live",
            safe_account_label="****-0000",
        )
    )

    assert first == 0
    assert second == 0
    assert calls == {"fills": 1, "open": 1}
    restored = CapitalAllocationStore(db_path).list_reservations(cycle.id)[0]
    assert restored.last_reconciled_at is not None
    assert restored.reconcile_result == "unresolved"
    assert restored.reconcile_attempts == 1


def test_submitted_order_timeout_remains_blocked(monkeypatch, tmp_path):
    from app.services import us_order_service as order_module
    from trading_engine.risk.allocation_store import CapitalAllocationStore
    from trading_engine.risk.capital_allocator import (
        CapitalAllocationState,
        evaluate_capital_allocation,
    )
    from trading_engine.services.market_time import market_time_context

    db_path = tmp_path / "orders.sqlite3"
    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(db_path))
    monkeypatch.setenv(
        "KIWOOM_US_ORDER_CONFIRMATION_TIMEOUT_SECONDS",
        "30",
    )
    store = CapitalAllocationStore(db_path)
    cycle = store.ensure_cycle(
        account_scope=order_module._allocation_account_scope(
            "live",
            "****-0000",
        ),
        market_date=market_time_context().us_market_date,
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
    store.mark_submitted(reservation.id, "uncertain-order")

    restored = CapitalAllocationStore(db_path).list_reservations(cycle.id)[0]
    submitted_at = datetime.fromisoformat(str(restored.submitted_at))
    monkeypatch.setattr(
        order_module,
        "_utc_now",
        lambda: submitted_at + timedelta(seconds=31),
    )

    blocker = order_module._submitted_order_state_blocker(
        session_mode="live",
        safe_account_label="****-0000",
    )

    assert blocker == "ORDER_STATE_CONFIRMATION_TIMEOUT"
    assert restored.status == "submitted"
    assert restored.submitted_at is not None
    assert store.list_reservations(cycle.id)[0].status == "submitted"


def test_partial_fill_then_cancel_marks_allocation_as_filled(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from app.services import us_order_service as order_module
    from trading_engine.risk.allocation_store import CapitalAllocationStore
    from trading_engine.risk.capital_allocator import (
        CapitalAllocationState,
        evaluate_capital_allocation,
    )
    from trading_engine.services.market_time import market_time_context

    db_path = tmp_path / "orders.sqlite3"
    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(db_path))
    store = CapitalAllocationStore(db_path)
    cycle = store.ensure_cycle(
        account_scope=order_module._allocation_account_scope("live", "****-0000"),
        market_date=market_time_context().us_market_date,
        orderable_cash=4_000,
    )
    decision = evaluate_capital_allocation(
        state=CapitalAllocationState(cycle_capital=4_000, orderable_cash=4_000),
        symbol="NVDA",
        reference_price=100,
        max_quantity=2,
    )
    reservation = store.reserve(
        cycle=cycle,
        decision=decision,
        strategy="strategy-a",
        exchange="ND",
        reference_price=100,
    )
    store.mark_submitted(reservation.id, "partial-order")
    store.record_reconciliation_result(reservation.id, "partial_fill")
    submitted_before_restart = store.list_reservations(cycle.id)[0]
    restarted_store = CapitalAllocationStore(db_path)

    async def partial_fill(**kwargs):
        return SimpleNamespace(
            data={
                "result_list": [
                    {
                        "ord_no": "partial-order",
                        "stk_code": "NVDA",
                        "cntr_qty": "1",
                    }
                ]
            }
        )

    async def canceled_remainder(**kwargs):
        return SimpleNamespace(
            data={
                "result_list": [
                    {
                        "ord_cntr_tp": "12",
                        "orig_ord_no": "partial-order",
                        "stk_code": "NVDA",
                        "cntr_qty": "1",
                        "cncl_qty": "1",
                        "ord_remnq": "0",
                        "ord_stat": "취소완료",
                    }
                ]
            }
        )

    monkeypatch.setattr(order_module.us_account_service, "get_today_order_fills", partial_fill)
    monkeypatch.setattr(order_module.us_account_service, "get_open_orders", canceled_remainder)

    reconciled = asyncio.run(
        order_module._reconcile_submitted_allocation_reservations(
            session_mode="live",
            safe_account_label="****-0000",
            force=True,
        )
    )
    reservations = restarted_store.list_reservations(cycle.id)
    state = restarted_store.load_state(cycle=cycle, orderable_cash=3_900)

    assert reconciled == 1
    assert reservations[0].status == "filled"
    assert reservations[0].filled_quantity == 1
    assert reservations[0].submitted_at == submitted_before_restart.submitted_at
    assert reservations[0].reconcile_result == "canceled_confirmed"
    assert reservations[0].reconcile_attempts == 2
    assert state.reserved_cash == 0
    assert state.filled_tranches == {"NVDA": 1}


def test_rejected_order_after_restart_releases_reservation_and_next_candidate(
    monkeypatch,
    tmp_path,
):
    from types import SimpleNamespace

    from app.services import us_order_service as order_module
    from trading_engine.risk.allocation_store import CapitalAllocationStore
    from trading_engine.risk.capital_allocator import (
        CapitalAllocationState,
        evaluate_capital_allocation,
    )
    from trading_engine.services.market_time import market_time_context

    db_path = tmp_path / "orders.sqlite3"
    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(db_path))
    store = CapitalAllocationStore(db_path)
    cycle = store.ensure_cycle(
        account_scope=order_module._allocation_account_scope(
            "live",
            "****-0000",
        ),
        market_date=market_time_context().us_market_date,
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
    store.mark_submitted(reservation.id, "rejected-order")
    store.record_reconciliation_result(reservation.id, "unresolved")

    async def no_fills(**kwargs):
        return SimpleNamespace(data={"result_list": []})

    async def rejected_order(**kwargs):
        return SimpleNamespace(
            data={
                "result_list": [
                    {
                        "ord_no": "rejected-order",
                        "orig_ord_no": "",
                        "stk_code": "NVDA",
                        "cntr_qty": "0",
                        "cncl_qty": "0",
                        "ord_remnq": "1",
                        "ord_stat": "주문거부",
                    }
                ]
            }
        )

    monkeypatch.setattr(
        order_module.us_account_service,
        "get_today_order_fills",
        no_fills,
    )
    monkeypatch.setattr(
        order_module.us_account_service,
        "get_open_orders",
        rejected_order,
    )

    restarted_store = CapitalAllocationStore(db_path)
    reconciled = asyncio.run(
        order_module._reconcile_submitted_allocation_reservations(
            session_mode="live",
            safe_account_label="****-0000",
            force=True,
        )
    )
    restored = restarted_store.list_reservations(cycle.id)[0]
    state = restarted_store.load_state(
        cycle=cycle,
        orderable_cash=4_000,
    )
    next_decision = evaluate_capital_allocation(
        state=state,
        symbol="AAPL",
        reference_price=200,
        max_quantity=1,
    )

    assert reconciled == 1
    assert restored.status == "released"
    assert restored.reconcile_result == "rejected_confirmed"
    assert restored.reconcile_attempts == 2
    assert state.reserved_cash == 0
    assert state.pending_symbols == frozenset()
    assert next_decision.allowed is True


def test_partial_fill_cancel_without_cancel_quantity_uses_confirmed_zero_remainder(
    monkeypatch,
    tmp_path,
):
    from types import SimpleNamespace

    from app.services import us_order_service as order_module
    from trading_engine.risk.allocation_store import CapitalAllocationStore
    from trading_engine.risk.capital_allocator import (
        CapitalAllocationState,
        evaluate_capital_allocation,
    )
    from trading_engine.services.market_time import market_time_context

    db_path = tmp_path / "orders.sqlite3"
    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(db_path))
    store = CapitalAllocationStore(db_path)
    cycle = store.ensure_cycle(
        account_scope=order_module._allocation_account_scope(
            "live",
            "****-0000",
        ),
        market_date=market_time_context().us_market_date,
        orderable_cash=4_000,
    )
    decision = evaluate_capital_allocation(
        state=CapitalAllocationState(
            cycle_capital=4_000,
            orderable_cash=4_000,
        ),
        symbol="NVDA",
        reference_price=100,
        max_quantity=2,
    )
    reservation = store.reserve(
        cycle=cycle,
        decision=decision,
        strategy="strategy-a",
        exchange="ND",
        reference_price=100,
    )
    store.mark_submitted(reservation.id, "partial-order")

    async def partial_fill(**kwargs):
        return SimpleNamespace(
            data={
                "result_list": [
                    {
                        "ord_no": "partial-order",
                        "stk_code": "NVDA",
                        "cntr_qty": "1",
                    }
                ]
            }
        )

    async def canceled_remainder(**kwargs):
        return SimpleNamespace(
            data={
                "result_list": [
                    {
                        "orig_ord_no": "partial-order",
                        "stk_code": "NVDA",
                        "cntr_qty": "1",
                        "cncl_qty": "",
                        "ord_remnq": "0",
                        "ord_stat": "취소완료",
                    }
                ]
            }
        )

    monkeypatch.setattr(
        order_module.us_account_service,
        "get_today_order_fills",
        partial_fill,
    )
    monkeypatch.setattr(
        order_module.us_account_service,
        "get_open_orders",
        canceled_remainder,
    )

    reconciled = asyncio.run(
        order_module._reconcile_submitted_allocation_reservations(
            session_mode="live",
            safe_account_label="****-0000",
            force=True,
        )
    )
    restored = CapitalAllocationStore(db_path).list_reservations(cycle.id)[0]

    assert reconciled == 1
    assert restored.status == "filled"
    assert restored.filled_quantity == 1
    assert restored.reconcile_result == "canceled_confirmed"
    assert restored.last_broker_status == "취소완료"


def test_us_auto_entry_tick_returns_waiting_without_recording_order_event(monkeypatch, tmp_path):
    from app.schemas.market import MarketRankItem, UsAutoTradePlanResponse
    from app.services import market_ranking_service as ranking_module
    from app.services import us_order_service as order_module

    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(tmp_path / "orders.sqlite3"))
    monkeypatch.setattr(order_module, "_auto_trade_runtime_enabled", True)
    monkeypatch.setattr(order_module, "_latest_armed_buy_row", lambda: None)

    async def fake_plan():
        return UsAutoTradePlanResponse(
            source="fixture",
            strategy="kiwoom-condition-003",
            rankingTrId="usa20910",
            chartTrId="usa06011",
            orderPrecheckTrId="ust31490",
            updatedAt="2026-07-16T12:00:00+09:00",
            targetRank=3,
            target=MarketRankItem(rank=3, code="WAIT", name="WAIT", price=0.15, changeRate=10.0, volume=200000, exchange="ND", reason="fixture"),
            criteria=[],
            readyForEntry=False,
            orderTicket=None,
            oneShareProcessReady=False,
            liveOrderBlockedReasons=["ENTRY_CONDITIONS_NOT_READY"],
            executionState="waiting_conditions",
            nextAction="fixture",
        )

    async def fake_plans_unavailable():
        raise RuntimeError("list plan unavailable")

    monkeypatch.setattr(ranking_module.market_ranking_service, "get_us_pullback_auto_trade_plans", fake_plans_unavailable)
    monkeypatch.setattr(ranking_module.market_ranking_service, "get_us_pullback_auto_trade_plan", fake_plan)

    result = asyncio.run(order_module.us_order_service.run_auto_entry_tick())
    events = asyncio.run(order_module.us_order_service.list_auto_trade_events(limit=10))

    assert result.action == "waiting"
    assert "ENTRY_CONDITIONS_NOT_READY" in result.blockedReasons
    assert not any(event.action == "auto_entry" for event in events)


def test_legacy_empty_auto_entry_block_is_presented_as_waiting(monkeypatch, tmp_path):
    from app.services import us_order_service as order_module

    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(tmp_path / "orders.sqlite3"))
    order_module._record_auto_trade_event(
        action="auto_entry",
        status="blocked",
        side="buy",
        tr_id="ust20000",
        strategy="kiwoom-condition-001",
        blocked_reasons=["ENTRY_CONDITIONS_NOT_READY", "BUY_TICKET_UNAVAILABLE"],
    )

    event = asyncio.run(order_module.us_order_service.list_auto_trade_events(limit=1))[0]

    assert event.action == "auto_entry_tick"
    assert event.status == "skipped"
    assert event.trId is None


def test_us_auto_entry_tick_submits_first_ready_strategy_from_plan_list(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from app.schemas.market import (
        MarketRankItem,
        UsAutoTradeOrderTicket,
        UsAutoTradePlanListResponse,
        UsAutoTradePlanResponse,
    )
    from app.schemas.us_order import UsOrderResponse
    from app.services import market_ranking_service as ranking_module
    from app.services import us_order_service as order_module

    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(tmp_path / "orders.sqlite3"))
    monkeypatch.setenv("KIWOOM_US_ENABLE_ORDER", "true")
    monkeypatch.setenv("KIWOOM_READ_ONLY", "false")
    monkeypatch.setenv("KIWOOM_US_ORDER_CONFIRM", "I_UNDERSTAND_LIVE_US_ORDER")
    monkeypatch.setenv("KIWOOM_US_LIVE_ORDER_UNLOCK", "I_ACCEPT_REAL_US_ORDER_RISK")
    monkeypatch.setenv("KIWOOM_US_ALLOW_ALL_COMMON_STOCKS", "true")
    monkeypatch.setenv("KIWOOM_US_COMMON_STOCK_ONLY", "true")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_QUANTITY", "1")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_KRW", "30000")
    monkeypatch.setenv("KIWOOM_US_ORDER_USD_KRW_RATE", "1400")
    get_settings.cache_clear()

    monkeypatch.setattr(order_module, "get_active_kiwoom_session", lambda: SimpleNamespace(mode="live", safe_account_label="****-0000"))
    monkeypatch.setattr(order_module, "_runtime_order_locked", lambda: False)
    monkeypatch.setattr(order_module, "_auto_trade_runtime_enabled", True)
    monkeypatch.setattr(order_module, "_latest_armed_buy_row", lambda: None)

    async def fake_execute(tr_id, body=None):
        if tr_id == "usa10100":
            return SimpleNamespace(data={"isEtf": "N", "stk_nm": "ONE", "stk_enm": "ONE COMMON"})
        if tr_id == "ust31490":
            return SimpleNamespace(data={"min_ord_alowq": "1", "min_ord_alowa": "10", "crnc_code": "USD"})
        raise AssertionError(tr_id)

    def plan(
        *,
        strategy: str,
        symbol: str,
        ready: bool,
        target_pct: float,
        blockers: list[str] | None = None,
    ) -> UsAutoTradePlanResponse:
        ticket = UsAutoTradeOrderTicket(
            side="buy",
            exchange="ND",
            symbol=symbol,
            quantity=1,
            tradeType="03",
            referencePrice=0.15,
            targetProfitPct=target_pct,
            takeProfitPrice=round(0.15 * (1 + target_pct / 100), 4),
            submitEndpoint="/api/us/orders",
            submitBlocked=not ready,
            submitBlockReason="" if ready else "blocked",
        ) if ready else None
        return UsAutoTradePlanResponse(
            source="fixture",
            strategy=strategy,
            strategyName="fixture",
            timeframe="minute",
            tickScope="1" if "1m" in strategy else "5",
            rankingTrId="usa20910",
            chartTrId="usa06011",
            orderPrecheckTrId="ust31490",
            updatedAt="2026-07-16T12:00:00+09:00",
            targetRank=1 if symbol == "FIVE" else 2,
            target=MarketRankItem(rank=1, code=symbol, name=symbol, price=0.15, changeRate=10.0, volume=400000, exchange="ND", reason="fixture"),
            criteria=[],
            readyForEntry=ready,
            orderTicket=ticket,
            oneShareProcessReady=ready,
            liveOrderBlockedReasons=blockers or ([] if ready else ["ENTRY_CONDITIONS_NOT_READY"]),
            executionState="entry_ready" if ready else "waiting_conditions",
            nextAction="fixture",
        )

    async def fake_plans():
        return UsAutoTradePlanListResponse(
            source="fixture",
            updatedAt="2026-07-16T12:00:00+09:00",
            selectedStrategy="kiwoom-condition-002",
            plans=[
                plan(strategy="kiwoom-condition-001", symbol="FIVE", ready=False, target_pct=5.0),
                plan(strategy="kiwoom-condition-002", symbol="ONE", ready=True, target_pct=3.0),
            ],
        )

    placed: dict[str, object] = {}

    async def fake_place_order(payload):
        placed["payload"] = payload
        return UsOrderResponse(
            trId="ust20000",
            side="buy",
            code=payload.symbol,
            exchange=payload.exchange,
            returnCode="0",
            returnMessage="OK",
            orderNo="entry-order-no",
            source="fixture",
            updatedAt="2026-07-16T12:00:01+09:00",
        )

    monkeypatch.setattr(order_module.us_account_service, "_execute", fake_execute)
    monkeypatch.setattr(ranking_module.market_ranking_service, "get_us_pullback_auto_trade_plans", fake_plans)
    monkeypatch.setattr(order_module.us_order_service, "place_order", fake_place_order)

    result = asyncio.run(order_module.us_order_service.run_auto_entry_tick())
    events = asyncio.run(order_module.us_order_service.list_auto_trade_events(limit=1))

    assert result.action == "submitted"
    assert result.strategy == "kiwoom-condition-002"
    assert result.symbol == "ONE"
    assert result.targetProfitPct == 3.0
    payload = placed["payload"]
    assert payload.reason == "auto_entry_kiwoom-condition-002"
    assert events[0].strategy == "kiwoom-condition-002"


def test_us_autotrade_diagnostics_reports_entry_condition_blocker(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from app.schemas.market import MarketRankItem, UsAutoTradePlanResponse
    from app.services import market_ranking_service as ranking_module
    from app.services import us_order_service as order_module

    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(tmp_path / "orders.sqlite3"))
    monkeypatch.setenv("KIWOOM_US_ENABLE_ORDER", "true")
    monkeypatch.setenv("KIWOOM_READ_ONLY", "false")
    monkeypatch.setenv("KIWOOM_US_ORDER_CONFIRM", "I_UNDERSTAND_LIVE_US_ORDER")
    monkeypatch.setenv("KIWOOM_US_LIVE_ORDER_UNLOCK", "I_ACCEPT_REAL_US_ORDER_RISK")
    monkeypatch.setenv("KIWOOM_US_ALLOW_ALL_COMMON_STOCKS", "true")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_QUANTITY", "1")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_KRW", "30000")
    monkeypatch.setattr(order_module, "get_active_kiwoom_session", lambda: SimpleNamespace(mode="live", safe_account_label="****-0000"))
    monkeypatch.setattr(order_module, "_runtime_order_locked", lambda: False)
    monkeypatch.setattr(order_module, "_auto_trade_runtime_enabled", True)
    monkeypatch.setattr(order_module, "_latest_armed_buy_row", lambda: None)

    async def fake_plan():
        return UsAutoTradePlanResponse(
            source="fixture",
            strategy="kiwoom-condition-003",
            rankingTrId="usa20910",
            chartTrId="usa06011",
            orderPrecheckTrId="ust31490",
            updatedAt="2026-07-16T12:00:00+09:00",
            targetRank=3,
            target=MarketRankItem(rank=3, code="WAIT", name="WAIT", price=0.15, changeRate=10.0, volume=200000, exchange="ND", reason="fixture"),
            criteria=[],
            readyForEntry=False,
            orderTicket=None,
            oneShareProcessReady=False,
            liveOrderBlockedReasons=["ENTRY_CONDITIONS_NOT_READY"],
            executionState="waiting_conditions",
            nextAction="fixture",
        )

    monkeypatch.setattr(ranking_module.market_ranking_service, "get_us_pullback_auto_trade_plan", fake_plan)

    diagnostics = asyncio.run(order_module.us_order_service.get_auto_trade_diagnostics())

    assert diagnostics.decision == "blocked"
    assert diagnostics.blockingStage == "entry_conditions"
    assert diagnostics.canAttemptEntry is False
    assert "ENTRY_CONDITIONS_NOT_READY" in diagnostics.blockerReasons
    assert diagnostics.plan is not None


def test_us_autotrade_diagnostics_reports_entry_ready_while_exit_is_monitored(
    monkeypatch,
    tmp_path,
):
    from types import SimpleNamespace

    from app.schemas.market import MarketRankItem, UsAutoTradeOrderTicket, UsAutoTradePlanResponse
    from app.services import market_ranking_service as ranking_module
    from app.services import us_order_service as order_module

    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(tmp_path / "orders.sqlite3"))
    monkeypatch.setenv("KIWOOM_US_ENABLE_ORDER", "true")
    monkeypatch.setenv("KIWOOM_READ_ONLY", "false")
    monkeypatch.setenv("KIWOOM_US_ORDER_CONFIRM", "I_UNDERSTAND_LIVE_US_ORDER")
    monkeypatch.setenv("KIWOOM_US_LIVE_ORDER_UNLOCK", "I_ACCEPT_REAL_US_ORDER_RISK")
    monkeypatch.setenv("KIWOOM_US_ALLOW_ALL_COMMON_STOCKS", "true")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_QUANTITY", "1")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_KRW", "30000")
    monkeypatch.setattr(order_module, "get_active_kiwoom_session", lambda: SimpleNamespace(mode="live", safe_account_label="****-0000"))
    monkeypatch.setattr(order_module, "_runtime_order_locked", lambda: False)
    monkeypatch.setattr(order_module, "_auto_trade_runtime_enabled", True)
    monkeypatch.setattr(
        order_module,
        "_latest_armed_buy_row",
        lambda: {"id": 1},
    )

    async def fake_plan():
        ticket = UsAutoTradeOrderTicket(
            side="buy",
            exchange="ND",
            symbol="READY",
            quantity=1,
            tradeType="03",
            referencePrice=0.15,
            targetProfitPct=2.0,
            takeProfitPrice=0.153,
            submitEndpoint="/api/us/orders",
            submitBlocked=False,
            submitBlockReason="",
        )
        return UsAutoTradePlanResponse(
            source="fixture",
            strategy="kiwoom-condition-003",
            rankingTrId="usa20910",
            chartTrId="usa06011",
            orderPrecheckTrId="ust31490",
            updatedAt="2026-07-16T12:00:00+09:00",
            targetRank=3,
            target=MarketRankItem(rank=3, code="READY", name="READY", price=0.15, changeRate=10.0, volume=200000, exchange="ND", reason="fixture"),
            criteria=[],
            readyForEntry=True,
            orderTicket=ticket,
            oneShareProcessReady=True,
            liveOrderBlockedReasons=[],
            executionState="entry_ready",
            nextAction="fixture",
        )

    monkeypatch.setattr(ranking_module.market_ranking_service, "get_us_pullback_auto_trade_plan", fake_plan)

    diagnostics = asyncio.run(order_module.us_order_service.get_auto_trade_diagnostics())

    assert diagnostics.decision == "entry_ready"
    assert diagnostics.canAttemptEntry is True
    assert diagnostics.canAttemptExit is True
    assert diagnostics.blockerReasons == []
    assert diagnostics.requiredAction.startswith("기존 포지션 매도를 감시하면서")


def test_us_autotrade_diagnostics_includes_pipeline_counts(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from app.schemas.market import MarketRankItem, UsAutoTradePlanResponse
    from app.services import market_ranking_service as ranking_module
    from app.services import us_order_service as order_module

    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(tmp_path / "orders.sqlite3"))
    monkeypatch.setenv("KIWOOM_US_ENABLE_ORDER", "true")
    monkeypatch.setenv("KIWOOM_READ_ONLY", "false")
    monkeypatch.setenv("KIWOOM_US_ORDER_CONFIRM", "I_UNDERSTAND_LIVE_US_ORDER")
    monkeypatch.setenv("KIWOOM_US_LIVE_ORDER_UNLOCK", "I_ACCEPT_REAL_US_ORDER_RISK")
    monkeypatch.setenv("KIWOOM_US_ALLOW_ALL_COMMON_STOCKS", "true")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_QUANTITY", "1")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_KRW", "30000")
    monkeypatch.setattr(order_module, "get_active_kiwoom_session", lambda: SimpleNamespace(mode="live", safe_account_label="****-0000"))
    monkeypatch.setattr(order_module, "_runtime_order_locked", lambda: False)
    monkeypatch.setattr(order_module, "_auto_trade_runtime_enabled", True)
    monkeypatch.setattr(order_module, "_latest_armed_buy_row", lambda: None)

    async def fake_plan():
        return UsAutoTradePlanResponse(
            source="fixture",
            strategy="kiwoom-condition-003",
            rankingTrId="usa20910",
            chartTrId="usa06011",
            orderPrecheckTrId="ust31490",
            updatedAt="2026-07-16T12:00:00+09:00",
            targetRank=3,
            target=MarketRankItem(rank=3, code="WAIT", name="WAIT", price=0.15, changeRate=10.0, volume=200000, exchange="ND", reason="fixture"),
            criteria=[],
            readyForEntry=False,
            orderTicket=None,
            oneShareProcessReady=False,
            liveOrderBlockedReasons=["ENTRY_CONDITIONS_NOT_READY"],
            executionState="waiting_conditions",
            nextAction="fixture",
        )

    monkeypatch.setattr(ranking_module.market_ranking_service, "get_us_pullback_auto_trade_plan", fake_plan)

    connection = order_module._connect_order_db()
    today = order_module.now_iso()[:10]
    try:
        connection.execute(
            """
            INSERT INTO us_order_attempts(
              tr_id, side, symbol, exchange, quantity, order_price, reference_price,
              trade_type, return_code, return_msg, order_no, created_at
            )
            VALUES ('ust20000', 'buy', 'WAIT', 'ND', 1, '', '0.15', '03', '0', 'OK', 'fixture-order', ?)
            """,
            (f"{today}T01:00:00+00:00",),
        )
        connection.execute(
            """
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
            )
            """
        )
        connection.execute(
            """
            INSERT INTO realtime_quote_events(
              symbol, event_type, provider, price, volume, trade_strength,
              bid, ask, source_event_time, received_at, created_at
            )
            VALUES ('WAIT', 'TICK', 'fixture', 0.15, 1000, NULL, NULL, NULL, ?, ?, ?)
            """,
            (f"{today}T01:00:00+00:00", f"{today}T01:00:00+00:00", f"{today}T01:00:00+00:00"),
        )
        connection.commit()
    finally:
        connection.close()

    diagnostics = asyncio.run(order_module.us_order_service.get_auto_trade_diagnostics())

    assert diagnostics.pipeline.ordersToday == 1
    assert diagnostics.pipeline.realtimeEventsToday == 1
    assert diagnostics.pipeline.eventsToday >= 0
    assert diagnostics.pipeline.dataFlowOk is True
    assert diagnostics.pipeline.orderFlowOk is True


def test_us_autotrade_runner_error_is_recorded_without_secret_values(monkeypatch, tmp_path):
    from app.services import us_order_service as order_module

    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(tmp_path / "orders.sqlite3"))

    order_module.us_order_service.record_runner_error("token secret account leaked")
    events = asyncio.run(order_module.us_order_service.list_auto_trade_events(limit=1))

    assert events[0].action == "runner_tick"
    assert events[0].status == "failed"
    assert events[0].blockedReasons == ["STAGE_RUNNER", "RUNNER_ERROR"]
    assert "secret" not in ",".join(events[0].blockedReasons).lower()


def test_us_autotrade_runner_records_stage_error_without_stopping_loop(monkeypatch, tmp_path):
    from app.services import autotrade_runner as runner_module

    monkeypatch.setenv("TRADING_ENGINE_DB_PATH", str(tmp_path / "orders.sqlite3"))

    async def failing_stage():
        raise RuntimeError("token secret account leaked")

    result = asyncio.run(runner_module._run_autotrade_stage("auto_exit", failing_stage))
    events = asyncio.run(runner_module.us_order_service.list_auto_trade_events(limit=1))

    assert result is False
    assert events[0].action == "runner_auto_exit"
    assert events[0].status == "failed"
    assert events[0].blockedReasons == ["STAGE_AUTO_EXIT", "RUNTIMEERROR", "RUNNER_ERROR"]
    assert "secret" not in ",".join(events[0].blockedReasons).lower()


def test_us_autotrade_runner_wakes_immediately_for_condition_entry(monkeypatch):
    from app.services import autotrade_runner as runner_module

    monkeypatch.setenv("KIWOOM_US_AUTOTRADE_RUNNER_ENABLED", "true")
    monkeypatch.setenv("KIWOOM_US_ENABLE_ORDER", "true")
    monkeypatch.setenv("KIWOOM_READ_ONLY", "false")
    monkeypatch.setattr(runner_module, "_runner_condition_wake_count", 0)
    monkeypatch.setattr(runner_module, "_runner_last_wake_reason", "startup")

    calls = {"entry": 0, "exit": 0, "wait": 0}

    class EnabledStatus:
        enabled = True

    async def enabled_status():
        return EnabledStatus()

    async def entry_tick():
        calls["entry"] += 1

    async def exit_tick():
        calls["exit"] += 1

    async def wait_for_entry_signal(timeout: float):
        assert timeout > 0
        calls["wait"] += 1
        if calls["wait"] == 1:
            return True
        raise asyncio.CancelledError

    monkeypatch.setattr(runner_module.us_order_service, "get_auto_trade_status", enabled_status)
    monkeypatch.setattr(runner_module.us_order_service, "run_auto_entry_tick", entry_tick)
    monkeypatch.setattr(runner_module.us_order_service, "run_auto_exit_tick", exit_tick)
    monkeypatch.setattr(runner_module.us_condition_service, "wait_for_entry_signal", wait_for_entry_signal)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(runner_module._autotrade_runner_loop())

    assert calls == {"entry": 2, "exit": 2, "wait": 2}
    assert runner_module._runner_condition_wake_count == 1
    assert runner_module._runner_last_wake_reason == "condition_entry"


def test_us_limit_order_requires_price(monkeypatch):
    monkeypatch.setenv("ALLOWED_USER_EMAILS", "allowed@example.com")
    get_settings.cache_clear()

    def verify(token: str):
        return AuthenticatedUser(email="allowed@example.com", subject="user-id")

    monkeypatch.setattr(auth_module, "verify_supabase_jwt", verify)

    response = TestClient(app).post(
        "/api/us/orders",
        headers={"Authorization": "Bearer valid-token"},
        json={
            "side": "buy",
            "exchange": "ND",
            "symbol": "NVDA",
            "quantity": 1,
            "orderPrice": "",
            "tradeType": "00",
            "confirmText": "I_UNDERSTAND_LIVE_US_ORDER",
        },
    )

    assert response.status_code == 422


def test_realtime_quotes_websocket_requires_backend_session_token():
    client = TestClient(app)

    with client.websocket_connect("/api/realtime/quotes/ws") as websocket:
        websocket.send_json({"type": "AUTH", "token": ""})
        body = websocket.receive_json()

    assert body["type"] == "ERROR"
    assert body["errorType"] == "AUTH_REQUIRED"


def test_realtime_quotes_websocket_reuses_shared_monitor(monkeypatch):
    from app.api import realtime as realtime_api

    session = KiwoomSession(
        session_token="quote-session",
        mode="live",
        account_no="configured",
        base_url="https://api.kiwoom.com",
        access_token="fixture-token",
        expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
    )
    kiwoom_session_manager._sessions[session.session_token] = session
    ensure_union = AsyncMock()

    class SharedMonitor:
        async def ensure_union(self, *args, **kwargs):
            await ensure_union(*args, **kwargs)

        def status(self):
            return {"connected": True, "symbols": ["NVDA"], "lastError": None}

    monkeypatch.setattr(realtime_api, "kiwoom_quote_monitor", SharedMonitor())
    realtime_window_store.record(
        {"type": "TICK", "symbol": "NVDA", "price": 125.5, "changeRate": 1.2, "volume": 777}
    )

    with TestClient(app).websocket_connect("/api/realtime/quotes/ws") as websocket:
        websocket.send_json(
            {
                "type": "AUTH",
                "token": session.session_token,
                "provider": "kiwoom",
                "symbols": ["NVDA"],
                "exchanges": {"NVDA": "ND"},
            }
        )
        authenticated = websocket.receive_json()
        snapshot = websocket.receive_json()

    assert authenticated["intervalMs"] == 2000
    assert authenticated["channels"] == ["FE", "FT"]
    assert snapshot["type"] == "QUOTE_SNAPSHOT"
    assert snapshot["monitorConnected"] is True
    assert snapshot["items"][0]["latestPrice"] == 125.5
    ensure_union.assert_awaited_once()


def test_realtime_rankings_websocket_reuses_shared_monitor(monkeypatch):
    from app.api import realtime as realtime_api

    session = KiwoomSession(
        session_token="ranking-session",
        mode="live",
        account_no="configured",
        base_url="https://api.kiwoom.com",
        access_token="fixture-token",
        expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
    )
    kiwoom_session_manager._sessions[session.session_token] = session
    ensure_union = AsyncMock()

    class SharedMonitor:
        async def ensure_union(self, *args, **kwargs):
            await ensure_union(*args, **kwargs)

        def status(self):
            return {"connected": True, "symbols": ["NVDA"], "lastError": None}

    monkeypatch.setattr(realtime_api, "kiwoom_quote_monitor", SharedMonitor())
    realtime_window_store.record(
        {"type": "TICK", "symbol": "NVDA", "price": 120.5, "changeRate": 2.4, "volume": 123456}
    )
    client = TestClient(app)

    with client.websocket_connect("/api/realtime/rankings/ws") as websocket:
        websocket.send_json(
            {
                "type": "AUTH",
                "token": session.session_token,
                "symbols": [{"symbol": "NVDA", "exchange": "ND"}],
            }
        )
        authenticated = websocket.receive_json()
        snapshot = websocket.receive_json()

    assert authenticated["intervalMs"] == 2000
    assert authenticated["readOnly"] is True
    assert authenticated["orderEnabled"] is False
    assert snapshot["type"] == "RANKING_SNAPSHOT"
    assert snapshot["monitorConnected"] is True
    assert snapshot["items"][0]["latestPrice"] == 120.5
    assert snapshot["items"][0]["latestChangeRate"] == 2.4
    assert snapshot["items"][0]["latestVolume"] == 123456
    ensure_union.assert_awaited_once()


def test_realtime_condition_websocket_requires_backend_session_token():
    client = TestClient(app)

    with client.websocket_connect("/api/realtime/us/conditions/ws") as websocket:
        websocket.send_json({"type": "AUTH", "token": ""})
        body = websocket.receive_json()

    assert body["type"] == "ERROR"
    assert body["errorType"] == "AUTH_REQUIRED"


def test_realtime_condition_websocket_pushes_shared_monitor_snapshot(monkeypatch):
    from app.api import realtime as realtime_api

    session = KiwoomSession(
        session_token="condition-session",
        mode="live",
        account_no="configured",
        base_url="https://api.kiwoom.com",
        access_token="fixture-token",
        expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
    )
    kiwoom_session_manager._sessions[session.session_token] = session

    class Match:
        def model_dump(self):
            return {
                "code": "NVDA",
                "name": "NVIDIA",
                "exchange": "ND",
                "price": 125.5,
                "changeRate": 1.2,
                "volume": 777,
            }

    class SharedConditionService:
        async def ensure_realtime_monitor(self, *args, **kwargs):
            await asyncio.Event().wait()

        def monitor_status(self, seq):
            return {
                "active": True,
                "selectedSeq": seq,
                "selectedName": "HTS 급등 조건",
                "matchCount": 1,
                "error": None,
            }

        def monitor_matches(self, seq):
            return [Match()]

    monkeypatch.setattr(realtime_api, "us_condition_service", SharedConditionService())

    with TestClient(app).websocket_connect("/api/realtime/us/conditions/ws") as websocket:
        websocket.send_json(
            {
                "type": "AUTH",
                "token": session.session_token,
                "provider": "kiwoom",
                "seqs": ["007"],
            }
        )
        authenticated = websocket.receive_json()
        snapshot = websocket.receive_json()

    assert authenticated["intervalMs"] == 2000
    assert authenticated["readOnly"] is True
    assert snapshot["type"] == "CONDITION_SNAPSHOT"
    assert snapshot["items"][0]["connected"] is True
    assert snapshot["items"][0]["matches"][0]["code"] == "NVDA"


def test_us_condition_request_wraps_ssl_errors_without_token_leak(monkeypatch):
    class FakeWebsockets:
        @staticmethod
        def connect(*args, **kwargs):
            assert kwargs.get("ssl") is not None
            raise ssl.SSLError("self-signed certificate in certificate chain")

    monkeypatch.setitem(sys.modules, "websockets", FakeWebsockets)

    with pytest.raises(UsConditionSearchError) as exc_info:
        asyncio.run(_send_condition_request("secret-token-value", "live", {"trnm": "CNSRLST"}))

    message = str(exc_info.value)
    assert "SSL verification failed" in message
    assert "secret-token-value" not in message


def test_us_condition_strategy_sequence_is_list_general_realtime_then_clear(monkeypatch):
    import json

    from app.services.us_condition_service import _send_condition_strategy_sequence

    class FakeSocket:
        def __init__(self):
            self.sent: list[dict[str, object]] = []
            self.responses = [
                {"trnm": "LOGIN", "return_code": 0},
                {"trnm": "GCNSRLST", "return_code": 0, "data": [["001", "US_COMMON_LIQUID_LONG"]]},
                {"trnm": "GCNSRREQ", "return_code": 0, "data": [{"jmcode": "AAA"}]},
                {"trnm": "GCNSRREQ", "return_code": 0, "data": [{"item": "BBB", "values": {"302": "Fixture"}}]},
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

    conditions, selected, matches, schema_keys = asyncio.run(
        _send_condition_strategy_sequence("fixture-token", "live", None)
    )

    packets = socket.sent[1:]
    assert [(item["trnm"], item.get("search_type")) for item in packets] == [
        ("GCNSRLST", None),
        ("GCNSRREQ", "0"),
        ("GCNSRREQ", "1"),
        ("GCNSRCLR", None),
    ]
    assert conditions[0].seq == "001"
    assert selected is not None and selected.name == "US_COMMON_LIQUID_LONG"
    assert {item.code for item in matches} == {"AAA", "BBB"}
    assert "data" in schema_keys


def test_us_condition_realtime_message_adds_and_removes_matches():
    from app.schemas.market import UsConditionSearchMatch
    from app.services.us_condition_service import _apply_realtime_condition_message

    current = [UsConditionSearchMatch(code="AAA", exchange="ND")]
    inserted = _apply_realtime_condition_message(
        current,
        {"trnm": "REAL", "data": [{"values": {"843": "I", "9001": "BBB"}, "stexTp": "NY"}]},
    )
    removed = _apply_realtime_condition_message(
        inserted,
        {"trnm": "REAL", "data": [{"values": {"843": "D", "9001": "AAA"}, "stexTp": "ND"}]},
    )

    assert {item.code for item in inserted} == {"AAA", "BBB"}
    assert {item.code for item in removed} == {"BBB"}


def test_us_condition_realtime_message_preserves_existing_market_values():
    from app.schemas.market import UsConditionSearchMatch
    from app.services.us_condition_service import _apply_realtime_condition_message

    current = [
        UsConditionSearchMatch(
            code="AAA",
            name="ALPHA",
            exchange="ND",
            price=12.5,
            changeRate=4.2,
            volume=450_000,
        )
    ]
    updated = _apply_realtime_condition_message(
        current,
        {"trnm": "REAL", "data": [{"values": {"843": "I", "9001": "AAA"}}]},
    )

    assert updated[0].price == 12.5
    assert updated[0].changeRate == 4.2
    assert updated[0].volume == 450_000


def test_us_condition_monitor_signals_only_new_entry_symbols():
    from app.schemas.market import UsConditionItem, UsConditionSearchMatch
    from app.services.us_condition_service import (
        UsConditionService,
        _ConditionMonitorState,
    )

    service = UsConditionService()
    state = _ConditionMonitorState(key=("session-token", "2"))
    selected = UsConditionItem(seq="2", name="BREAKOUT")
    first_match = UsConditionSearchMatch(code="AAA", exchange="ND")

    service._store_monitor_response(
        state,
        "2",
        [selected],
        selected,
        [first_match],
        {"data"},
    )
    assert asyncio.run(service.wait_for_entry_signal(0.01)) is True

    service._store_monitor_response(
        state,
        "2",
        [selected],
        selected,
        [first_match],
        {"data"},
    )
    assert asyncio.run(service.wait_for_entry_signal(0.01)) is False

    service._store_monitor_response(
        state,
        "2",
        [selected],
        selected,
        [first_match, UsConditionSearchMatch(code="BBB", exchange="NY")],
        {"data"},
    )
    assert asyncio.run(service.wait_for_entry_signal(0.01)) is True


def test_us_condition_explicit_unknown_sequence_does_not_fallback():
    from app.schemas.market import UsConditionItem
    from app.services.us_condition_service import _select_condition

    conditions = [
        UsConditionItem(seq="0", name="FIRST"),
        UsConditionItem(seq="2", name="BREAKOUT"),
    ]

    assert _select_condition(conditions, None) == conditions[0]
    assert _select_condition(conditions, "2") == conditions[1]
    assert _select_condition(conditions, "2028") is None


def test_us_condition_monitor_keeps_realtime_registration_until_stopped(monkeypatch):
    import json

    from app.services.us_condition_service import UsConditionService

    class FakeSocket:
        def __init__(self):
            self.sent: list[dict[str, object]] = []
            self.responses = [
                {"trnm": "LOGIN", "return_code": 0},
                {"trnm": "GCNSRLST", "return_code": 0, "data": [["001", "US_COMMON_LIQUID_LONG"]]},
                {"trnm": "GCNSRREQ", "return_code": 0, "data": [{"jmcode": "AAA", "stex_tp": "ND"}]},
            ]

        async def send(self, payload: str):
            self.sent.append(json.loads(payload))

        async def recv(self):
            if self.responses:
                return json.dumps(self.responses.pop(0))
            await asyncio.Future()

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
    service = UsConditionService()
    session = KiwoomSession(
        session_token="session-token",
        mode="live",
        account_no="configured",
        base_url="https://api.kiwoom.com",
        access_token="fixture-token",
        expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
    )

    async def run_test():
        await service.ensure_realtime_monitor(session)
        packets_before_stop = list(socket.sent)
        response = service._cached_response
        await service.stop_realtime_monitor()
        return packets_before_stop, response

    packets_before_stop, response = asyncio.run(run_test())

    assert [(packet["trnm"], packet.get("search_type")) for packet in packets_before_stop[1:]] == [
        ("GCNSRLST", None),
        ("GCNSRREQ", "0"),
        ("GCNSRREQ", "1"),
    ]
    assert socket.sent[-1]["trnm"] == "GCNSRCLR"
    assert response is not None
    assert {item.code for item in response.matches} == {"AAA"}


def test_us_realtime_hub_registers_quotes_and_conditions_on_one_websocket(monkeypatch):
    import json

    from app.services.us_condition_service import UsConditionService

    class FakeSocket:
        def __init__(self):
            self.sent: list[dict[str, object]] = []
            self.responses = [
                {"trnm": "LOGIN", "return_code": 0},
                {
                    "trnm": "GCNSRLST",
                    "return_code": 0,
                    "data": [["001", "US_COMMON_LIQUID_LONG"]],
                },
                {
                    "trnm": "GCNSRREQ",
                    "return_code": 0,
                    "data": [{"jmcode": "AAA", "stex_tp": "ND"}],
                },
            ]

        async def send(self, payload: str):
            self.sent.append(json.loads(payload))

        async def recv(self):
            if self.responses:
                return json.dumps(self.responses.pop(0))
            await asyncio.Future()

    socket = FakeSocket()
    connection_count = 0

    class FakeContext:
        async def __aenter__(self):
            return socket

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeWebsockets:
        @staticmethod
        def connect(*args, **kwargs):
            nonlocal connection_count
            connection_count += 1
            return FakeContext()

    monkeypatch.setitem(sys.modules, "websockets", FakeWebsockets)
    service = UsConditionService()
    session = KiwoomSession(
        session_token="shared-session-token",
        mode="live",
        account_no="configured",
        base_url="https://api.kiwoom.com",
        access_token="fixture-token",
        expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
    )

    async def run_test():
        condition_task = asyncio.create_task(
            service.ensure_realtime_monitor(session, "001")
        )
        quote_task = asyncio.create_task(
            service.ensure_quote_monitor(
                session,
                ["NVDA"],
                {"NVDA": "ND"},
            )
        )
        await asyncio.gather(condition_task, quote_task)
        packets = list(socket.sent)
        status = service.quote_monitor_status()
        await service.stop_realtime_monitor()
        await service.stop_quote_monitor()
        return packets, status

    packets, status = asyncio.run(run_test())

    assert connection_count == 1
    assert [packet["trnm"] for packet in packets].count("LOGIN") == 1
    assert any(packet["trnm"] == "GCNSRREQ" and packet.get("search_type") == "1" for packet in packets)
    assert any(packet["trnm"] == "REG" and packet["data"][0]["type"] == ["FE", "FT"] for packet in packets)
    assert status["connected"] is True
    assert status["symbols"] == ["NVDA"]


def test_us_condition_monitor_reuses_one_websocket_for_multiple_sequences(monkeypatch):
    import json

    from app.services.us_condition_service import UsConditionService

    class FakeSocket:
        def __init__(self):
            self.sent: list[dict[str, object]] = []
            self.responses = [
                {"trnm": "LOGIN", "return_code": 0},
                {
                    "trnm": "GCNSRLST",
                    "return_code": 0,
                    "data": [["0", "FIRST"], ["2", "BREAKOUT"]],
                },
                {"trnm": "GCNSRREQ", "return_code": 0, "seq": "0", "data": [{"jmcode": "AAA"}]},
                {"trnm": "GCNSRREQ", "return_code": 0, "seq": "2", "data": [{"jmcode": "BBB"}]},
            ]

        async def send(self, payload: str):
            self.sent.append(json.loads(payload))

        async def recv(self):
            if self.responses:
                return json.dumps(self.responses.pop(0))
            await asyncio.Future()

    socket = FakeSocket()
    connect_calls = 0

    class FakeContext:
        async def __aenter__(self):
            return socket

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeWebsockets:
        @staticmethod
        def connect(*args, **kwargs):
            nonlocal connect_calls
            connect_calls += 1
            return FakeContext()

    monkeypatch.setitem(sys.modules, "websockets", FakeWebsockets)
    service = UsConditionService()
    session = KiwoomSession(
        session_token="shared-session-token",
        mode="live",
        account_no="configured",
        base_url="https://api.kiwoom.com",
        access_token="fixture-token",
        expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
    )

    async def run_test():
        first = asyncio.create_task(service.ensure_realtime_monitor(session, "0"))
        second = asyncio.create_task(service.ensure_realtime_monitor(session, "2"))
        states = await asyncio.gather(first, second)
        await service.stop_realtime_monitor()
        return states

    states = asyncio.run(run_test())

    assert connect_calls == 1
    assert {item.code for item in states[0].response.matches} == {"AAA"}
    assert {item.code for item in states[1].response.matches} == {"BBB"}
    assert [(packet["trnm"], packet.get("seq"), packet.get("search_type")) for packet in socket.sent[:6]] == [
        ("LOGIN", None, None),
        ("GCNSRLST", None, None),
        ("GCNSRREQ", "0", "0"),
        ("GCNSRREQ", "2", "0"),
        ("GCNSRREQ", "0", "1"),
        ("GCNSRREQ", "2", "1"),
    ]


def test_condition_direct_entry_uses_condition_matches_without_ranking_or_chart(monkeypatch):
    from app.schemas.market import MarketRankingResponse, UsConditionSearchMatch
    from app.services import market_ranking_service as ranking_module

    config = {
        "strategy": "builder-direct",
        "name": "조건 편입 직접 진입",
        "condition_seq": "2",
        "condition_name": "COND",
        "tick_scope": "1",
        "bearish_count": 1,
        "entry_rule": "condition_direct",
        "target_profit_pct": 3.0,
        "stop_loss_pct": 2.0,
        "required_criteria": ("strategy_session", "condition_search_match", "quote_price"),
        "live_execution_allowed": True,
        "builder_strategy": True,
        "condition_direct_entry": True,
    }
    ranking = MarketRankingResponse(
        trId="usa20910",
        title="fixture",
        market="US",
        source="fixture",
        updatedAt="2026-07-28T00:00:00+00:00",
        items=[],
    )
    captured: list[tuple[str, str, str]] = []

    monkeypatch.setattr(ranking_module.us_order_service, "is_strategy_enabled", lambda strategy: True)

    async def fake_compose(**kwargs):
        captured.append((
            kwargs["target"].code,
            kwargs["ranking_tr_id"],
            kwargs["chart"].source,
        ))
        return ranking_module._empty_pullback_plan(config, "fixture", "usa20290")

    monkeypatch.setattr(ranking_module.market_ranking_service, "_compose_pullback_plan", fake_compose)

    asyncio.run(ranking_module.market_ranking_service._build_pullback_strategy_candidates(
        ranking,
        config,
        condition_codes={"FBRX", "ENTX"},
        condition_matches=[
            UsConditionSearchMatch(code="FBRX", exchange="ND", price=4.25),
            UsConditionSearchMatch(code="ENTX", exchange="NA", price=2.10),
        ],
        condition_name="COND",
    ))

    assert captured == [
        ("FBRX", "usa20290", "condition-direct-entry-no-chart"),
        ("ENTX", "usa20290", "condition-direct-entry-no-chart"),
    ]


def test_condition_plans_request_each_hts_condition_sequence(monkeypatch):
    from app.schemas.market import (
        MarketRankingResponse,
        UsConditionItem,
        UsConditionSearchMatch,
        UsConditionSearchResponse,
    )
    from app.services import market_ranking_service as ranking_module

    configs = (
        {
            "strategy": "kiwoom-condition-001",
            "condition_seq": "001",
            "condition_name": "COND_A",
            "condition_direct_entry": True,
        },
        {
            "strategy": "kiwoom-condition-002",
            "condition_seq": "002",
            "condition_name": "COND_B",
            "condition_direct_entry": True,
        },
    )
    requested: list[str | None] = []
    evaluated: list[tuple[str, frozenset[str], str | None]] = []

    async def fake_ranking():
        return MarketRankingResponse(
            trId="usa20910",
            title="fixture",
            market="US",
            source="fixture",
            updatedAt="2026-07-25T00:00:00+00:00",
            items=[],
        )

    async def fake_condition_search(seq: str | None = None):
        requested.append(seq)
        symbol = "AAA" if seq == "001" else "BBB"
        name = "COND_A" if seq == "001" else "COND_B"
        return UsConditionSearchResponse(
            source="fixture",
            listTrId="usa20280",
            searchTrId="usa20281",
            realtimeTrId="usa20290",
            clearTrId="usa20291",
            updatedAt="2026-07-25T00:00:00+00:00",
            conditions=[UsConditionItem(seq=seq or "", name=name)],
            selectedSeq=seq,
            selectedName=name,
            matches=[UsConditionSearchMatch(code=symbol, exchange="ND")],
            schemaKeys=["data", "trnm"],
        )

    async def fake_build(ranking, config, *, condition_codes, condition_matches, condition_name):
        evaluated.append((str(config["strategy"]), frozenset(condition_codes or set()), condition_name))
        return []

    monkeypatch.setattr(ranking_module, "_all_pullback_strategies", lambda conditions: configs)
    monkeypatch.setattr(ranking_module.us_order_service, "is_strategy_enabled", lambda strategy: True)
    monkeypatch.setattr(
        ranking_module.market_ranking_service,
        "_get_pullback_candidate_ranking",
        fake_ranking,
    )
    monkeypatch.setattr(
        ranking_module.us_condition_service,
        "get_condition_search",
        fake_condition_search,
    )
    monkeypatch.setattr(
        ranking_module.market_ranking_service,
        "_build_pullback_strategy_candidates",
        fake_build,
    )
    monkeypatch.setattr(ranking_module, "get_active_or_latest_kiwoom_session", lambda: None)

    asyncio.run(ranking_module.market_ranking_service._load_us_pullback_auto_trade_plans())

    assert set(requested) == {"001", "002"}
    assert set(evaluated) == {
        ("kiwoom-condition-001", frozenset({"AAA"}), "COND_A"),
        ("kiwoom-condition-002", frozenset({"BBB"}), "COND_B"),
    }


def test_kiwoom_quote_stream_yields_safe_error_on_ssl_failure(monkeypatch):
    class FakeWebsockets:
        @staticmethod
        def connect(*args, **kwargs):
            assert kwargs.get("ssl") is not None
            raise ssl.SSLError("self-signed certificate in certificate chain")

    monkeypatch.setitem(sys.modules, "websockets", FakeWebsockets)
    session = KiwoomSession(
        session_token="session-token",
        mode="live",
        account_no="1234",
        base_url="https://api.kiwoom.com",
        access_token="secret-token-value",
        expires_at=datetime.now(timezone.utc),
    )

    async def collect_events():
        from app.services.realtime_quote_service import kiwoom_quote_stream

        events = []
        async for event in kiwoom_quote_stream(session, ["NVDA"]):
            events.append(event)
            if event.get("type") == "ERROR":
                return events
        return events

    events = asyncio.run(collect_events())

    assert events[-1]["errorType"] == "KIWOOM_WEBSOCKET_SSL_ERROR"
    assert "secret-token-value" not in str(events)


def test_kiwoom_quote_monitor_runs_fe_ft_stream_without_order_channel(monkeypatch):
    from datetime import timedelta

    from app.services.kiwoom_session import KiwoomSession
    from app.services import realtime_quote_service as quote_module

    captured: dict[str, object] = {}

    async def fake_stream(session, symbols, exchanges=None):
        captured["symbols"] = symbols
        captured["exchanges"] = exchanges
        yield {
            "type": "TICK",
            "symbol": symbols[0],
            "price": 10.5,
            "volume": 100,
        }
        await asyncio.sleep(60)

    monkeypatch.setattr(quote_module, "kiwoom_quote_stream", fake_stream)
    session = KiwoomSession(
        session_token="safe-session",
        mode="live",
        account_no="masked",
        base_url="https://api.kiwoom.com",
        access_token="not-logged",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    monitor = quote_module.KiwoomQuoteMonitor()

    async def scenario():
        await monitor.ensure(session, ["AAA", "BBB"], {"AAA": "NA", "BBB": "NY"})
        await asyncio.sleep(0)
        status = monitor.status()
        await monitor.stop()
        return status

    status = asyncio.run(scenario())

    assert captured["symbols"] == ["AAA", "BBB"]
    assert captured["exchanges"] == {"AAA": "NA", "BBB": "NY"}
    assert status["running"] is True
    assert status["channels"] == ["FE", "FT"]


def test_kiwoom_quote_reg_packet_uses_readonly_realtime_type_only():
    packet = build_kiwoom_quote_reg_packet(["NVDA", "NVDA", "bad symbol"])

    assert packet["trnm"] == "REG"
    assert packet["data"][0]["item"] == [{"jmcode": "NVDA", "stex_tp": "ND"}, {"jmcode": "BADSYMBOL", "stex_tp": "ND"}]
    assert packet["data"][0]["type"] == ["FE", "FT"]
    assert "F4" not in packet["data"][0]["type"]


def test_kiwoom_quote_reg_packet_preserves_symbol_exchanges():
    packet = build_kiwoom_quote_reg_packet(
        ["AAA", "BBB", "CCC"],
        exchanges={"AAA": "NA", "BBB": "NY", "CCC": "ND"},
    )

    assert packet["data"][0]["item"] == [
        {"jmcode": "AAA", "stex_tp": "NA"},
        {"jmcode": "BBB", "stex_tp": "NY"},
        {"jmcode": "CCC", "stex_tp": "ND"},
    ]


def test_safe_quote_symbols_limits_and_sanitizes_values():
    symbols = safe_quote_symbols(["nvda", " tsla ", "bad-symbol", "", "x" * 30])

    assert symbols == ["NVDA", "TSLA", "BAD-SYMBOL"]


def test_kiwoom_realtime_message_normalizes_tick_without_raw_payload():
    events = normalize_kiwoom_realtime_message(
        {
            "trnm": "REAL",
            "data": [
                {
                    "item": {"jmcode": "NVDA", "stex_tp": "ND"},
                    "values": {"10": "+198.4200", "12": "+1.24", "13": "2,150,000", "27": "198.4100", "28": "198.4300"},
                }
            ],
        }
    )

    assert events[0]["type"] == "TICK"
    assert events[0]["symbol"] == "NVDA"
    assert events[0]["price"] == 198.42
    assert events[0]["changeRate"] == 1.24
    assert "values" not in events[0]
    assert events[1]["type"] == "ORDERBOOK"
    assert events[1]["symbol"] == "NVDA"


def test_kiwoom_realtime_message_normalizes_ft_orderbook_fields():
    events = normalize_kiwoom_realtime_message(
        {
            "trnm": "REAL",
            "data": [
                {
                    "item": {"jmcode": "NVDA", "stex_tp": "ND"},
                    "values": {"41": "198.4300", "51": "198.4100", "61": "120", "71": "90"},
                }
            ],
        }
    )

    assert events == [
        {
            "type": "ORDERBOOK",
            "symbol": "NVDA",
            "name": "NVDA",
            "bid": 198.41,
            "ask": 198.43,
            "bidSize": 120,
            "askSize": 90,
            "levels": [{"level": 1, "bid": 198.41, "ask": 198.43, "bidSize": 120, "askSize": 90}],
            "provider": "kiwoom",
            "timestamp": events[0]["timestamp"],
            "receivedAt": events[0]["receivedAt"],
            "sourceEventTime": None,
        }
    ]


def test_realtime_window_store_calculates_delay_conditions_without_raw_payload():
    store = RealtimeWindowStore()
    store.record(
        {
            "type": "TICK",
            "symbol": "NVDA",
            "price": 198.1,
            "volume": 1000,
            "tradeStrength": 95.0,
            "receivedAt": "2026-07-15T12:00:02+00:00",
        }
    )
    store.record(
        {
            "type": "TICK",
            "symbol": "NVDA",
            "price": 198.4,
            "volume": 1300,
            "tradeStrength": 112.5,
            "receivedAt": "2026-07-15T12:00:11+00:00",
        }
    )
    store.record(
        {
            "type": "ORDERBOOK",
            "symbol": "NVDA",
            "bid": 198.41,
            "ask": 198.43,
            "receivedAt": "2026-07-15T12:00:12+00:00",
        }
    )

    summary = store.summary("NVDA")

    assert summary.tickCount == 2
    assert summary.orderbookCount == 1
    assert summary.volume10sDelta == 300
    assert summary.volume10sIncreasing is True
    assert summary.tradeStrength == 112.5
    assert summary.tradeStrengthIncreasing is True
    assert summary.spreadPct is not None
    assert summary.spreadPct < 0.1
    assert "token" not in str(summary.to_dict()).lower()
    assert realtime_event_counts(["NVDA"])["NVDA"] == 3
    db_metrics = realtime_db_window_metrics(["NVDA"], now=datetime.fromisoformat("2026-07-15T12:00:12+00:00"))["NVDA"]
    assert db_metrics.events10s == 3
    assert db_metrics.events1m == 3
    assert db_metrics.events5m == 3
    assert db_metrics.volume10sDelta == 300
    assert db_metrics.volume1mDelta == 300
    assert db_metrics.volume5mDelta == 300
    assert db_metrics.tradeStrength1mChange == 17.5
    assert db_metrics.spreadPctLatest is not None
    assert db_metrics.spreadPctLatest < 0.1


def test_realtime_receive_delay_uses_us_market_dst_timezone():
    summer_delay = _receive_delay_ms(
        {
            "sourceEventTime": "20260715T093001",
            "receivedAt": "2026-07-15T13:30:01.250+00:00",
        }
    )
    winter_delay = _receive_delay_ms(
        {
            "sourceEventTime": "20261215T093001",
            "receivedAt": "2026-12-15T14:30:02+00:00",
        }
    )

    assert summer_delay == 250
    assert winter_delay == 1_000


def test_realtime_receive_delay_treats_zero_seconds_as_minute_precision():
    same_minute = _receive_delay_ms(
        {
            "sourceEventTime": "20260715T093000",
            "receivedAt": "2026-07-15T13:30:30+00:00",
        }
    )
    older_minute = _receive_delay_ms(
        {
            "sourceEventTime": "20260715T093000",
            "receivedAt": "2026-07-15T13:31:05+00:00",
        }
    )

    assert same_minute == 0
    assert older_minute == 5_001



def test_invalid_jwt_returns_401(monkeypatch):
    monkeypatch.setenv("ALLOWED_USER_EMAILS", "allowed@example.com")
    get_settings.cache_clear()

    def fail_verify(token: str):
        raise SupabaseAuthError("invalid token")

    monkeypatch.setattr(auth_module, "verify_supabase_jwt", fail_verify)

    response = TestClient(app).get("/api/accounts", headers={"Authorization": "Bearer invalid-token"})

    assert response.status_code == 401


def test_jwk_client_uses_timeout():
    auth_module._jwk_clients.clear()

    client = _get_jwk_client("https://example.supabase.co/auth/v1/.well-known/jwks.json")

    assert client.timeout == 5


def test_email_claim_must_be_string():
    with pytest.raises(SupabaseAuthError):
        _email_from_claims({"email": ["allowed@example.com"]})

    with pytest.raises(SupabaseAuthError):
        _email_from_claims({"user_metadata": {"email": 123}})

    with pytest.raises(SupabaseAuthError):
        _email_from_claims({"email": "   "})


def test_email_claim_is_normalized_from_primary_or_metadata():
    assert _email_from_claims({"email": " Allowed@Example.COM "}) == "allowed@example.com"
    assert _email_from_claims({"user_metadata": {"email": " Meta@Example.COM "}}) == "meta@example.com"


def test_authenticated_email_not_in_allowlist_returns_403(monkeypatch):
    monkeypatch.setenv("ALLOWED_USER_EMAILS", "allowed@example.com")
    get_settings.cache_clear()

    def verify(token: str):
        return AuthenticatedUser(email="other@example.com", subject="user-id")

    monkeypatch.setattr(auth_module, "verify_supabase_jwt", verify)

    response = TestClient(app).get("/api/accounts", headers={"Authorization": "Bearer valid-token"})

    assert response.status_code == 403


def test_empty_allowlist_blocks_authenticated_user(monkeypatch):
    get_settings.cache_clear()

    def verify(token: str):
        return AuthenticatedUser(email="allowed@example.com", subject="user-id")

    monkeypatch.setattr(auth_module, "verify_supabase_jwt", verify)

    response = TestClient(app).get("/api/accounts", headers={"Authorization": "Bearer valid-token"})

    assert response.status_code == 403



def test_authenticated_user_without_live_session_gets_explicit_account_error(monkeypatch):
    monkeypatch.setenv("ALLOWED_USER_EMAILS", "allowed@example.com")
    get_settings.cache_clear()

    def verify(token: str):
        return AuthenticatedUser(email="allowed@example.com", subject="user-id")

    monkeypatch.setattr(auth_module, "verify_supabase_jwt", verify)

    client = TestClient(app)

    for path in (
        "/api/accounts",
        "/api/account/cash",
        "/api/account/portfolio",
        "/api/account/performance",
        "/api/account/holdings",
        "/api/us/account/cash",
        "/api/us/account/valuation",
        "/api/us/account/realized-pnl",
        "/api/us/account/period-return",
        "/api/us/account/daily-returns",
    ):
        assert client.get(path, headers={"Authorization": "Bearer valid-token"}).status_code in {400, 502}


def test_authenticated_user_without_live_session_gets_ranking_error(monkeypatch):
    monkeypatch.setenv("ALLOWED_USER_EMAILS", "allowed@example.com")
    get_settings.cache_clear()

    def verify(token: str):
        return AuthenticatedUser(email="allowed@example.com", subject="user-id")

    monkeypatch.setattr(auth_module, "verify_supabase_jwt", verify)

    client = TestClient(app)
    ranking_paths = (
        "/api/market/rankings/us/realtime",
        "/api/market/rankings/us/change-rate",
        "/api/market/rankings/us/volume",
        "/api/market/rankings/us/price-spike",
    )
    for path in ranking_paths:
        response = client.get(path, headers={"Authorization": "Bearer valid-token"})
        assert response.status_code == 502
    return

    chart_paths = {
        "minute": "usa06011",
        "day": "usa06012",
        "week": "usa06013",
        "month": "usa06014",
    }
    for timeframe, tr_id in chart_paths.items():
        chart_response = client.get(f"/api/market/us/chart/{timeframe}?symbol=NVDA&exchange=ND", headers={"Authorization": "Bearer valid-token"})
        assert chart_response.status_code == 200
        chart_body = chart_response.json()
        assert chart_body["trId"] == tr_id
        assert chart_body["timeframe"] == timeframe
        assert chart_body["candles"]

    condition_response = client.get("/api/market/us/conditions", headers={"Authorization": "Bearer valid-token"})
    assert condition_response.status_code == 200
    condition_body = condition_response.json()
    assert condition_body["listTrId"] == "usa20280"
    assert condition_body["searchTrId"] == "usa20281"
    assert condition_body["realtimeTrId"] == "usa20290"
    assert condition_body["clearTrId"] == "usa20291"
    assert condition_body["conditions"]


def test_change_rate_ranking_is_sorted_highest_first(monkeypatch):
    from app.services.market_ranking_service import market_ranking_service
    from trading_engine.providers.kiwoom_us.schemas import UsReadOnlyTrResponse

    async def fake_execute(tr_id: str):
        assert tr_id == "usa20910"
        return UsReadOnlyTrResponse(
            tr_id=tr_id,
            return_code="0",
            return_msg="OK",
            data={
                "result_list": [
                    {"rank": "1", "stk_cd": "LOW", "flu_rt": "+2.10", "trde_qty": "900"},
                    {"rank": "2", "stk_cd": "HIGH", "flu_rt": "+12.50", "trde_qty": "800"},
                    {"rank": "3", "stk_cd": "MID", "flu_rt": "+7.25", "trde_qty": "1000"},
                ]
            },
            unknown_fields={},
        )

    monkeypatch.setattr(market_ranking_service, "_execute_us_ranking", fake_execute)

    ranking = asyncio.run(market_ranking_service.get_us_ranking("change-rate"))

    assert ranking.trId == "usa20910"
    assert [item.code for item in ranking.items] == ["HIGH", "MID", "LOW"]
    assert [item.rank for item in ranking.items] == [1, 2, 3]


def test_us_chart_candles_are_sorted_and_duplicate_timestamps_are_merged():
    from app.services.market_ranking_service import _normalize_us_chart_candles

    candles = _normalize_us_chart_candles([
        {
            "cntr_tm": "20260721100500",
            "cur_prc": "10.2000",
            "open_pric": "10.0000",
            "high_pric": "10.3000",
            "low_pric": "9.9000",
            "trde_qty": "120",
        },
        {
            "cntr_tm": "20260721100000",
            "cur_prc": "9.9000",
            "open_pric": "9.8000",
            "high_pric": "10.0000",
            "low_pric": "9.7000",
            "trde_qty": "100",
        },
        {
            "cntr_tm": "20260721100500",
            "cur_prc": "10.2500",
            "open_pric": "10.0000",
            "high_pric": "10.3500",
            "low_pric": "9.9500",
            "trde_qty": "130",
        },
    ])

    assert [item.executedAt for item in candles] == ["20260721100000", "20260721100500"]
    assert candles[-1].open == 10.0
    assert candles[-1].high == 10.35
    assert candles[-1].low == 9.9
    assert candles[-1].close == 10.25
    assert candles[-1].volume == 130


def test_us_strategy_ignores_an_unfinished_latest_candle():
    from app.schemas.market import UsChartCandle
    from app.services.market_ranking_service import _completed_strategy_candles

    candles = [
        UsChartCandle(open=10, high=11, low=9, close=10.5, volume=100, executedAt="20200101100000"),
        UsChartCandle(open=10.5, high=11, low=10, close=10.2, volume=80, executedAt="20991231235959"),
    ]

    completed = _completed_strategy_candles(candles, "5")

    assert [item.executedAt for item in completed] == ["20200101100000"]


def test_us_pullback_plan_concurrent_requests_share_one_load(monkeypatch):
    from app.schemas.market import UsAutoTradePlanListResponse
    from app.services.market_ranking_service import MarketRankingService

    service = MarketRankingService()
    calls = 0

    async def fake_load():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return UsAutoTradePlanListResponse(
            source="fixture",
            updatedAt="2026-07-22T00:00:00+00:00",
            plans=[],
            candidatePlans=[],
        )

    monkeypatch.setattr(service, "_load_us_pullback_auto_trade_plans", fake_load)

    async def load_twice():
        return await asyncio.gather(
            service.get_us_pullback_auto_trade_plans(),
            service.get_us_pullback_auto_trade_plans(),
        )

    first, second = asyncio.run(load_twice())

    assert calls == 1
    assert first.source == second.source == "fixture"


def test_us_daily_returns_without_live_session_does_not_fabricate_rows(monkeypatch):
    monkeypatch.setenv("ALLOWED_USER_EMAILS", "allowed@example.com")
    get_settings.cache_clear()

    def verify(token: str):
        return AuthenticatedUser(email="allowed@example.com", subject="user-id")

    monkeypatch.setattr(auth_module, "verify_supabase_jwt", verify)

    response = TestClient(app).get("/api/us/account/daily-returns", headers={"Authorization": "Bearer valid-token"})

    assert response.status_code == 400


def test_us_order_candidates_merge_readonly_rankings(monkeypatch):
    from app.schemas.market import MarketRankItem, MarketRankingResponse
    from app.services.market_ranking_service import market_ranking_service

    monkeypatch.setenv("ALLOWED_USER_EMAILS", "allowed@example.com")
    get_settings.cache_clear()

    def verify(token: str):
        return AuthenticatedUser(email="allowed@example.com", subject="user-id")

    monkeypatch.setattr(auth_module, "verify_supabase_jwt", verify)

    async def fake_ranking(ranking_type: str):
        tr_ids = {
            "change-rate": "usa20910",
            "price-spike": "usa20930",
            "volume": "usa20530",
            "realtime": "usa01980",
        }
        return MarketRankingResponse(
            trId=tr_ids[ranking_type],
            title=ranking_type,
            market="US",
            source="fixture",
            updatedAt="2026-07-15T12:00:00+00:00",
            items=[
                MarketRankItem(rank=1, code=f"{ranking_type[:2].upper()}A", name="A", price=4.5, changeRate=9.0, volume=150_000, exchange="ND", reason=ranking_type),
                MarketRankItem(rank=2, code=f"{ranking_type[:2].upper()}B", name="B", price=99.0, changeRate=8.0, volume=900, exchange="ND", reason=ranking_type),
                MarketRankItem(rank=3, code=f"{ranking_type[:2].upper()}W", name="테스트 콜 워런트", price=0.1, changeRate=300.0, volume=300_000, exchange="ND", reason=ranking_type),
            ],
        )

    monkeypatch.setattr(market_ranking_service, "get_us_ranking", fake_ranking)

    response = TestClient(app).get(
        "/api/market/us/order-candidates?maxNotional=10&limit=5",
        headers={"Authorization": "Bearer valid-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "미국주식 1주 테스트 후보"
    assert "usa20910" in body["trId"]
    assert body["items"]
    assert body["items"][0]["price"] <= 10
    assert any(item["price"] > 10 for item in body["items"])
    assert any("1주 후보" in item["reason"] for item in body["items"])
    assert any("한도초과 관찰" in item["reason"] for item in body["items"])
    assert any("프리마켓 거래량 10만+" in item["reason"] for item in body["items"])
    assert "premarketVolumeThreshold=100000" in body["notes"]
    assert "nonCommonExcluded=2" in body["notes"]
    assert all("워런트" not in item["name"] for item in body["items"])


def test_pullback_candidate_ranking_uses_premarket_sources_when_change_rate_is_empty(monkeypatch):
    from app.schemas.market import MarketRankItem, MarketRankingResponse
    from app.services import market_ranking_service as ranking_module

    async def fake_ranking(ranking_type: str):
        tr_ids = {"change-rate": "usa20910", "realtime": "usa01980", "volume": "usa20530"}
        items = [] if ranking_type == "change-rate" else [
            MarketRankItem(
                rank=1,
                code="PREM" if ranking_type == "realtime" else "VOLM",
                name="Fixture common stock",
                price=12.5,
                changeRate=4.0 if ranking_type == "realtime" else 3.0,
                volume=200_000,
                exchange="ND",
                reason=ranking_type,
            )
        ]
        return MarketRankingResponse(
            trId=tr_ids[ranking_type],
            title=ranking_type,
            market="US",
            source="fixture",
            updatedAt="2026-07-22T12:00:00+00:00",
            items=items,
        )

    monkeypatch.setattr(ranking_module, "_is_us_premarket", lambda now=None: True)
    monkeypatch.setattr(ranking_module.market_ranking_service, "get_us_ranking", fake_ranking)

    result = asyncio.run(ranking_module.market_ranking_service._get_pullback_candidate_ranking())

    assert result.trId == "usa01980+usa20530"
    assert [item.code for item in result.items] == ["PREM", "VOLM"]
    assert "premarketEntryEnabled=false" in result.notes
    assert "premarketOrderType=00" in result.notes


def test_pullback_candidate_ranking_failure_does_not_block_condition_direct_strategies(monkeypatch):
    from app.services import market_ranking_service as ranking_module

    async def failing_ranking(ranking_type: str):
        raise ranking_module.MarketRankingError(f"{ranking_type} unavailable")

    monkeypatch.setattr(ranking_module, "_is_us_premarket", lambda now=None: False)
    monkeypatch.setattr(ranking_module.market_ranking_service, "get_us_ranking", failing_ranking)

    result = asyncio.run(ranking_module.market_ranking_service._get_pullback_candidate_ranking())

    assert result.trId == "usa20910"
    assert result.items == []
    assert result.source == "kiwoom-us-usa20910-unavailable"
    assert "rankingUnavailable=true" in result.notes


def test_pullback_strategy_session_blocks_premarket_entry():
    from app.services.market_ranking_service import _is_us_premarket, _strategy_session_status

    premarket = datetime(2026, 7, 22, 8, 5, tzinfo=ZoneInfo("America/New_York"))

    assert _is_us_premarket(premarket) is True
    assert _strategy_session_status("1", premarket) == (False, "04:00~09:29 ET · 지정가(00)")
    assert _strategy_session_status("5", premarket) == (False, "04:00~09:29 ET · 지정가(00)")


def test_pullback_strategy_session_allows_premarket_limit_entry_when_enabled(monkeypatch):
    from app.services.market_ranking_service import _strategy_session_status

    monkeypatch.setenv("KIWOOM_US_PREMARKET_ENTRY_ENABLED", "true")
    premarket = datetime(2026, 7, 22, 8, 5, tzinfo=ZoneInfo("America/New_York"))

    assert _strategy_session_status("1", premarket) == (True, "04:00~09:29 ET · 지정가(00)")
    assert _strategy_session_status("5", premarket) == (True, "04:00~09:29 ET · 지정가(00)")


def test_premarket_limit_price_requires_fresh_tight_orderbook():
    from app.services.market_ranking_service import _premarket_buy_limit_price

    realtime_window_store.record({
        "type": "ORDERBOOK",
        "symbol": "PREM",
        "bid": 10.00,
        "ask": 10.01,
        "receivedAt": datetime.now(timezone.utc).isoformat(),
    })

    assert _premarket_buy_limit_price(realtime_window_store.summary("PREM")) == 10.01

    realtime_window_store.record({
        "type": "ORDERBOOK",
        "symbol": "WIDE",
        "bid": 10.00,
        "ask": 10.10,
        "receivedAt": datetime.now(timezone.utc).isoformat(),
    })
    assert _premarket_buy_limit_price(realtime_window_store.summary("WIDE")) is None


def test_authenticated_user_can_access_realtime_window(monkeypatch):
    monkeypatch.setenv("ALLOWED_USER_EMAILS", "allowed@example.com")
    get_settings.cache_clear()

    def verify(token: str):
        return AuthenticatedUser(email="allowed@example.com", subject="user-id")

    monkeypatch.setattr(auth_module, "verify_supabase_jwt", verify)
    realtime_window_store.clear()
    now = datetime.now(timezone.utc)
    realtime_window_store.record({"type": "TICK", "symbol": "NVDA", "price": 198.4, "volume": 100, "receivedAt": now.isoformat()})
    realtime_window_store.record({"type": "TICK", "symbol": "NVDA", "price": 198.8, "volume": 180, "receivedAt": now.isoformat()})

    response = TestClient(app).get("/api/market/us/realtime-window?symbols=NVDA", headers={"Authorization": "Bearer valid-token"})

    assert response.status_code == 200
    body = response.json()
    assert body["channels"] == ["FE", "FT"]
    assert body["monitorRunning"] is False
    assert body["monitorConnected"] is False
    assert body["monitorReconnectCount"] == 0
    assert body["monitoredSymbols"] == []
    assert body["items"][0]["symbol"] == "NVDA"
    assert body["items"][0]["tickCount"] == 2
    assert body["items"][0]["persistedEventCount"] == 2
    assert body["items"][0]["dbEvents1m"] == 2
    assert body["items"][0]["dbVolume1mDelta"] == 80
    assert body["qualityState"] == "healthy"
    assert body["expectedSymbolCount"] == 1
    assert body["freshSymbolCount"] == 1
    assert body["missingSymbolCount"] == 0
    assert body["coveragePct"] == 100.0


def test_kiwoom_session_preserves_pre_masked_cli_account_label():
    session = KiwoomSession(
        session_token="safe-session",
        mode="live",
        account_no="****-1574 [위탁종합]",
        base_url="https://api.kiwoom.com",
        access_token="safe-access-token",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    assert session.safe_account_label == "****-1574 [위탁종합]"


def test_kiwoom_session_masks_raw_account_digits_only():
    session = KiwoomSession(
        session_token="safe-session",
        mode="live",
        account_no="61771574",
        base_url="https://api.kiwoom.com",
        access_token="safe-access-token",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    assert session.safe_account_label == "****-1574"


def test_realtime_quality_reports_partial_coverage_without_network():
    from types import SimpleNamespace

    from app.api.market import _realtime_quality

    now = datetime.now(timezone.utc)
    summaries = [
        SimpleNamespace(
            symbol="NVDA",
            lastEventAt=now.isoformat(),
            receiveDelayMs=250,
        ),
        SimpleNamespace(
            symbol="MSFT",
            lastEventAt=None,
            receiveDelayMs=None,
        ),
    ]

    quality = _realtime_quality(summaries, ["NVDA", "MSFT"])

    assert quality["qualityState"] == "degraded"
    assert quality["expectedSymbolCount"] == 2
    assert quality["freshSymbolCount"] == 1
    assert quality["missingSymbolCount"] == 1
    assert quality["staleSymbolCount"] == 0
    assert quality["coveragePct"] == 50.0
    assert quality["averageReceiveDelayMs"] == 250


def test_realtime_quality_reports_reconnecting_monitor_as_degraded():
    from types import SimpleNamespace

    from app.api.market import _realtime_quality

    now = datetime.now(timezone.utc)
    summaries = [
        SimpleNamespace(
            symbol="NVDA",
            lastEventAt=now.isoformat(),
            receiveDelayMs=120,
        ),
    ]

    quality = _realtime_quality(
        summaries,
        ["NVDA"],
        monitor_running=True,
        monitor_connected=False,
    )

    assert quality["qualityState"] == "degraded"
    assert quality["freshSymbolCount"] == 1
    assert quality["coveragePct"] == 100.0


def test_us_readonly_live_mode_missing_token_does_not_fallback_to_mock(monkeypatch):
    monkeypatch.setenv("KIWOOM_MODE", "live")
    monkeypatch.setenv("ALLOWED_USER_EMAILS", "allowed@example.com")
    monkeypatch.setenv("KIWOOM_US_READ_ONLY", "true")
    monkeypatch.setenv("KIWOOM_US_ENABLE_ORDER", "false")
    monkeypatch.setenv("KIWOOM_US_LIVE_PROVIDER", "true")
    get_settings.cache_clear()

    def verify(token: str):
        return AuthenticatedUser(email="allowed@example.com", subject="user-id")

    monkeypatch.setattr(auth_module, "verify_supabase_jwt", verify)

    response = TestClient(app).get("/api/us/account/cash", headers={"Authorization": "Bearer valid-token"})

    assert response.status_code == 400
    assert "token" in response.text.lower()
    assert "mock" not in response.text.lower()


def test_status_does_not_expose_secret_values(monkeypatch):
    monkeypatch.setenv("KIWOOM_MODE", "live")
    monkeypatch.setenv("KIWOOM_APP_KEY", "app-secret-visible-value")
    monkeypatch.setenv("KIWOOM_SECRET_KEY", "secret-visible-value")
    monkeypatch.setenv("KIWOOM_ACCOUNT_NO", "1234567890")
    get_settings.cache_clear()
    token_manager._access_token = "token-visible-value"

    response = TestClient(app).get("/api/kiwoom/status")

    assert response.status_code == 200
    body_text = response.text
    assert "token-visible-value" not in body_text
    assert "app-secret-visible-value" not in body_text
    assert "secret-visible-value" not in body_text
    assert "1234567890" not in body_text
    body = response.json()
    assert set(body) == {"mode", "readOnly", "orderEnabled", "configured", "tokenCached", "tokenExpiresAt", "missing"}
    assert body["configured"] is True
    assert body["tokenCached"] is True


def test_live_mode_missing_credentials_returns_400(monkeypatch):
    monkeypatch.setenv("KIWOOM_MODE", "live")
    monkeypatch.setenv("ALLOWED_USER_EMAILS", "allowed@example.com")
    get_settings.cache_clear()

    def verify(token: str):
        return AuthenticatedUser(email="allowed@example.com", subject="user-id")

    monkeypatch.setattr(auth_module, "verify_supabase_jwt", verify)

    response = TestClient(app).get("/api/accounts", headers={"Authorization": "Bearer valid-token"})

    assert response.status_code == 400
    assert "KIWOOM_APP_KEY" in response.text
    assert "KIWOOM_SECRET_KEY" in response.text
    assert "KIWOOM_ACCOUNT_NO" in response.text


def test_token_failure_returns_backend_error(monkeypatch):
    monkeypatch.setenv("KIWOOM_MODE", "live")
    monkeypatch.setenv("KIWOOM_APP_KEY", "configured-app-key")
    monkeypatch.setenv("KIWOOM_SECRET_KEY", "configured-secret")
    monkeypatch.setenv("KIWOOM_ACCOUNT_NO", "configured-account")
    monkeypatch.setenv("ALLOWED_USER_EMAILS", "allowed@example.com")
    get_settings.cache_clear()

    def verify(token: str):
        return AuthenticatedUser(email="allowed@example.com", subject="user-id")

    monkeypatch.setattr(auth_module, "verify_supabase_jwt", verify)

    async def fail_token():
        raise TokenManagerError("Kiwoom token HTTP error: 401")

    monkeypatch.setattr(kiwoom_module.token_manager, "get_access_token", fail_token)

    response = TestClient(app).get("/api/accounts", headers={"Authorization": "Bearer valid-token"})

    assert response.status_code == 502
    assert "configured-app-key" not in response.text
    assert "configured-secret" not in response.text
    assert "configured-account" not in response.text


class FakeTokenResponse:
    def __init__(self, body, status_code=200):
        self._body = body
        self.status_code = status_code

    def json(self):
        return self._body

    def raise_for_status(self):
        return None


class RedirectTokenResponse(FakeTokenResponse):
    def json(self):
        raise AssertionError("redirect bodies must not be parsed as token JSON")


class FakeTokenClient:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def post(self, *args, **kwargs):
        return self.response


class CapturingTokenClient(FakeTokenClient):
    def __init__(self, response, capture):
        super().__init__(response)
        self.capture = capture

    async def post(self, *args, **kwargs):
        self.capture["args"] = args
        self.capture["kwargs"] = kwargs
        return self.response


class FakeTrResponse(FakeTokenResponse):
    headers = {"cont-yn": "N", "next-key": ""}


class CapturingTrClient(FakeTokenClient):
    def __init__(self, response, capture):
        super().__init__(response)
        self.capture = capture

    async def post(self, *args, **kwargs):
        self.capture["args"] = args
        self.capture["kwargs"] = kwargs
        return self.response


class TimeoutTokenClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, *args, **kwargs):
        raise httpx.ReadTimeout("timeout")


def configure_live_token_env(monkeypatch):
    monkeypatch.setenv("KIWOOM_MODE", "live")
    monkeypatch.setenv("KIWOOM_APP_KEY", "configured-app-key")
    monkeypatch.setenv("KIWOOM_SECRET_KEY", "configured-secret")
    monkeypatch.setenv("KIWOOM_ACCOUNT_NO", "configured-account")
    get_settings.cache_clear()


def install_fake_token_response(monkeypatch, body, status_code=200):
    monkeypatch.setattr(
        "app.services.token_manager.httpx.AsyncClient",
        lambda timeout=10: FakeTokenClient(FakeTokenResponse(body, status_code=status_code)),
    )


def test_token_url_default_uses_official_path(monkeypatch):
    monkeypatch.setenv("KIWOOM_BASE_URL", "https://api.kiwoom.com")
    monkeypatch.delenv("KIWOOM_TOKEN_URL", raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.token_url == "https://api.kiwoom.com/oauth2/token"


def test_blank_token_url_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("KIWOOM_BASE_URL", "https://api.kiwoom.com/")
    monkeypatch.setenv("KIWOOM_TOKEN_URL", "   ")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.token_url == "https://api.kiwoom.com/oauth2/token"


def test_token_request_header_uses_oauth_only_content_type():
    assert TokenManager._token_request_headers() == {"Content-Type": "application/json;charset=UTF-8"}


def test_token_request_rejects_api_id_header():
    with pytest.raises(TokenManagerError):
        TokenManager._validate_token_request("https://api.kiwoom.com/oauth2/token", {"api-id": "au10001"})


def test_token_request_rejects_authorization_header():
    with pytest.raises(TokenManagerError):
        TokenManager._validate_token_request("https://api.kiwoom.com/oauth2/token", {"Authorization": "Bearer token"})


def test_token_request_rejects_wrong_path():
    with pytest.raises(TokenManagerError):
        TokenManager._validate_token_request("https://api.kiwoom.com/api/dostk/acnt", {"Content-Type": "application/json;charset=UTF-8"})


def test_token_request_rejects_wrong_body_keys():
    with pytest.raises(TokenManagerError):
        TokenManager._validate_token_request(
            "https://api.kiwoom.com/oauth2/token",
            {"Content-Type": "application/json;charset=UTF-8"},
            {"grant_type": "client_credentials", "app_key": "wrong", "secretkey": "secret"},
        )


def test_token_request_wire_summary_uses_exact_url_headers_and_body_keys():
    request = TokenManager._build_token_request(
        "https://api.kiwoom.com/oauth2/token",
        "visible-app-key",
        "visible-secret-key",
    )

    assert request["url"] == "https://api.kiwoom.com/oauth2/token"
    assert request["headers"] == {"Content-Type": "application/json;charset=UTF-8"}
    assert tuple(request["json"].keys()) == TOKEN_REQUEST_BODY_KEYS
    assert "visible-app-key" in request["json"].values()
    assert "visible-secret-key" in request["json"].values()


def test_refresh_access_token_passes_expected_wire_request(monkeypatch):
    configure_live_token_env(monkeypatch)
    capture = {}
    response = FakeTokenResponse({"token": "live-token-value", "expires_in": 3600, "return_code": 0, "return_msg": "OK"})
    monkeypatch.setattr(
        "app.services.token_manager.httpx.AsyncClient",
        lambda timeout=10: CapturingTokenClient(response, capture),
    )
    manager = TokenManager()

    asyncio.run(manager.refresh_access_token())

    assert capture["args"] == ("https://api.kiwoom.com/oauth2/token",)
    assert capture["kwargs"]["headers"] == {"Content-Type": "application/json;charset=UTF-8"}
    assert tuple(capture["kwargs"]["json"].keys()) == TOKEN_REQUEST_BODY_KEYS


def test_token_request_diagnostics_are_safe(monkeypatch, capsys):
    monkeypatch.setenv("KIWOOM_MODE", "live")
    monkeypatch.setenv("KIWOOM_BASE_URL", "https://api.kiwoom.com")
    monkeypatch.setenv("KIWOOM_APP_KEY", "visible-app-key")
    monkeypatch.setenv("KIWOOM_SECRET_KEY", "visible-secret-key")
    monkeypatch.setenv("KIWOOM_ACCOUNT_NO", "1234567890")
    get_settings.cache_clear()

    diagnostics = token_manager.token_request_diagnostics()
    print_token_request_diagnostics()

    output = capsys.readouterr().out
    assert diagnostics["path"] == TOKEN_PATH
    assert diagnostics["url_expected_match"] is True
    assert diagnostics["api_id_header_present"] is False
    assert diagnostics["header_names"] == ["content-type"]
    assert diagnostics["content_type_expected_match"] is True
    assert diagnostics["request_body_keys"] == ["grant_type", "appkey", "secretkey"]
    assert diagnostics["authorization_header_present"] is False
    assert "visible-app-key" not in output
    assert "visible-secret-key" not in output
    assert "1234567890" not in output
    assert "api_id_header_present=False" in output
    assert "request_body_keys=['grant_type', 'appkey', 'secretkey']" in output
    assert "appkey_present=True" in output
    assert "secretkey_present=True" in output
    assert "content_type_expected_match=True" in output


def test_return_msg_sanitizer_redacts_long_tokens():
    assert sanitize_return_msg("error abcdefghijklmnopqrstuvwxyz123456") == "error [redacted]"


def test_regular_account_tr_keeps_api_id_and_bearer_token(monkeypatch):
    monkeypatch.setenv("KIWOOM_MODE", "live")
    monkeypatch.setenv("KIWOOM_APP_KEY", "configured-app-key")
    monkeypatch.setenv("KIWOOM_SECRET_KEY", "configured-secret")
    monkeypatch.setenv("KIWOOM_ACCOUNT_NO", "configured-account")
    get_settings.cache_clear()
    capture = {}

    async def fake_token():
        return "live-token-value"

    monkeypatch.setattr(kiwoom_module.token_manager, "get_access_token", fake_token)
    monkeypatch.setattr(
        "app.services.kiwoom_client.httpx.AsyncClient",
        lambda timeout=10: CapturingTrClient(FakeTrResponse({"acctNo": "MOCK", "return_code": 0}), capture),
    )
    client = kiwoom_module.KiwoomClient()

    response = asyncio.run(client.request_tr("ka00001"))

    assert response.api_id == "ka00001"
    headers = capture["kwargs"]["headers"]
    assert headers["api-id"] == "ka00001"
    assert headers["Authorization"] == "Bearer live-token-value"
    assert headers["cont-yn"] == "N"
    assert headers["next-key"] == ""


def test_au10001_token_field_is_accepted(monkeypatch):
    configure_live_token_env(monkeypatch)
    install_fake_token_response(
        monkeypatch,
        {"token": "live-token-value", "token_type": "Bearer", "expires_dt": "20991231235959", "return_code": 0, "return_msg": "OK"},
    )
    manager = TokenManager()

    token = asyncio.run(manager.get_access_token())

    assert token == "live-token-value"
    assert manager._access_token == "live-token-value"


def test_au10001_expiration_datetime_is_interpreted_as_kst():
    expires_at = TokenManager._parse_expires_at({"expires_dt": "20260728013000"})

    assert expires_at == datetime(2026, 7, 27, 16, 29, tzinfo=timezone.utc)


def test_expired_active_kiwoom_session_is_not_reused(monkeypatch):
    from app.services import kiwoom_session as session_module

    expired = KiwoomSession(
        session_token="expired-session",
        mode="live",
        account_no="configured",
        base_url="https://api.kiwoom.com",
        access_token="expired-token",
        expires_at=datetime.now(timezone.utc),
    )
    session_module.set_active_kiwoom_session(expired)
    monkeypatch.setattr(session_module.kiwoom_session_manager, "get_latest_session", lambda: None)

    assert session_module.get_active_or_latest_kiwoom_session() is None
    assert session_module.get_active_kiwoom_session() is None


def test_au10001_access_token_fallback_is_accepted(monkeypatch):
    configure_live_token_env(monkeypatch)
    install_fake_token_response(
        monkeypatch,
        {"access_token": "legacy-token-value", "token_type": "Bearer", "expires_in": 3600, "return_code": 0, "return_msg": "OK"},
    )
    manager = TokenManager()

    token = asyncio.run(manager.get_access_token())

    assert token == "legacy-token-value"


def test_au10001_return_code_error_is_safe(monkeypatch):
    configure_live_token_env(monkeypatch)
    install_fake_token_response(monkeypatch, {"return_code": "999", "return_msg": "denied"})
    manager = TokenManager()

    with pytest.raises(TokenManagerError) as exc_info:
        asyncio.run(manager.get_access_token())

    message = str(exc_info.value)
    assert "return_code=999" in message
    assert "denied" in message
    assert "configured-app-key" not in message
    assert "configured-secret" not in message
    assert "configured-account" not in message
    assert exc_info.value.return_code == "999"


def test_au10001_missing_token_error_is_safe(monkeypatch):
    configure_live_token_env(monkeypatch)
    install_fake_token_response(monkeypatch, {"return_code": 0, "return_msg": "OK"})
    manager = TokenManager()

    with pytest.raises(TokenManagerError) as exc_info:
        asyncio.run(manager.get_access_token())

    message = str(exc_info.value)
    assert "did not include token" in message
    assert "configured-app-key" not in message
    assert "configured-secret" not in message
    assert "configured-account" not in message


def test_au10001_timeout_error_is_safe(monkeypatch):
    configure_live_token_env(monkeypatch)
    monkeypatch.setattr(
        "app.services.token_manager.httpx.AsyncClient",
        lambda timeout=5: TimeoutTokenClient(),
    )
    manager = TokenManager()

    with pytest.raises(TokenManagerError) as exc_info:
        asyncio.run(manager.get_access_token())

    message = str(exc_info.value)
    assert "timed out" in message
    assert exc_info.value.return_code == "TIMEOUT"
    assert exc_info.value.return_msg == "token request timed out"
    assert "configured-app-key" not in message
    assert "configured-secret" not in message
    assert "configured-account" not in message


def test_au10001_redirect_is_blocked_before_body_parsing(monkeypatch):
    configure_live_token_env(monkeypatch)
    monkeypatch.setattr(
        "app.services.token_manager.httpx.AsyncClient",
        lambda timeout=5: FakeTokenClient(RedirectTokenResponse({}, status_code=302)),
    )
    manager = TokenManager()

    with pytest.raises(TokenManagerError) as exc_info:
        asyncio.run(manager.get_access_token())

    error = exc_info.value
    assert error.http_status == 302
    assert error.return_code == "TOKEN_ENDPOINT_REDIRECT"
    assert error.return_msg == "Secure token issuance is temporarily unavailable"
    assert "configured-app-key" not in str(error)
    assert "configured-secret" not in str(error)
    assert "configured-account" not in str(error)


def test_live_verify_requires_explicit_confirm():
    with pytest.raises(LiveVerifyBlocked):
        validate_live_verify_environment(
            {
                "KIWOOM_MODE": "live",
                "KIWOOM_READ_ONLY": "true",
                "KIWOOM_ENABLE_ORDER": "false",
            }
        )


def test_live_verify_blocks_order_enabled():
    with pytest.raises(LiveVerifyBlocked):
        validate_live_verify_environment(
            {
                "KIWOOM_MODE": "live",
                "KIWOOM_READ_ONLY": "true",
                "KIWOOM_ENABLE_ORDER": "true",
                "KIWOOM_LIVE_VERIFY_CONFIRM": CONFIRM_VALUE,
            }
        )


def test_live_verify_blocks_mock_mode():
    with pytest.raises(LiveVerifyBlocked):
        validate_live_verify_environment(
            {
                "KIWOOM_MODE": "mock",
                "KIWOOM_READ_ONLY": "true",
                "KIWOOM_ENABLE_ORDER": "false",
                "KIWOOM_LIVE_VERIFY_CONFIRM": CONFIRM_VALUE,
            }
        )


def test_live_verify_environment_accepts_readonly_confirm():
    validate_live_verify_environment(
        {
            "KIWOOM_MODE": "live",
            "KIWOOM_READ_ONLY": "true",
            "KIWOOM_ENABLE_ORDER": "false",
            "KIWOOM_LIVE_VERIFY_CONFIRM": CONFIRM_VALUE,
        }
    )


def test_live_verify_loads_backend_env_file_without_export(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "KIWOOM_MODE=live\n"
        "KIWOOM_READ_ONLY=true\n"
        "KIWOOM_ENABLE_ORDER=false\n"
        f"KIWOOM_LIVE_VERIFY_CONFIRM={CONFIRM_VALUE}\n",
        encoding="utf-8",
    )
    for key in ("KIWOOM_MODE", "KIWOOM_READ_ONLY", "KIWOOM_ENABLE_ORDER", "KIWOOM_LIVE_VERIFY_CONFIRM"):
        monkeypatch.delenv(key, raising=False)

    load_backend_env_file(env_file)

    validate_live_verify_environment(dict(os.environ))


def test_safe_response_output_does_not_print_sensitive_values(capsys):
    print_safe_step_result(
        "ka00001",
        {
            "acctNo": "1234567890",
            "token": "token-visible-value",
            "balance": "999999999",
        },
    )
    output = capsys.readouterr().out
    assert "1234567890" not in output
    assert "token-visible-value" not in output
    assert "999999999" not in output
    assert "schema_keys" in output


def test_safe_failure_output_handles_mapper_error_without_name_error(capsys):
    from app.services.account_service import MapperValidationError

    print_safe_failure("ka00001", MapperValidationError("ka00001", ["acctNo"]))

    output = capsys.readouterr().out
    assert "TR=ka00001" in output
    assert "status=failed" in output
    assert "error_type=MapperValidationError" in output
    assert "acctNo" in output


def test_safe_failure_output_handles_token_error_without_sensitive_values(capsys):
    exc = TokenManagerError(
        "safe failure",
        http_status=200,
        return_code="999",
        return_msg="denied",
    )

    print_safe_failure("au10001", exc)

    output = capsys.readouterr().out
    assert "TR=au10001" in output
    assert "status=failed" in output
    assert "error_type=TokenManagerError" in output
    assert "http_status=200" in output
    assert "return_code=999" in output
    assert "safe failure" not in output


def test_supported_tr_specs_are_readonly_domestic_account_scope_only():
    assert set(TR_SPECS) == {"ka00001", "kt00001", "kt00004", "kt00005", "ka10085"}
    assert TR_SPECS["ka00001"].default_payload == {}
    assert TR_SPECS["kt00001"].default_payload == {"qry_tp": "2"}
    assert TR_SPECS["kt00004"].default_payload == {"qry_tp": "1", "dmst_stex_tp": "KRX"}
    assert TR_SPECS["kt00005"].default_payload == {"dmst_stex_tp": "KRX"}
    assert TR_SPECS["ka10085"].default_payload == {"stex_tp": "0"}


def test_ka00001_account_mapper_does_not_return_account_number():
    account = map_account_response({"acctNo": "1234567890"})
    assert account.maskedNumber == "configured"
    assert "1234567890" not in account.model_dump_json()


def test_mapper_validation_error_for_missing_required_field():
    with pytest.raises(ValueError) as exc_info:
        map_cash_response({"entr": "1000"})
    message = str(exc_info.value)
    assert "kt00001" in message
    assert "pymn_alow_amt|wdra_alow_amt" in message


def test_kt00001_cash_mapper():
    cash = map_cash_response({"entr": "0000018420000", "pymn_alow_amt": "11230000", "ord_alow_amt": "12550000"})
    assert cash.cash == 18_420_000
    assert cash.withdrawableAmount == 11_230_000
    assert cash.orderableAmount == 12_550_000


def test_kt00001_cash_mapper_uses_live_ord_alowa_fallback():
    cash = map_cash_response({"entr": "18420000", "pymn_alow_amt": "11230000", "ord_alowa": "12550000"})
    assert cash.orderableAmount == 12_550_000


def test_kt00004_portfolio_mapper():
    portfolio = map_portfolio_response(
        {"aset_evlt_amt": "52184300", "tdy_lspft": "312500", "tdy_lspft_rt": "0.61", "lspft": "2184300"},
        cash=18_420_000,
    )
    assert portfolio.equity == 52_184_300
    assert portfolio.cash == 18_420_000
    assert portfolio.dayPnl == 312_500
    assert portfolio.dayPnlPct == 0.61
    assert portfolio.cumulativePnl == 2_184_300


def test_kt00004_portfolio_mapper_uses_live_amount_fallbacks():
    portfolio = map_portfolio_response(
        {"prsm_dpst_aset_amt": "52,184,300", "tdy_lspft_amt": "+312,500", "lspft_amt": "-2,184,300", "lspft_ratio": "0.61"},
        cash=18_420_000,
    )
    assert portfolio.equity == 52_184_300
    assert portfolio.dayPnl == 312_500
    assert portfolio.cumulativePnl == -2_184_300
    assert portfolio.dayPnlPct == 0.61


def test_kt00005_holdings_mapper():
    holdings = map_holdings_response(
        [
            {"stk_cd": "A005930", "stk_nm": "삼성전자", "cur_qty": "20", "buy_uv": "71350", "cur_prc": "71800", "evlt_amt": "1436000", "evltv_prft": "9000", "pl_rt": "0.63"},
            {"stk_cd": "A000660", "stk_nm": "SK하이닉스", "cur_qty": "4", "buy_uv": "195200", "cur_prc": "198500", "evlt_amt": "794000", "evltv_prft": "13200", "pl_rt": "1.69"},
        ]
    )
    assert holdings[0].code == "005930"
    assert holdings[0].quantity == 20
    assert holdings[0].valuationAmount == 1_436_000
    assert holdings[1].profitLoss == 13_200


def test_kt00005_holdings_mapper_allows_empty_live_list():
    assert map_holdings_response([]) == []


def test_ka10085_performance_mapper():
    performance = map_performance_response(
        [
            {"stk_cd": "005930", "stk_nm": "삼성전자", "rmnd_qty": "20", "pur_pric": "71350", "cur_prc": "71800", "pur_amt": "1427000"},
            {"stk_cd": "000660", "stk_nm": "SK하이닉스", "rmnd_qty": "4", "pur_pric": "195200", "cur_prc": "198500", "pur_amt": "780800"},
        ]
    )
    assert len(performance.items) == 2
    assert performance.totalPurchaseAmount == 2_207_800
    assert performance.totalValuationAmount == 2_230_000
    assert performance.totalProfitLoss == 22_200


def test_parse_number_helpers_handle_sign_commas_and_blanks():
    assert parse_int("+1,234") == 1234
    assert parse_int("-1,234") == -1234
    assert parse_int("") == 0
    assert parse_float("+1.25") == 1.25
    assert parse_float("") == 0.0


def test_kiwoom_mapper_contract_fixtures_match_shapes():
    account = {"acctNo": "configured"}
    cash = {"entr": "18420000", "pymn_alow_amt": "11230000", "ord_alow_amt": "12550000"}
    portfolio = {"aset_evlt_amt": "52184300", "tdy_lspft_amt": "312500", "lspft_amt": "2184300"}
    holdings = {
        "stk_cntr_remn": [
            {"stk_cd": "000001", "stk_nm": "FIXTURE", "cur_qty": "10", "buy_uv": "10000", "cur_prc": "10500", "evlt_amt": "105000"}
        ]
    }
    performance = {
        "acnt_prft_rt": [
            {"stk_cd": "000001", "stk_nm": "FIXTURE", "rmnd_qty": "10", "pur_pric": "10000", "cur_prc": "10500", "pur_amt": "100000"}
        ]
    }

    assert map_account_response(account).maskedNumber == "configured"
    assert map_cash_response(cash).cash == 18_420_000
    assert map_portfolio_response(portfolio, cash=18_420_000).equity == 52_184_300
    assert len(map_holdings_response(holdings["stk_cntr_remn"])) == 1
    assert len(map_performance_response(performance["acnt_prft_rt"]).items) == 1


def test_mapper_validation_error_does_not_include_sensitive_values():
    with pytest.raises(ValueError) as exc_info:
        map_holdings_response([{"stk_cd": "1234567890", "stk_nm": "SENSITIVE NAME"}])

    message = str(exc_info.value)
    assert "cur_prc" in message
    assert "evlt_amt" in message
    assert "1234567890" not in message
    assert "SENSITIVE NAME" not in message


def test_continuation_query_merges_list_items(monkeypatch):
    calls: list[tuple[str, str]] = []

    async def fake_request_tr(api_id, payload=None, cont_yn="N", next_key=""):
        calls.append((cont_yn, next_key))
        if cont_yn == "N":
            return KiwoomResponse(api_id=api_id, body={"acnt_prft_rt": [{"stk_cd": "005930"}]}, cont_yn="Y", next_key="next-1")
        return KiwoomResponse(api_id=api_id, body={"acnt_prft_rt": [{"stk_cd": "000660"}]}, cont_yn="N", next_key="")

    client = kiwoom_module.KiwoomClient()
    monkeypatch.setattr(client, "request_tr", fake_request_tr)

    response = asyncio.run(client.request_tr_all("ka10085", {"stex_tp": "0"}))

    assert calls == [("N", ""), ("Y", "next-1")]
    assert response.body["acnt_prft_rt"] == [{"stk_cd": "005930"}, {"stk_cd": "000660"}]


def test_us_live_order_direct_call_requires_server_precheck(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace

    from app.schemas.us_order import UsOrderRequest
    from app.services.kiwoom_session import KiwoomSession, set_active_kiwoom_session
    from app.services import us_order_service as order_module

    monkeypatch.setenv("KIWOOM_READ_ONLY", "false")
    monkeypatch.setenv("KIWOOM_US_ENABLE_ORDER", "true")
    monkeypatch.setenv("KIWOOM_US_ORDER_CONFIRM", "I_UNDERSTAND_LIVE_US_ORDER")
    monkeypatch.setenv("KIWOOM_US_ALLOWED_SYMBOLS", "AAPL")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_QUANTITY", "1")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_NOTIONAL", "500")
    set_active_kiwoom_session(
        KiwoomSession(
            session_token="safe-session",
            mode="live",
            account_no="masked-account",
            base_url="https://api.kiwoom.com",
            access_token="token-never-printed",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    )

    async def fake_orderability(*args, **kwargs):
        return SimpleNamespace(data={"min_ord_alowq": "1", "min_ord_alowa": "500", "crnc_code": "USD", "aplc_rt": "100%"})

    monkeypatch.setattr(order_module.us_account_service, "_execute", fake_orderability)

    payload = UsOrderRequest(
        side="buy",
        exchange="ND",
        symbol="NVDA",
        quantity=1,
        referencePrice="100",
        tradeType="03",
        confirmText="I_UNDERSTAND_LIVE_US_ORDER",
    )

    precheck = asyncio.run(order_module.us_order_service.precheck_order(payload))
    assert precheck.canSubmit is False
    assert "SYMBOL_NOT_ALLOWED" in precheck.blockedReasons
    with pytest.raises(order_module.UsOrderBlocked) as exc_info:
        asyncio.run(order_module.us_order_service.place_order(payload))
    assert str(exc_info.value) == "LIVE_ORDER_EXECUTION_NOT_IMPLEMENTED"
    assert "token-never-printed" not in str(exc_info.value)
    set_active_kiwoom_session(None)


def test_us_readonly_internal_call_uses_latest_kiwoom_session(monkeypatch):
    from datetime import timedelta

    from app.services.kiwoom_session import KiwoomSession, kiwoom_session_manager, set_active_kiwoom_session
    from app.services.us_account_service import us_account_service
    from trading_engine.providers.kiwoom_us.schemas import PreparedUsHttpRequest

    monkeypatch.setenv("KIWOOM_MODE", "live")
    get_settings.cache_clear()
    session = KiwoomSession(
        session_token="latest-session-token",
        mode="live",
        account_no="masked-account",
        base_url="https://api.kiwoom.com",
        access_token="token-never-printed",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    kiwoom_session_manager._sessions[session.session_token] = session
    kiwoom_session_manager._latest_session_token = session.session_token
    set_active_kiwoom_session(None)

    captured: dict[str, object] = {}

    class FakeSender:
        def send(self, request: PreparedUsHttpRequest) -> dict[str, object]:
            captured["url"] = request.url
            captured["api_id"] = request.headers.get("api-id")
            captured["has_authorization"] = "Authorization" in request.headers
            assert "token-never-printed" not in repr(request.body)
            return {"return_code": "0", "return_msg": "OK", "result_list": []}

    monkeypatch.setattr("app.services.us_account_service.KiwoomUsUrllibHttpSender", lambda **kwargs: FakeSender())

    summary = asyncio.run(us_account_service.get_holdings())

    assert summary.trId == "ust21070"
    assert captured == {
        "url": "https://api.kiwoom.com/api/us/acnt",
        "api_id": "ust21070",
        "has_authorization": True,
    }
    set_active_kiwoom_session(None)
    kiwoom_session_manager.revoke_session(session.session_token)


def test_us_live_order_requires_explicit_server_unlock_before_sender(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace

    from app.schemas.us_order import UsOrderRequest
    from app.services.kiwoom_session import KiwoomSession, set_active_kiwoom_session
    from app.services import us_order_service as order_module

    monkeypatch.setenv("KIWOOM_READ_ONLY", "false")
    monkeypatch.setenv("KIWOOM_US_ENABLE_ORDER", "true")
    monkeypatch.setenv("KIWOOM_US_ORDER_CONFIRM", "I_UNDERSTAND_LIVE_US_ORDER")
    monkeypatch.setenv("KIWOOM_US_ALLOWED_SYMBOLS", "NVDA")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_QUANTITY", "1")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_NOTIONAL", "500")
    set_active_kiwoom_session(
        KiwoomSession(
            session_token="safe-session",
            mode="live",
            account_no="masked-account",
            base_url="https://api.kiwoom.com",
            access_token="token-never-printed",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    )

    async def fake_orderability(*args, **kwargs):
        return SimpleNamespace(data={"min_ord_alowq": "1", "min_ord_alowa": "500", "crnc_code": "USD", "aplc_rt": "100%"})

    monkeypatch.setattr(order_module.us_account_service, "_execute", fake_orderability)

    payload = UsOrderRequest(
        side="buy",
        exchange="ND",
        symbol="NVDA",
        quantity=1,
        referencePrice="100",
        tradeType="03",
        confirmText="I_UNDERSTAND_LIVE_US_ORDER",
    )

    precheck = asyncio.run(order_module.us_order_service.precheck_order(payload))
    assert precheck.canSubmit is True
    assert precheck.blockedReasons == []

    with pytest.raises(order_module.UsOrderBlocked) as exc_info:
        asyncio.run(order_module.us_order_service.place_order(payload))

    assert str(exc_info.value) == "LIVE_ORDER_EXECUTION_NOT_IMPLEMENTED"
    assert "token-never-printed" not in str(exc_info.value)
    set_active_kiwoom_session(None)


def test_us_live_order_direct_call_blocks_orderable_quantity_before_sender(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace

    from app.schemas.us_order import UsOrderRequest
    from app.services.kiwoom_session import KiwoomSession, set_active_kiwoom_session
    from app.services import us_order_service as order_module

    monkeypatch.setenv("KIWOOM_READ_ONLY", "false")
    monkeypatch.setenv("KIWOOM_US_ENABLE_ORDER", "true")
    monkeypatch.setenv("KIWOOM_US_ORDER_CONFIRM", "I_UNDERSTAND_LIVE_US_ORDER")
    monkeypatch.setenv("KIWOOM_US_ALLOWED_SYMBOLS", "NVDA")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_QUANTITY", "1")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_NOTIONAL", "500")
    set_active_kiwoom_session(
        KiwoomSession(
            session_token="safe-session",
            mode="live",
            account_no="masked-account",
            base_url="https://api.kiwoom.com",
            access_token="token-never-printed",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    )

    async def fake_orderability(*args, **kwargs):
        return SimpleNamespace(data={"min_ord_alowq": "0", "min_ord_alowa": "0", "crnc_code": "USD", "aplc_rt": "100%"})

    monkeypatch.setattr(order_module.us_account_service, "_execute", fake_orderability)

    payload = UsOrderRequest(
        side="buy",
        exchange="ND",
        symbol="NVDA",
        quantity=1,
        referencePrice="100",
        tradeType="03",
        confirmText="I_UNDERSTAND_LIVE_US_ORDER",
    )

    precheck = asyncio.run(order_module.us_order_service.precheck_order(payload))
    assert precheck.canSubmit is False
    assert "ORDERABLE_QUANTITY_EXCEEDED" in precheck.blockedReasons
    with pytest.raises(order_module.UsOrderBlocked) as exc_info:
        asyncio.run(order_module.us_order_service.place_order(payload))
    assert str(exc_info.value) == "LIVE_ORDER_EXECUTION_NOT_IMPLEMENTED"
    assert "token-never-printed" not in str(exc_info.value)
    set_active_kiwoom_session(None)


def test_us_liquidation_plan_uses_ust21070_official_holding_fields(monkeypatch):
    from types import SimpleNamespace

    from app.services import us_order_service as order_module
    from app.services.us_account_service import map_holdings_for_order

    mapped = map_holdings_for_order(
        {
            "result_list": [
                {
                    "stex_nm": "NASDAQ",
                    "stk_cd": "NVDA",
                    "qty": "000000000002",
                    "poss_qty": "000000000002",
                    "sell_alowq": "000000000001",
                    "now_pric": "182.5000",
                }
            ]
        },
        max_quantity=1,
    )
    assert mapped[0].symbol == "NVDA"
    assert mapped[0].exchange == "ND"
    assert mapped[0].sellableQuantity == 1
    assert mapped[0].price == 182.5
    assert mapped[0].rawQuantityField == "sell_alowq"
    assert mapped[0].rawExchangeField == "stex_nm"
    assert mapped[0].rawExchangeValue == "NASDAQ"
    assert mapped[0].blockedReasons == []

    monkeypatch.setenv("KIWOOM_READ_ONLY", "false")
    monkeypatch.setenv("KIWOOM_US_ENABLE_ORDER", "true")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_QUANTITY", "1")

    async def fake_holdings(*args, **kwargs):
        return SimpleNamespace(
            data={
                "result_list": [
                    {
                        "stex_nm": "NASDAQ",
                        "stk_cd": "NVDA",
                        "qty": "000000000002",
                        "poss_qty": "000000000002",
                        "sell_alowq": "000000000001",
                        "now_pric": "182.5000",
                    }
                ]
            }
        )

    monkeypatch.setattr(order_module.us_account_service, "get_holdings", fake_holdings)

    plan = asyncio.run(order_module.us_order_service.get_liquidation_plan())

    assert plan.enabled is True
    assert plan.executableCount == 1
    assert plan.totalCount == 1
    assert plan.blockedReasons == []
    assert plan.holdings[0].symbol == "NVDA"
    assert plan.holdings[0].exchange == "ND"
    assert plan.holdings[0].quantity == 1
    assert plan.holdings[0].price == 182.5
    assert plan.holdings[0].rawQuantityField == "sell_alowq"
    assert plan.holdings[0].rawExchangeField == "stex_nm"
    assert plan.holdings[0].rawExchangeValue == "NASDAQ"


def test_us_liquidation_plan_maps_common_exchange_aliases():
    from app.services.us_account_service import map_holdings_for_order

    mapped = map_holdings_for_order(
        {
            "result_list": [
                {"stex_nm": "나스닥", "stk_cd": "NVDA", "sell_alowq": "1"},
                {"stex_nm": "뉴욕증권거래소", "stk_cd": "A", "sell_alowq": "1"},
                {"stex_nm": "아멕스", "stk_cd": "GLD", "sell_alowq": "1"},
                {"stex_nm": "NASD", "stk_cd": "MSFT", "sell_alowq": "1"},
                {"stex_nm": "NYSE American", "stk_cd": "BTG", "sell_alowq": "1"},
            ]
        },
        max_quantity=1,
    )

    assert [item.exchange for item in mapped] == ["ND", "NY", "NA", "ND", "NA"]
    assert all(item.blockedReasons == [] for item in mapped)


def test_us_liquidation_plan_blocks_when_sellable_quantity_exceeds_policy(monkeypatch):
    from types import SimpleNamespace

    from app.services import us_order_service as order_module

    monkeypatch.setenv("KIWOOM_READ_ONLY", "false")
    monkeypatch.setenv("KIWOOM_US_ENABLE_ORDER", "true")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_QUANTITY", "1")

    async def fake_holdings(*args, **kwargs):
        return SimpleNamespace(
            data={
                "result_list": [
                    {
                        "stex_nm": "NYSE",
                        "stk_cd": "AAPL",
                        "sell_alowq": "000000000003",
                        "now_pric": "12.3400",
                    }
                ]
            }
        )

    monkeypatch.setattr(order_module.us_account_service, "get_holdings", fake_holdings)

    plan = asyncio.run(order_module.us_order_service.get_liquidation_plan())

    assert plan.executableCount == 0
    assert plan.totalCount == 1
    assert "NO_EXECUTABLE_HOLDINGS" in plan.blockedReasons
    assert "MAX_ORDER_QUANTITY_EXCEEDED" in plan.holdings[0].blockedReasons


def test_us_liquidation_plan_blocks_without_ust21070_rows(monkeypatch):
    from types import SimpleNamespace

    from app.services import us_order_service as order_module

    monkeypatch.setenv("KIWOOM_READ_ONLY", "false")
    monkeypatch.setenv("KIWOOM_US_ENABLE_ORDER", "true")

    async def fake_holdings(*args, **kwargs):
        return SimpleNamespace(data={"result_list": []})

    monkeypatch.setattr(order_module.us_account_service, "get_holdings", fake_holdings)

    plan = asyncio.run(order_module.us_order_service.get_liquidation_plan())

    assert plan.executableCount == 0
    assert plan.totalCount == 0
    assert plan.holdings == []
    assert "NO_HOLDINGS_ROWS_FOUND" in plan.blockedReasons


def test_us_liquidation_plan_blocks_unsupported_exchange_value(monkeypatch):
    from types import SimpleNamespace

    from app.services import us_order_service as order_module
    from app.services.us_account_service import map_holdings_for_order

    mapped = map_holdings_for_order(
        {
            "result_list": [
                {
                    "stex_nm": "미국",
                    "stk_cd": "STAK",
                    "sell_alowq": "000000000001",
                    "now_pric": "3.4600",
                }
            ]
        },
        max_quantity=1,
    )
    assert mapped[0].rawExchangeField == "stex_nm"
    assert mapped[0].rawExchangeValue == "미국"
    assert "UNSUPPORTED_EXCHANGE_VALUE" in mapped[0].blockedReasons

    monkeypatch.setenv("KIWOOM_READ_ONLY", "false")
    monkeypatch.setenv("KIWOOM_US_ENABLE_ORDER", "true")
    monkeypatch.setenv("KIWOOM_US_MAX_ORDER_QUANTITY", "1")

    async def fake_holdings(*args, **kwargs):
        return SimpleNamespace(
            data={
                "result_list": [
                    {
                        "stex_nm": "미국",
                        "stk_cd": "STAK",
                        "sell_alowq": "000000000001",
                        "now_pric": "3.4600",
                    }
                ]
            }
        )

    monkeypatch.setattr(order_module.us_account_service, "get_holdings", fake_holdings)

    plan = asyncio.run(order_module.us_order_service.get_liquidation_plan())

    assert plan.executableCount == 0
    assert "NO_EXECUTABLE_HOLDINGS" in plan.blockedReasons
    assert plan.holdings[0].rawExchangeField == "stex_nm"
    assert plan.holdings[0].rawExchangeValue == "미국"
    assert "UNSUPPORTED_EXCHANGE_VALUE" in plan.holdings[0].blockedReasons


def test_us_order_followup_queries_use_official_us_account_contract(monkeypatch):
    from types import SimpleNamespace

    from app.services import us_account_service as account_module

    calls: list[tuple[str, dict[str, object]]] = []

    async def fake_execute(tr_id, body=None):
        calls.append((tr_id, body or {}))
        return SimpleNamespace(
            tr_id=tr_id,
            return_code="0",
            return_msg="OK",
            data={"result_list": []},
        )

    monkeypatch.setattr(account_module.us_account_service, "_execute", fake_execute)

    asyncio.run(account_module.us_account_service.get_holdings(exchange="ND", symbol="NVDA"))
    asyncio.run(account_module.us_account_service.get_open_orders(symbol="NVDA", side="2"))
    asyncio.run(account_module.us_account_service.get_today_order_fills(symbol="NVDA", exchange="ND", side="2"))

    assert calls == [
        ("ust21070", {"stex_tp": "ND", "stk_cd": "NVDA"}),
        ("ust21050", {"ord_dt": "", "slby_tp": "2", "stk_code": "NVDA"}),
        ("ust21510", {"slby_tp": "2", "stex_tp": "ND", "stk_cd": "NVDA"}),
    ]


def test_us_order_followup_merges_continuation_pages_conservatively(
    monkeypatch,
):
    from app.services import us_account_service as account_module
    from trading_engine.providers.kiwoom_us.schemas import UsReadOnlyTrResponse

    calls: list[tuple[str, str]] = []
    first_row = {"ord_no": "order-a", "cntr_qty": "1"}
    second_row = {"ord_no": "order-b", "cntr_qty": "1"}

    async def fake_execute(
        tr_id,
        body=None,
        *,
        cont_yn="N",
        next_key="",
    ):
        calls.append((cont_yn, next_key))
        if cont_yn == "N":
            return UsReadOnlyTrResponse(
                tr_id=tr_id,
                return_code="0",
                return_msg="OK",
                data={"result_list": [first_row]},
                cont_yn="Y",
                next_key="page-2",
            )
        return UsReadOnlyTrResponse(
            tr_id=tr_id,
            return_code="0",
            return_msg="OK",
            data={"result_list": [first_row, second_row]},
            cont_yn="N",
            next_key="",
        )

    monkeypatch.setattr(
        account_module.us_account_service,
        "_execute",
        fake_execute,
    )

    summary = asyncio.run(
        account_module.us_account_service.get_today_order_fills(
            symbol="NVDA",
            exchange="ND",
            side="2",
        )
    )

    assert calls == [("N", ""), ("Y", "page-2")]
    assert summary.data["result_list"] == [first_row, second_row]


def test_us_order_followup_rejects_repeated_continuation_key(monkeypatch):
    from app.services import us_account_service as account_module
    from trading_engine.providers.kiwoom_us.schemas import UsReadOnlyTrResponse

    async def fake_execute(
        tr_id,
        body=None,
        *,
        cont_yn="N",
        next_key="",
    ):
        return UsReadOnlyTrResponse(
            tr_id=tr_id,
            return_code="0",
            return_msg="OK",
            data={"result_list": []},
            cont_yn="Y",
            next_key="repeated",
        )

    monkeypatch.setattr(
        account_module.us_account_service,
        "_execute",
        fake_execute,
    )

    with pytest.raises(
        account_module.UsReadOnlyConfigurationError,
        match="continuation metadata",
    ):
        asyncio.run(
            account_module.us_account_service.get_open_orders(
                symbol="NVDA",
                side="2",
            )
        )
