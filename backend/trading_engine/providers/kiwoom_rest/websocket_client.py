from __future__ import annotations

from typing import Any

from trading_engine.providers.kiwoom_rest.credentials import CredentialProvider, SkeletonCredentialProvider
from trading_engine.providers.kiwoom_rest.safety import KiwoomProviderSafety
from trading_engine.providers.kiwoom_rest.schemas import SubscribeRequest


class KiwoomWebSocketClientSkeleton:
    """WebSocket skeleton for future quote/orderbook/condition subscriptions.

    The official samples use a LOGIN packet followed by REG/REMOVE packets.
    This skeleton only builds subscription packets and blocks connection by
    default. Reconnect/resubscribe will be implemented after official realtime
    protocol review and paper-mode observation rules are documented.
    """

    def __init__(
        self,
        *,
        safety: KiwoomProviderSafety | None = None,
        credentials: CredentialProvider | None = None,
    ) -> None:
        self.safety = safety or KiwoomProviderSafety()
        self.credentials = credentials or SkeletonCredentialProvider()
        self.subscriptions: list[SubscribeRequest] = []

    async def connect(self) -> None:
        self.safety.assert_live_allowed()
        raise RuntimeError("Kiwoom WebSocket transport is not implemented")

    def build_login_packet(self) -> dict[str, str]:
        self.safety.assert_live_allowed()
        return {"trnm": "LOGIN", "token": self.credentials.authorization_header().removeprefix("Bearer ")}

    def subscribe_quotes(self, symbols: list[str]) -> dict[str, Any]:
        request = SubscribeRequest(items=symbols, types=["0B"])
        self.subscriptions.append(request)
        return request.to_reg_packet()

    def subscribe_orderbook(self, symbols: list[str]) -> dict[str, Any]:
        request = SubscribeRequest(items=symbols, types=["0D"])
        self.subscriptions.append(request)
        return request.to_reg_packet()

    def subscribe_condition(self, condition_ids: list[str]) -> dict[str, Any]:
        request = SubscribeRequest(items=condition_ids, types=["0C"])
        self.subscriptions.append(request)
        return request.to_reg_packet()

    def subscribe_order_fills(self, *_: object, **__: object) -> None:
        self.safety.assert_order_blocked()
