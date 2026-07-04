from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.services import kiwoom_client as kiwoom_module
from app.services.account_service import (
    map_account_response,
    map_cash_response,
    map_holdings_response,
    map_performance_response,
    map_portfolio_response,
)
from app.services.kiwoom_client import KiwoomConfigurationError, KiwoomResponse, TR_SPECS
from app.services.token_manager import TokenManagerError, token_manager
from scripts.verify_live_readonly import (
    CONFIRM_VALUE,
    LiveVerifyBlocked,
    print_safe_step_result,
    validate_live_verify_environment,
)


@pytest.fixture(autouse=True)
def reset_settings_and_token(monkeypatch):
    for key in (
        "KIWOOM_MODE",
        "KIWOOM_APP_KEY",
        "KIWOOM_SECRET_KEY",
        "KIWOOM_APP_SECRET",
        "KIWOOM_ACCOUNT_NO",
        "KIWOOM_READ_ONLY",
        "KIWOOM_ENABLE_ORDER",
    ):
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    token_manager._access_token = None
    token_manager._expires_at = None
    yield
    get_settings.cache_clear()
    token_manager._access_token = None
    token_manager._expires_at = None


def test_mock_mode_is_default_and_health_loads():
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "mock"
    assert body["kiwoom"]["readOnly"] is True
    assert body["kiwoom"]["orderEnabled"] is False
    for path in (
        "/api/kiwoom/status",
        "/api/accounts",
        "/api/account/cash",
        "/api/account/portfolio",
        "/api/account/performance",
        "/api/account/holdings",
        "/api/market/watchlist",
    ):
        assert client.get(path).status_code == 200


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
    get_settings.cache_clear()

    response = TestClient(app).get("/api/accounts")

    assert response.status_code == 400
    assert "KIWOOM_APP_KEY" in response.text
    assert "KIWOOM_SECRET_KEY" in response.text
    assert "KIWOOM_ACCOUNT_NO" in response.text


def test_token_failure_returns_backend_error(monkeypatch):
    monkeypatch.setenv("KIWOOM_MODE", "live")
    monkeypatch.setenv("KIWOOM_APP_KEY", "configured-app-key")
    monkeypatch.setenv("KIWOOM_SECRET_KEY", "configured-secret")
    monkeypatch.setenv("KIWOOM_ACCOUNT_NO", "configured-account")
    get_settings.cache_clear()

    async def fail_token():
        raise TokenManagerError("Kiwoom token HTTP error: 401")

    monkeypatch.setattr(kiwoom_module.token_manager, "get_access_token", fail_token)

    response = TestClient(app).get("/api/accounts")

    assert response.status_code == 502
    assert "configured-app-key" not in response.text
    assert "configured-secret" not in response.text
    assert "configured-account" not in response.text


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


def test_supported_tr_specs_are_readonly_account_scope_only():
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
