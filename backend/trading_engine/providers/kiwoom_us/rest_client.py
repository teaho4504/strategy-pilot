from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from trading_engine.providers.kiwoom_us.request_builder import build_readonly_request
from trading_engine.providers.kiwoom_us.safety import (
    UsLiveProviderDisabledError,
    assert_us_live_provider_enabled,
    assert_us_order_blocked,
    assert_us_readonly_tr_allowed,
)
from trading_engine.providers.kiwoom_us.schemas import UsReadOnlyTrRequest


@dataclass(frozen=True)
class KiwoomUsRestClientSkeleton:
    access_token_present: bool = False
    live_provider_enabled: bool = False

    def build_readonly_tr_request(self, tr_id: str, body: dict[str, Any] | None = None) -> UsReadOnlyTrRequest:
        spec = assert_us_readonly_tr_allowed(tr_id)
        request = build_readonly_request(spec.tr_id, body)
        return UsReadOnlyTrRequest(
            tr_id=request.tr_id,
            endpoint=request.endpoint,
            method=request.method,
            headers=self._readonly_headers(request.tr_id),
            body=request.body,
            read_only=True,
        )

    def execute_readonly_tr(self, tr_id: str, body: dict[str, Any] | None = None) -> None:
        self.build_readonly_tr_request(tr_id, body)
        assert_us_live_provider_enabled(self.live_provider_enabled)
        raise UsLiveProviderDisabledError("US REST skeleton has no HTTP transport")

    def place_order(self, tr_id: str, *_: object, **__: object) -> None:
        assert_us_order_blocked(tr_id)

    def _readonly_headers(self, tr_id: str) -> dict[str, str]:
        headers = {
            "api-id": tr_id,
            "Content-Type": "application/json;charset=UTF-8",
        }
        if self.access_token_present:
            headers["Authorization"] = "Bearer <redacted>"
        return headers
