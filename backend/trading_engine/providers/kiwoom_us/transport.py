from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from trading_engine.providers.kiwoom_us.schemas import UsReadOnlyTrRequest, UsReadOnlyTrResponse


class KiwoomUsReadOnlyTransport(Protocol):
    def send_readonly(self, request: UsReadOnlyTrRequest) -> UsReadOnlyTrResponse:
        ...


@dataclass
class FakeKiwoomUsTransport:
    responses: dict[str, UsReadOnlyTrResponse] = field(default_factory=dict)
    sent_requests: list[UsReadOnlyTrRequest] = field(default_factory=list)

    def send_readonly(self, request: UsReadOnlyTrRequest) -> UsReadOnlyTrResponse:
        self.sent_requests.append(request)
        return self.responses.get(
            request.tr_id,
            UsReadOnlyTrResponse(
                tr_id=request.tr_id,
                return_code="0",
                return_msg="OK",
                data={"fake": True},
                unknown_fields={"fake": True},
            ),
        )
