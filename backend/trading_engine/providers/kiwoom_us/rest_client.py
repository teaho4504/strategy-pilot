from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from trading_engine.providers.kiwoom_us.request_builder import build_readonly_request
from trading_engine.providers.kiwoom_us.safety import (
    UsLiveProviderDisabledError,
    assert_live_provider_policy,
    assert_no_secret_in_payload,
    assert_us_live_provider_enabled,
    assert_us_order_blocked,
    assert_us_readonly_tr_allowed,
)
from trading_engine.providers.kiwoom_us.schemas import UsReadOnlyTrRequest, UsReadOnlyTrResponse
from trading_engine.providers.kiwoom_us.transport import KiwoomUsReadOnlyTransport


@dataclass(frozen=True)
class KiwoomUsRestClientSkeleton:
    access_token_present: bool = False
    live_provider_enabled: bool = False
    read_only: bool = True
    order_enabled: bool = False
    transport: KiwoomUsReadOnlyTransport | None = None

    def build_readonly_tr_request(
        self,
        tr_id: str,
        body: dict[str, Any] | None = None,
        *,
        cont_yn: str = "N",
        next_key: str = "",
    ) -> UsReadOnlyTrRequest:
        assert_live_provider_policy(
            live_provider_enabled=self.live_provider_enabled,
            read_only=self.read_only,
            order_enabled=self.order_enabled,
        )
        spec = assert_us_readonly_tr_allowed(tr_id)
        request = build_readonly_request(spec.tr_id, body)
        assert_no_secret_in_payload(request.body)
        return UsReadOnlyTrRequest(
            tr_id=request.tr_id,
            endpoint=request.endpoint,
            method=request.method,
            headers=self._readonly_headers(
                request.tr_id,
                cont_yn=cont_yn,
                next_key=next_key,
            ),
            body=request.body,
            read_only=True,
        )

    def execute_readonly_tr(
        self,
        tr_id: str,
        body: dict[str, Any] | None = None,
        *,
        cont_yn: str = "N",
        next_key: str = "",
    ) -> UsReadOnlyTrResponse:
        request = self.build_readonly_tr_request(
            tr_id,
            body,
            cont_yn=cont_yn,
            next_key=next_key,
        )
        assert_us_live_provider_enabled(self.live_provider_enabled)
        if self.transport is None:
            raise RuntimeError("US Kiwoom read-only transport is not configured")
        return self.transport.send_readonly(request)

    def place_order(self, tr_id: str, *_: object, **__: object) -> None:
        assert_us_order_blocked(tr_id)

    def _readonly_headers(
        self,
        tr_id: str,
        *,
        cont_yn: str,
        next_key: str,
    ) -> dict[str, str]:
        headers = {
            "api-id": tr_id,
            "Content-Type": "application/json;charset=UTF-8",
            "cont-yn": "Y" if str(cont_yn).strip().upper() == "Y" else "N",
            "next-key": str(next_key or "").strip(),
        }
        if self.access_token_present:
            headers["Authorization"] = "Bearer <redacted>"
        return headers
