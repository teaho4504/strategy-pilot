from __future__ import annotations

import asyncio
import os

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
    parse_float,
    parse_int,
)
from app.services.kiwoom_client import KiwoomConfigurationError, KiwoomResponse, TR_SPECS
from app.services.token_manager import TOKEN_PATH, TOKEN_REQUEST_BODY_KEYS, TokenManager, TokenManagerError, token_manager
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
def reset_settings_and_token(monkeypatch):
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


class FakeTokenResponse:
    def __init__(self, body, status_code=200):
        self._body = body
        self.status_code = status_code

    def json(self):
        return self._body

    def raise_for_status(self):
        return None


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


def test_kiwoom_mock_responses_match_mapper_shapes():
    client = kiwoom_module.KiwoomClient()
    account = client._mock_response("ka00001")
    cash = client._mock_response("kt00001")
    portfolio = client._mock_response("kt00004")
    holdings = client._mock_response("kt00005")
    performance = client._mock_response("ka10085")

    assert map_account_response(account).maskedNumber == "configured"
    assert map_cash_response(cash).cash == 18_420_000
    assert map_portfolio_response(portfolio, cash=18_420_000).equity == 52_184_300
    assert len(map_holdings_response(holdings["stk_cntr_remn"])) == 1
    assert len(map_performance_response(performance["acnt_prft_rt"]).items) == 2


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
