from __future__ import annotations

import sys

import pytest

from trading_engine.providers.kiwoom_us import (
    KiwoomUsRestClientSkeleton,
    UsMappingError,
    build_account_balance_request,
    build_daily_account_return_request,
    build_profit_loss_request,
    build_realtime_price_subscription,
    map_us_account_balance_response,
    map_us_condition_search_response,
)
from trading_engine.providers.kiwoom_us.response_mapper import map_daily_account_return_response, map_profit_loss_response, map_readonly_response
from trading_engine.providers.kiwoom_us.safety import (
    UsLiveProviderDisabledError,
    UsOrderBlockedError,
    assert_us_order_tr_blocked,
    assert_us_readonly_tr_allowed,
    assert_us_realtime_channel_allowed,
    us_blocked_order_tr_codes,
    us_readonly_tr_codes,
)
from trading_engine.providers.kiwoom_us.schemas import UsRealtimeSymbol


def test_us_readonly_tr_allow_list_and_blocked_orders():
    for tr_id in ["usa20280", "usa20281", "usa20290", "usa20291", "FE", "FT", "ust21110", "ust21120", "ust21150", "ust21510", "ust21630", "ust21650", "usa21670"]:
        assert assert_us_readonly_tr_allowed(tr_id).tr_id == tr_id
        assert tr_id in us_readonly_tr_codes()

    for tr_id in ["ust20000", "ust20001", "ust20002", "ust20003", "F4", "F5"]:
        assert tr_id in us_blocked_order_tr_codes()
        with pytest.raises(UsOrderBlockedError):
            assert_us_order_tr_blocked(tr_id)


def test_us_realtime_channel_safety_allows_fe_ft_and_blocks_order_channels():
    assert assert_us_realtime_channel_allowed("FE").tr_id == "FE"
    assert assert_us_realtime_channel_allowed("FT").tr_id == "FT"

    for tr_id in ["F4", "F5"]:
        with pytest.raises(UsOrderBlockedError):
            assert_us_realtime_channel_allowed(tr_id)


def test_us_rest_client_builds_readonly_request_shape_without_transport():
    client = KiwoomUsRestClientSkeleton(access_token_present=True, live_provider_enabled=False)
    request = client.build_readonly_tr_request("ust21110")

    assert request.tr_id == "ust21110"
    assert request.endpoint == "/api/us/acnt"
    assert request.method == "POST"
    assert request.headers["api-id"] == "ust21110"
    assert request.headers["Authorization"] == "Bearer <redacted>"
    assert request.body == {}
    assert request.read_only is True


def test_us_rest_client_blocks_before_any_live_transport_execution():
    client = KiwoomUsRestClientSkeleton(access_token_present=True, live_provider_enabled=False)

    with pytest.raises(UsLiveProviderDisabledError):
        client.execute_readonly_tr("ust21110")


def test_us_rest_client_order_path_is_unconditionally_blocked():
    client = KiwoomUsRestClientSkeleton(access_token_present=True, live_provider_enabled=True)

    with pytest.raises(UsOrderBlockedError):
        client.place_order("ust20000")


def test_us_rest_skeleton_does_not_import_network_clients():
    for module_name in ["httpx", "requests", "websockets"]:
        sys.modules.pop(module_name, None)

    client = KiwoomUsRestClientSkeleton()
    client.build_readonly_tr_request("ust21650", {"fr_dt": "20260701", "to_dt": "20260710"})

    assert "httpx" not in sys.modules
    assert "requests" not in sys.modules
    assert "websockets" not in sys.modules


def test_us_adapter_readonly_request_helpers():
    cash = build_account_balance_request()
    pnl = build_profit_loss_request("ust21630", {"fc_krw_tp": "1"})
    daily_return = build_daily_account_return_request("20260501", "20260511")
    subscription = build_realtime_price_subscription([UsRealtimeSymbol("NVDA", "NASD")])

    assert cash.tr_id == "ust21110"
    assert pnl.tr_id == "ust21630"
    assert pnl.body["fc_krw_tp"] == "1"
    assert daily_return.tr_id == "usa21670"
    assert daily_return.body == {"from": "20260501", "to": "20260511"}
    assert subscription.to_packet()["data"][0]["type"] == ["FE"]


def test_us_daily_account_return_request_validates_dates():
    with pytest.raises(ValueError, match="YYYYMMDD"):
        build_daily_account_return_request("2026-05-01", "20260511")


def test_us_response_mappers_preserve_unknown_fields():
    response = map_readonly_response("ust21110", {"return_code": "0", "return_msg": "OK", "krw_entra": "1000"})
    balance = map_us_account_balance_response({"return_code": "0", "return_msg": "OK", "krw_entra": "1000", "custom": "kept"})
    pnl = map_profit_loss_response("ust21630", {"return_code": "0", "return_msg": "OK", "rlzt_pl": "10", "pl_rt": "1.2", "extra": "kept"})

    assert response.data["krw_entra"] == "1000"
    assert balance.cash == "1000"
    assert balance.unknown_fields["custom"] == "kept"
    assert pnl.realized_profit_loss == "10"
    assert pnl.unknown_fields["extra"] == "kept"


def test_us_daily_account_return_mapper():
    result = map_daily_account_return_response(
        {
            "return_code": "0",
            "return_msg": "OK",
            "result_lsit": [
                {
                    "wo_base_dt": "20260501",
                    "wo_stk_evlta": "1000",
                    "wo_pl_amt": "-10",
                    "wo_dvid_amt": "0",
                    "wo_cmsn_tax": "1",
                    "wo_acum_pl_amt": "+20",
                    "wo_pymn_amt": "0",
                    "wo_dast": "990",
                    "wo_dly_amt": "0",
                    "wo_sell_amt": "100",
                    "wo_buy_amt": "90",
                    "wo_prft_rt": "+1.23",
                    "wo_frgn_stk_outq_amt": "0",
                    "wo_frgn_stk_inq_amt": "0",
                    "wo_ina_amt": "0",
                    "wo_exrt": "1370.00",
                    "extra": "kept",
                }
            ],
            "top_level_extra": "kept",
        }
    )

    assert result.tr_id == "usa21670"
    assert len(result.rows) == 1
    assert result.rows[0].base_dt == "20260501"
    assert result.rows[0].prft_rt == "+1.23"
    assert result.rows[0].unknown_fields["extra"] == "kept"
    assert result.unknown_fields["top_level_extra"] == "kept"


def test_us_daily_account_return_mapper_rejects_invalid_result_list_shape():
    with pytest.raises(UsMappingError, match="result_list"):
        map_daily_account_return_response({"return_code": "0", "return_msg": "OK", "result_list": {}})


def test_us_condition_search_response_mapper():
    result = map_us_condition_search_response(
        {
            "seq": "001",
            "name": "US momentum",
            "items": [{"jmcode": "NVDA"}, {"stk_cd": "TSLA"}, "AAPL"],
            "extra": "kept",
        }
    )

    assert result.condition_id == "001"
    assert result.condition_name == "US momentum"
    assert result.symbols == ["NVDA", "TSLA", "AAPL"]
    assert result.unknown_fields["extra"] == "kept"


def test_us_response_mapper_missing_required_field_raises_safe_error():
    with pytest.raises(UsMappingError, match="return_code"):
        map_us_account_balance_response({"return_msg": "OK"})
