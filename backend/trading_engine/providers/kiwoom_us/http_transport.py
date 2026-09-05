from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Protocol

from trading_engine.providers.kiwoom_us.credentials import MissingCredentialError
from trading_engine.providers.kiwoom_us.response_mapper import map_readonly_response
from trading_engine.providers.kiwoom_us.schemas import PreparedUsHttpRequest, UsReadOnlyTrRequest, UsReadOnlyTrResponse
from trading_engine.providers.kiwoom_us.tr_codes import US_REST_BASE_URL


class KiwoomUsTransportError(RuntimeError):
    def __init__(self, tr_id: str, return_code: str, return_msg: str) -> None:
        self.tr_id = tr_id
        self.return_code = return_code
        self.return_msg = return_msg
        super().__init__(f"US Kiwoom read-only TR failed: tr_id={tr_id} return_code={return_code} return_msg={return_msg}")


class UsHttpSender(Protocol):
    def send(self, request: PreparedUsHttpRequest) -> dict[str, object]:
        ...


@dataclass(frozen=True)
class KiwoomUsHttpReadOnlyTransport:
    token_provider: Callable[[], str | None]
    sender: UsHttpSender | None = None
    base_url: str = US_REST_BASE_URL
    timeout_seconds: float = 5.0

    def send_readonly(self, request: UsReadOnlyTrRequest) -> UsReadOnlyTrResponse:
        if self.sender is None:
            raise RuntimeError("US Kiwoom HTTP sender is not configured")
        token = self.token_provider()
        if token is None or not str(token).strip():
            raise MissingCredentialError("missing US Kiwoom access token")
        prepared = self.prepare_request(request, str(token).strip())
        raw = self.sender.send(prepared)
        response = map_readonly_response(request.tr_id, raw)
        response = replace(
            response,
            cont_yn=str(getattr(raw, "cont_yn", "N") or "N"),
            next_key=str(getattr(raw, "next_key", "") or ""),
        )
        if response.return_code != "0":
            raise KiwoomUsTransportError(request.tr_id, response.return_code, response.return_msg)
        return response

    def prepare_request(self, request: UsReadOnlyTrRequest, token: str) -> PreparedUsHttpRequest:
        if not token.strip():
            raise MissingCredentialError("missing US Kiwoom access token")
        return PreparedUsHttpRequest(
            url=self._join_url(request.endpoint),
            method=request.method,
            headers={
                **request.headers,
                "Authorization": f"Bearer {token}",
            },
            body=request.body,
            timeout_seconds=self.timeout_seconds,
        )

    def _join_url(self, endpoint: str) -> str:
        return f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
