from __future__ import annotations

import sys

import pytest

from trading_engine.providers.kiwoom_us import KiwoomUsRestClientSkeleton
from trading_engine.providers.kiwoom_us.safety import UsLiveProviderDisabledError, UsOrderBlockedError
from trading_engine.providers.kiwoom_us.schemas import UsReadOnlyTrResponse
from trading_engine.providers.kiwoom_us.transport import FakeKiwoomUsTransport


def test_transport_none_blocks_after_live_provider_gate():
    client = KiwoomUsRestClientSkeleton(access_token_present=True, live_provider_enabled=True)

    with pytest.raises(RuntimeError, match="transport"):
        client.execute_readonly_tr("ust21110")


def test_live_provider_false_blocks_before_fake_transport_call():
    transport = FakeKiwoomUsTransport()
    client = KiwoomUsRestClientSkeleton(
        access_token_present=True,
        live_provider_enabled=False,
        transport=transport,
    )

    with pytest.raises(UsLiveProviderDisabledError):
        client.execute_readonly_tr("ust21110")

    assert transport.sent_requests == []


def test_fake_transport_returns_readonly_response_without_network():
    response = UsReadOnlyTrResponse(
        tr_id="ust21110",
        return_code="0",
        return_msg="OK",
        data={"fixture": True},
        unknown_fields={"fixture": True},
    )
    transport = FakeKiwoomUsTransport(responses={"ust21110": response})
    client = KiwoomUsRestClientSkeleton(
        access_token_present=True,
        live_provider_enabled=True,
        transport=transport,
    )

    result = client.execute_readonly_tr("ust21110")

    assert result is response
    assert len(transport.sent_requests) == 1
    assert transport.sent_requests[0].headers["api-id"] == "ust21110"
    assert transport.sent_requests[0].headers["Authorization"] == "Bearer <redacted>"


def test_transport_path_blocks_order_trs():
    client = KiwoomUsRestClientSkeleton(live_provider_enabled=True, transport=FakeKiwoomUsTransport())

    with pytest.raises(UsOrderBlockedError):
        client.execute_readonly_tr("ust20000")


def test_transport_path_blocks_secret_like_request_body():
    client = KiwoomUsRestClientSkeleton(live_provider_enabled=True, transport=FakeKiwoomUsTransport())

    with pytest.raises(RuntimeError, match="credential-like"):
        client.execute_readonly_tr("ust21110", {"token": "configured"})


def test_us_transport_interface_does_not_import_network_clients():
    for module_name in ["httpx", "requests", "websockets"]:
        sys.modules.pop(module_name, None)

    transport = FakeKiwoomUsTransport()
    client = KiwoomUsRestClientSkeleton(live_provider_enabled=True, transport=transport)
    client.execute_readonly_tr("ust21650", {"fr_dt": "20260701", "to_dt": "20260710"})

    assert "httpx" not in sys.modules
    assert "requests" not in sys.modules
    assert "websockets" not in sys.modules
