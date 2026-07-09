from __future__ import annotations

import asyncio

import pytest

from trading_engine.domain.enums import ConditionEventType
from trading_engine.providers.kiwoom_rest import (
    KiwoomProviderSafety,
    KiwoomRestClientSkeleton,
    KiwoomWebSocketClientSkeleton,
    adapt_condition_payload,
    adapt_quote_payload,
)
from trading_engine.providers.kiwoom_rest.credentials import SkeletonCredentialProvider
from trading_engine.providers.kiwoom_rest.safety import sanitize_mapping


def test_kiwoom_rest_provider_skeleton_imports():
    assert KiwoomProviderSafety().live_provider_enabled is False
    assert KiwoomRestClientSkeleton().token_status().configured is False
    assert KiwoomWebSocketClientSkeleton().subscriptions == []


def test_rest_client_blocks_external_call_when_live_provider_disabled():
    called = False

    def transport(_spec, _headers):
        nonlocal called
        called = True
        return {"return_code": 0}

    client = KiwoomRestClientSkeleton(transport=transport)

    with pytest.raises(RuntimeError, match="live provider is disabled"):
        client.stock_info("005930")

    assert called is False


def test_websocket_connect_blocks_when_live_provider_disabled():
    client = KiwoomWebSocketClientSkeleton()

    with pytest.raises(RuntimeError, match="live provider is disabled"):
        asyncio.run(client.connect())


def test_order_methods_are_blocked():
    rest_client = KiwoomRestClientSkeleton()
    ws_client = KiwoomWebSocketClientSkeleton()

    with pytest.raises(RuntimeError, match="order execution is disabled"):
        rest_client.place_order(symbol="005930", quantity=1)

    with pytest.raises(RuntimeError, match="order execution is disabled"):
        ws_client.subscribe_order_fills()


def test_mock_quote_payload_adapts_to_market_data_event():
    event = adapt_quote_payload(
        {
            "stk_cd": "005930",
            "cur_prc": "+72,000",
            "flu_rt": "+2.25",
            "cntr_qty": "120000",
            "acc_trdvol": "3200000",
            "bid_prc": "71900",
            "ask_prc": "72000",
            "time": "093015",
        }
    )

    assert event.symbol == "005930"
    assert event.last_price == 72000
    assert event.change_rate == 2.25
    assert event.trade_volume == 120000
    assert event.bid == 71900
    assert event.ask == 72000


def test_mock_condition_payload_adapts_to_condition_event():
    event = adapt_condition_payload(
        {
            "cond_id": "001",
            "cond_name": "거래대금 돌파",
            "stk_cd": "005930",
            "stk_nm": "삼성전자",
            "event": "entered",
        }
    )

    assert event.event_type == ConditionEventType.ENTERED
    assert event.condition_id == "001"
    assert event.symbol == "005930"
    assert event.source == "kiwoom"


def test_secret_token_and_account_values_are_sanitized():
    payload = {
        "appkey": "APPKEY-SHOULD-NOT-LEAK",
        "secretkey": "SECRET-SHOULD-NOT-LEAK",
        "token": "TOKEN-SHOULD-NOT-LEAK",
        "account_no": "ACCOUNT-SHOULD-NOT-LEAK",
        "safe": "visible",
    }

    sanitized = sanitize_mapping(payload)

    assert sanitized["safe"] == "visible"
    assert "APPKEY-SHOULD-NOT-LEAK" not in str(sanitized)
    assert "SECRET-SHOULD-NOT-LEAK" not in str(sanitized)
    assert "TOKEN-SHOULD-NOT-LEAK" not in str(sanitized)
    assert "ACCOUNT-SHOULD-NOT-LEAK" not in str(sanitized)


def test_credentials_skeleton_never_returns_authorization_header():
    provider = SkeletonCredentialProvider()

    with pytest.raises(RuntimeError, match="credentials are not loaded"):
        provider.authorization_header()
