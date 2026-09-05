from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.schemas.us_order import UsOrderRequest
from app.services import us_order_service as order_module
def test_live_order_sender_is_unreachable_even_after_successful_precheck(monkeypatch) -> None:
    async def successful_precheck(_payload):
        return SimpleNamespace(canSubmit=True, blockedReasons=[])

    monkeypatch.setattr(order_module.us_order_service, "precheck_order", successful_precheck)
    payload = UsOrderRequest(
        side="buy",
        exchange="ND",
        symbol="NVDA",
        quantity=1,
        referencePrice="100",
        tradeType="03",
        confirmText="I_UNDERSTAND_LIVE_US_ORDER",
    )

    with pytest.raises(order_module.UsOrderBlocked, match="LIVE_ORDER_EXECUTION_NOT_IMPLEMENTED"):
        asyncio.run(order_module.us_order_service.place_order(payload))
