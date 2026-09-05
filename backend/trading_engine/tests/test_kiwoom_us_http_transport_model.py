from __future__ import annotations

import sys
from dataclasses import dataclass, field

import pytest

from trading_engine.providers.kiwoom_us import KiwoomUsHttpReadOnlyTransport, KiwoomUsRestClientSkeleton, KiwoomUsTransportError
from trading_engine.providers.kiwoom_us.credentials import MissingCredentialError
from trading_engine.providers.kiwoom_us.schemas import PreparedUsHttpRequest


@dataclass
class RecordingSender:
    response: dict[str, object]
    sent: list[PreparedUsHttpRequest] = field(default_factory=list)

    def send(self, request: PreparedUsHttpRequest) -> dict[str, object]:
        self.sent.append(request)
        return self.response


def test_us_http_transport_blocks_without_sender():
    transport = KiwoomUsHttpReadOnlyTransport(token_provider=lambda: "configured")
    client = KiwoomUsRestClientSkeleton(live_provider_enabled=True, transport=transport)

    with pytest.raises(RuntimeError, match="sender"):
        client.execute_readonly_tr("ust21110")


def test_us_http_transport_blocks_without_token():
    sender = RecordingSender({"return_code": "0", "return_msg": "OK"})
    transport = KiwoomUsHttpReadOnlyTransport(token_provider=lambda: None, sender=sender)
    client = KiwoomUsRestClientSkeleton(live_provider_enabled=True, transport=transport)

    with pytest.raises(MissingCredentialError):
        client.execute_readonly_tr("ust21110")

    assert sender.sent == []


def test_us_http_transport_prepares_wire_request_and_maps_response():
    sender = RecordingSender({"return_code": "0", "return_msg": "OK", "krw_entra": "1000"})
    transport = KiwoomUsHttpReadOnlyTransport(token_provider=lambda: "configured", sender=sender)
    client = KiwoomUsRestClientSkeleton(live_provider_enabled=True, transport=transport)

    response = client.execute_readonly_tr("ust21110")

    assert response.return_code == "0"
    assert response.data["krw_entra"] == "1000"
    assert len(sender.sent) == 1
    request = sender.sent[0]
    assert request.url == "https://api.kiwoom.com/api/us/acnt"
    assert request.method == "POST"
    assert request.headers["api-id"] == "ust21110"
    assert request.headers["Content-Type"] == "application/json;charset=UTF-8"
    assert request.headers["Authorization"] == "Bearer configured"
    assert request.headers["cont-yn"] == "N"
    assert request.headers["next-key"] == ""
    assert request.timeout_seconds == 5.0


def test_us_http_transport_forwards_continuation_request_headers():
    sender = RecordingSender(
        {"return_code": "0", "return_msg": "OK", "result_list": []}
    )
    transport = KiwoomUsHttpReadOnlyTransport(
        token_provider=lambda: "configured",
        sender=sender,
    )
    client = KiwoomUsRestClientSkeleton(
        live_provider_enabled=True,
        transport=transport,
    )

    client.execute_readonly_tr(
        "ust21510",
        {"stk_code": "NVDA"},
        cont_yn="Y",
        next_key="next-page",
    )

    assert sender.sent[0].headers["cont-yn"] == "Y"
    assert sender.sent[0].headers["next-key"] == "next-page"


def test_us_http_transport_handles_nonzero_return_code_safely():
    sender = RecordingSender({"return_code": "7", "return_msg": "denied"})
    transport = KiwoomUsHttpReadOnlyTransport(token_provider=lambda: "configured", sender=sender)
    client = KiwoomUsRestClientSkeleton(live_provider_enabled=True, transport=transport)

    with pytest.raises(KiwoomUsTransportError) as exc_info:
        client.execute_readonly_tr("ust21110")

    assert exc_info.value.tr_id == "ust21110"
    assert exc_info.value.return_code == "7"
    assert exc_info.value.return_msg == "denied"
    assert "configured" not in str(exc_info.value)


def test_us_http_transport_does_not_import_network_clients():
    for module_name in ["httpx", "requests", "websockets"]:
        sys.modules.pop(module_name, None)

    sender = RecordingSender({"return_code": "0", "return_msg": "OK"})
    transport = KiwoomUsHttpReadOnlyTransport(token_provider=lambda: "configured", sender=sender)
    client = KiwoomUsRestClientSkeleton(live_provider_enabled=True, transport=transport)
    client.execute_readonly_tr("ust21650")

    assert "httpx" not in sys.modules
    assert "requests" not in sys.modules
    assert "websockets" not in sys.modules
