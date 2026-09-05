from __future__ import annotations

import sys
from dataclasses import asdict

import pytest

from trading_engine.providers.kiwoom_us import (
    UsOrderEventMappingError,
    map_us_order_realtime_payload,
)
from trading_engine.providers.kiwoom_us.safety import (
    UsOrderBlockedError,
    assert_us_realtime_channel_allowed,
)


def test_f4_maps_order_state_without_account_data():
    account_marker = "ACCOUNT-MUST-NOT-SURVIVE"
    events = map_us_order_realtime_payload(
        {
            "trnm": "REAL",
            "data": [
                {
                    "type": "F4",
                    "item": "NVDA",
                    "values": {
                        "9201": account_marker,
                        "9203": "000000027",
                        "9001": "NVDA",
                        "905": "10",
                        "907": "02",
                        "904": "000000000",
                        "900": "2",
                        "901": "198.4200",
                        "906": "00",
                        "913": "주문전송",
                        "908": "105247",
                        "8043": "USD",
                        "99999": "unknown-sensitive-value",
                    },
                }
            ],
        }
    )

    assert len(events) == 1
    event = events[0]
    assert event.tr_id == "F4"
    assert event.order_no == "000000027"
    assert event.original_order_no is None
    assert event.symbol == "NVDA"
    assert event.side == "buy"
    assert event.order_quantity == 2
    assert event.order_price == 198.42
    assert event.status == "주문전송"
    assert event.unknown_field_ids == ("99999",)
    assert "9201" not in event.unknown_field_ids
    assert account_marker not in repr(event)
    assert account_marker not in repr(asdict(event))
    assert "unknown-sensitive-value" not in repr(event)


@pytest.mark.parametrize(
    ("status", "unfilled_quantity", "fill_quantity"),
    [
        ("부분체결", "1", "1"),
        ("체결완료", "0", "2"),
    ],
)
def test_f5_maps_partial_and_full_fill_state(status: str, unfilled_quantity: str, fill_quantity: str):
    event = map_us_order_realtime_payload(
        {
            "trnm": "REAL",
            "data": [
                {
                    "type": "F5",
                    "item": "MSFT",
                    "values": {
                        "9201": "FAKE-ACCOUNT",
                        "9203": "000000031",
                        "9001": "MSFT",
                        "904": "000000000",
                        "905": "10",
                        "907": "01",
                        "908": "111500",
                        "913": status,
                        "900": "2",
                        "901": "510.2500",
                        "902": unfilled_quantity,
                        "909": "000000045",
                        "910": "510.2000",
                        "911": fill_quantity,
                        "930": "3",
                        "8043": "USD",
                    },
                }
            ],
        }
    )[0]

    assert event.tr_id == "F5"
    assert event.side == "sell"
    assert event.status == status
    assert event.unfilled_quantity == int(unfilled_quantity)
    assert event.fill_no == "000000045"
    assert event.fill_quantity == int(fill_quantity)
    assert event.fill_price == 510.2
    assert event.holding_quantity == 3


def test_order_event_mapper_rejects_missing_required_order_number():
    with pytest.raises(UsOrderEventMappingError, match="order number"):
        map_us_order_realtime_payload(
            {
                "trnm": "REAL",
                "data": [
                    {
                        "type": "F5",
                        "item": "NVDA",
                        "values": {"9001": "NVDA", "913": "체결완료"},
                    }
                ],
            }
        )


@pytest.mark.parametrize("invalid_quantity", ["1.5", "-1", "not-a-number"])
def test_order_event_mapper_rejects_invalid_quantities(invalid_quantity: str):
    with pytest.raises(UsOrderEventMappingError):
        map_us_order_realtime_payload(
            {
                "trnm": "REAL",
                "data": [
                    {
                        "type": "F5",
                        "item": "NVDA",
                        "values": {
                            "9203": "000000027",
                            "9001": "NVDA",
                            "913": "부분체결",
                            "911": invalid_quantity,
                        },
                    }
                ],
            }
        )


def test_order_event_mapper_ignores_non_order_channels():
    assert (
        map_us_order_realtime_payload(
            {
                "trnm": "REAL",
                "data": [{"type": "FE", "item": "NVDA", "values": {"10": "100"}}],
            }
        )
        == []
    )


def test_f4_f5_registration_remains_blocked():
    for tr_id in ["F4", "F5"]:
        with pytest.raises(UsOrderBlockedError):
            assert_us_realtime_channel_allowed(tr_id)


def test_order_event_mapper_has_no_network_dependency():
    for module_name in ["httpx", "requests", "websockets"]:
        sys.modules.pop(module_name, None)

    map_us_order_realtime_payload({"trnm": "REAL", "data": []})

    assert "httpx" not in sys.modules
    assert "requests" not in sys.modules
    assert "websockets" not in sys.modules
