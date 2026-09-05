from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field

import pytest

from trading_engine.providers.kiwoom_us.http_sender import (
    KiwoomUsHttpSenderBlockedError,
    KiwoomUsHttpSenderError,
    KiwoomUsUrllibHttpSender,
)
from trading_engine.providers.kiwoom_us.schemas import PreparedUsHttpRequest
from trading_engine.providers.kiwoom_us.smoke_plan import US_READONLY_HTTP_SENDER_CONFIRM


@dataclass
class FakeUrlOpenResponse:
    payload: dict[str, object]
    headers: dict[str, str] = field(default_factory=dict)

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self) -> "FakeUrlOpenResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


@dataclass
class RecordingUrlOpen:
    payload: dict[str, object]
    response_headers: dict[str, str] = field(default_factory=dict)
    requests: list[urllib.request.Request] = field(default_factory=list)
    timeouts: list[float] = field(default_factory=list)

    def __call__(self, request: urllib.request.Request, timeout: float) -> FakeUrlOpenResponse:
        self.requests.append(request)
        self.timeouts.append(timeout)
        return FakeUrlOpenResponse(
            self.payload,
            headers=self.response_headers,
        )


def _prepared_request() -> PreparedUsHttpRequest:
    return PreparedUsHttpRequest(
        url="https://api.kiwoom.com/api/us/acnt",
        method="POST",
        headers={
            "api-id": "ust21110",
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": "Bearer configured",
        },
        body={"qry_tp": "1"},
        timeout_seconds=5.0,
    )


def test_live_http_sender_blocks_when_network_not_enabled():
    opener = RecordingUrlOpen({"return_code": "0", "return_msg": "OK"})
    sender = KiwoomUsUrllibHttpSender(
        network_enabled=False,
        confirm_phrase=US_READONLY_HTTP_SENDER_CONFIRM,
        opener=opener,
    )

    with pytest.raises(KiwoomUsHttpSenderBlockedError):
        sender.send(_prepared_request())

    assert opener.requests == []


def test_live_http_sender_blocks_without_confirm_phrase():
    opener = RecordingUrlOpen({"return_code": "0", "return_msg": "OK"})
    sender = KiwoomUsUrllibHttpSender(network_enabled=True, confirm_phrase=None, opener=opener)

    with pytest.raises(KiwoomUsHttpSenderBlockedError):
        sender.send(_prepared_request())

    assert opener.requests == []


def test_live_http_sender_builds_urllib_request_with_safe_shape():
    opener = RecordingUrlOpen({"return_code": "0", "return_msg": "OK", "field": "value"})
    sender = KiwoomUsUrllibHttpSender(
        network_enabled=True,
        confirm_phrase=US_READONLY_HTTP_SENDER_CONFIRM,
        opener=opener,
    )

    response = sender.send(_prepared_request())

    assert response["return_code"] == "0"
    assert len(opener.requests) == 1
    request = opener.requests[0]
    assert request.full_url == "https://api.kiwoom.com/api/us/acnt"
    assert request.get_method() == "POST"
    assert request.get_header("Api-id") == "ust21110"
    assert request.get_header("Content-type") == "application/json;charset=UTF-8"
    assert request.get_header("Authorization") == "Bearer configured"
    assert json.loads(request.data.decode("utf-8")) == {"qry_tp": "1"}
    assert opener.timeouts == [5.0]


def test_live_http_sender_preserves_safe_continuation_headers():
    opener = RecordingUrlOpen(
        {"return_code": "0", "return_msg": "OK"},
        response_headers={"cont-yn": "Y", "next-key": "next-page"},
    )
    sender = KiwoomUsUrllibHttpSender(
        network_enabled=True,
        confirm_phrase=US_READONLY_HTTP_SENDER_CONFIRM,
        opener=opener,
    )

    response = sender.send(_prepared_request())

    assert response.cont_yn == "Y"
    assert response.next_key == "next-page"
    assert "next-page" not in response


def test_live_http_sender_errors_do_not_include_secret_values():
    def failing_opener(_: urllib.request.Request, __: float) -> FakeUrlOpenResponse:
        raise urllib.error.URLError("network blocked")

    sender = KiwoomUsUrllibHttpSender(
        network_enabled=True,
        confirm_phrase=US_READONLY_HTTP_SENDER_CONFIRM,
        opener=failing_opener,
    )

    with pytest.raises(KiwoomUsHttpSenderError) as exc_info:
        sender.send(_prepared_request())

    message = str(exc_info.value)
    assert "configured" not in message
    assert "Bearer" not in message
    assert "qry_tp" not in message
