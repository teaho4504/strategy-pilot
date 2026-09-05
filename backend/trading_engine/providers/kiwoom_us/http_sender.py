from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Protocol

import certifi

from trading_engine.providers.kiwoom_us.schemas import PreparedUsHttpRequest
from trading_engine.providers.kiwoom_us.smoke_plan import US_READONLY_HTTP_SENDER_CONFIRM


class KiwoomUsHttpSenderBlockedError(RuntimeError):
    pass


class KiwoomUsHttpSenderError(RuntimeError):
    def __init__(self, *, http_status: int | None = None, error_type: str = "http_sender_error") -> None:
        self.http_status = http_status
        self.error_type = error_type
        super().__init__(f"US Kiwoom HTTP sender failed: error_type={error_type} http_status={http_status}")


class KiwoomUsHttpPayload(dict[str, object]):
    def __init__(
        self,
        body: dict[str, object],
        *,
        cont_yn: str = "N",
        next_key: str = "",
    ) -> None:
        super().__init__(body)
        self.cont_yn = cont_yn
        self.next_key = next_key


class UrlOpenResponse(Protocol):
    def read(self) -> bytes:
        ...

    def __enter__(self) -> "UrlOpenResponse":
        ...

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        ...


UrlOpen = Callable[[urllib.request.Request, float], UrlOpenResponse]


def _default_urlopen(request: urllib.request.Request, timeout: float) -> UrlOpenResponse:
    context = ssl.create_default_context(cafile=certifi.where())
    return urllib.request.urlopen(request, timeout=timeout, context=context)


@dataclass(frozen=True)
class KiwoomUsUrllibHttpSender:
    network_enabled: bool = False
    confirm_phrase: str | None = None
    expected_confirm_phrase: str = US_READONLY_HTTP_SENDER_CONFIRM
    opener: UrlOpen = _default_urlopen

    def send(self, request: PreparedUsHttpRequest) -> KiwoomUsHttpPayload:
        self._assert_enabled()
        wire_request = urllib.request.Request(
            url=request.url,
            data=json.dumps(request.body, ensure_ascii=False).encode("utf-8"),
            headers=request.headers,
            method=request.method,
        )
        try:
            with self.opener(wire_request, request.timeout_seconds) as response:
                payload = response.read().decode("utf-8")
                response_headers = getattr(response, "headers", None)
                cont_yn = _response_header(response_headers, "cont-yn") or "N"
                next_key = _response_header(response_headers, "next-key")
        except urllib.error.HTTPError as exc:
            raise KiwoomUsHttpSenderError(http_status=exc.code, error_type="http_error") from None
        except urllib.error.URLError as exc:
            raise KiwoomUsHttpSenderError(error_type=type(exc).__name__) from None
        except TimeoutError:
            raise KiwoomUsHttpSenderError(error_type="timeout") from None

        if not payload.strip():
            return KiwoomUsHttpPayload(
                {},
                cont_yn=cont_yn,
                next_key=next_key,
            )
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            raise KiwoomUsHttpSenderError(error_type="invalid_json") from None
        if not isinstance(parsed, dict):
            raise KiwoomUsHttpSenderError(error_type="invalid_json_shape")
        return KiwoomUsHttpPayload(
            parsed,
            cont_yn=cont_yn,
            next_key=next_key,
        )

    def _assert_enabled(self) -> None:
        if not self.network_enabled:
            raise KiwoomUsHttpSenderBlockedError("US Kiwoom HTTP sender network use is disabled")
        if self.confirm_phrase != self.expected_confirm_phrase:
            raise KiwoomUsHttpSenderBlockedError("US Kiwoom HTTP sender confirmation phrase is missing")


def _response_header(headers: object, name: str) -> str:
    getter = getattr(headers, "get", None)
    if not callable(getter):
        return ""
    value = getter(name)
    return str(value or "").strip()
