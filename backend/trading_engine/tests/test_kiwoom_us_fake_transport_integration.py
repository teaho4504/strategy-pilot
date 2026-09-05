from __future__ import annotations

import sys

import pytest

from trading_engine.providers.kiwoom_us.credentials import KiwoomUsCredentialConfig
from trading_engine.providers.kiwoom_us.response_mapper import map_account_balance_response, map_condition_search_response, map_profit_loss_response
from trading_engine.providers.kiwoom_us.rest_client import KiwoomUsRestClientSkeleton
from trading_engine.providers.kiwoom_us.safety import UsLiveProviderDisabledError, UsOrderBlockedError
from trading_engine.providers.kiwoom_us.schemas import UsReadOnlyTrResponse
from trading_engine.providers.kiwoom_us.transport import FakeKiwoomUsTransport


def test_us_fake_transport_account_balance_integration_flow():
    config = KiwoomUsCredentialConfig.from_mapping(
        {
            "KIWOOM_US_APP_KEY": "configured",
            "KIWOOM_US_APP_SECRET": "configured",
            "KIWOOM_US_ACCOUNT_NO": "configured",
            "KIWOOM_US_READ_ONLY": "true",
            "KIWOOM_US_ENABLE_ORDER": "false",
        },
        source="fixture",
    )
    transport = FakeKiwoomUsTransport(
        responses={
            "ust21110": UsReadOnlyTrResponse(
                tr_id="ust21110",
                return_code="0",
                return_msg="OK",
                data={"krw_entra": "1000", "ord_alow_amt": "900", "custom_field": "kept"},
                unknown_fields={"krw_entra": "1000", "ord_alow_amt": "900", "custom_field": "kept"},
            )
        }
    )
    client = KiwoomUsRestClientSkeleton(
        access_token_present=bool(config.token),
        live_provider_enabled=True,
        read_only=config.read_only,
        order_enabled=config.order_enabled,
        transport=transport,
    )

    response = client.execute_readonly_tr("ust21110")
    mapped = map_account_balance_response(response.tr_id, {"return_code": response.return_code, "return_msg": response.return_msg, **response.data})

    assert mapped.tr_id == "ust21110"
    assert mapped.cash == "1000"
    assert mapped.orderable_cash == "900"
    assert mapped.unknown_fields["custom_field"] == "kept"
    assert len(transport.sent_requests) == 1
    assert transport.sent_requests[0].headers["api-id"] == "ust21110"
    assert "Authorization" not in transport.sent_requests[0].headers


def test_us_fake_transport_profit_loss_integration_flow_with_redacted_token_presence():
    config = KiwoomUsCredentialConfig.from_mapping(
        {
            "KIWOOM_US_APP_KEY": "configured",
            "KIWOOM_US_APP_SECRET": "configured",
            "KIWOOM_US_ACCESS_TOKEN": "configured",
            "KIWOOM_US_READ_ONLY": "true",
            "KIWOOM_US_ENABLE_ORDER": "false",
        },
        source="fixture",
    )
    transport = FakeKiwoomUsTransport(
        responses={
            "ust21630": UsReadOnlyTrResponse(
                tr_id="ust21630",
                return_code="0",
                return_msg="OK",
                data={"rlzt_pl": "10", "pl_rt": "1.2"},
                unknown_fields={"rlzt_pl": "10", "pl_rt": "1.2"},
            )
        }
    )
    client = KiwoomUsRestClientSkeleton(
        access_token_present=bool(config.token),
        live_provider_enabled=True,
        read_only=config.read_only,
        order_enabled=config.order_enabled,
        transport=transport,
    )

    response = client.execute_readonly_tr("ust21630", {"fc_krw_tp": "1"})
    mapped = map_profit_loss_response(response.tr_id, {"return_code": response.return_code, "return_msg": response.return_msg, **response.data})

    assert mapped.realized_profit_loss == "10"
    assert mapped.profit_loss_rate == "1.2"
    assert transport.sent_requests[0].headers["Authorization"] == "Bearer <redacted>"
    assert transport.sent_requests[0].body == {"fc_krw_tp": "1"}


def test_us_fake_transport_condition_search_mapper_flow():
    raw_payload = {
        "seq": "001",
        "name": "US momentum",
        "items": [{"jmcode": "NVDA"}, {"stk_cd": "TSLA"}],
        "extra": "kept",
    }

    mapped = map_condition_search_response(raw_payload)

    assert mapped.condition_id == "001"
    assert mapped.symbols == ["NVDA", "TSLA"]
    assert mapped.unknown_fields["extra"] == "kept"


def test_us_fake_transport_order_policy_blocks_integration_flow():
    with pytest.raises(UsOrderBlockedError):
        KiwoomUsCredentialConfig.from_mapping({"KIWOOM_US_ENABLE_ORDER": "true"})

    client = KiwoomUsRestClientSkeleton(live_provider_enabled=True, transport=FakeKiwoomUsTransport())
    with pytest.raises(UsOrderBlockedError):
        client.execute_readonly_tr("ust20000")


def test_us_fake_transport_live_provider_false_blocks_before_transport_integration_flow():
    transport = FakeKiwoomUsTransport()
    client = KiwoomUsRestClientSkeleton(live_provider_enabled=False, transport=transport)

    with pytest.raises(UsLiveProviderDisabledError):
        client.execute_readonly_tr("ust21110")

    assert transport.sent_requests == []


def test_us_fake_transport_integration_layer_keeps_network_clients_unimported():
    for module_name in ["httpx", "requests", "websockets"]:
        sys.modules.pop(module_name, None)

    client = KiwoomUsRestClientSkeleton(live_provider_enabled=True, transport=FakeKiwoomUsTransport())
    client.execute_readonly_tr("ust21120", {"cmsn_incl_tp": "0", "exrt_tp": "0"})

    assert "httpx" not in sys.modules
    assert "requests" not in sys.modules
    assert "websockets" not in sys.modules
