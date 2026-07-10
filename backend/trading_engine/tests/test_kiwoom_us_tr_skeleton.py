from __future__ import annotations

import pytest

from trading_engine.domain.enums import ConditionEventType
from trading_engine.providers.kiwoom_us import (
    US_TR_INVENTORY,
    UsTrCategory,
    adapt_us_condition_payload,
    adapt_us_quote_payload,
    build_condition_clear_request,
    build_condition_list_request,
    build_condition_search_request,
    build_readonly_request,
    build_realtime_registration,
    build_us_order_request_blocked,
)
from trading_engine.providers.kiwoom_us.safety import UsOrderBlockedError
from trading_engine.providers.kiwoom_us.schemas import UsRealtimeSymbol


def test_google_sheet_priority_us_tr_inventory_is_present():
    expected = {
        "usa20280",
        "usa20281",
        "usa20290",
        "usa20291",
        "FE",
        "FT",
        "F4",
        "ust21110",
        "ust21120",
        "ust21150",
        "ust21510",
        "ust21630",
        "ust21650",
        "ust20000",
        "ust20001",
        "ust20002",
        "ust20003",
    }

    assert expected.issubset(US_TR_INVENTORY)


def test_us_readonly_account_request_builders():
    cash = build_readonly_request("ust21110")
    valuation = build_readonly_request("ust21120", {"cmsn_incl_tp": "0", "exrt_tp": "0"})
    daily_fills = build_readonly_request("ust21150", {"query_tp": "1", "slby_tp": "0"})

    assert cash.endpoint == "/api/us/acnt"
    assert cash.body == {}
    assert valuation.body["cmsn_incl_tp"] == "0"
    assert daily_fills.body["query_tp"] == "1"
    assert cash.read_only is True


def test_us_condition_websocket_request_builders():
    listing = build_condition_list_request()
    normal = build_condition_search_request("001")
    realtime = build_condition_search_request("001", realtime=True)
    clear = build_condition_clear_request("001")

    assert listing.tr_id == "usa20280"
    assert listing.body == {"trnm": "GCNSRLST"}
    assert normal.body["search_type"] == "0"
    assert realtime.tr_id == "usa20290"
    assert realtime.body["search_type"] == "1"
    assert clear.body == {"trnm": "GCNSRCLR", "seq": "001"}


def test_us_realtime_registration_for_fe_and_ft():
    symbols = [UsRealtimeSymbol("NVDA", "ND")]
    quote_packet = build_realtime_registration("FE", symbols).to_packet()
    orderbook_packet = build_realtime_registration("FT", symbols).to_packet()

    assert quote_packet["trnm"] == "REG"
    assert quote_packet["data"][0]["item"] == [{"jmcode": "NVDA", "stex_tp": "ND"}]
    assert quote_packet["data"][0]["type"] == ["FE"]
    assert orderbook_packet["data"][0]["type"] == ["FT"]


def test_order_and_order_related_trs_are_blocked():
    for tr_id in ["ust20000", "ust20001", "ust20002", "ust20003", "F4"]:
        spec = US_TR_INVENTORY[tr_id]
        assert spec.order_related is True
        with pytest.raises(UsOrderBlockedError):
            if spec.category == UsTrCategory.ORDER:
                build_us_order_request_blocked(tr_id)
            else:
                build_realtime_registration(tr_id, [UsRealtimeSymbol("NVDA", "ND")])


def test_us_quote_payload_adapts_to_market_data_event():
    event = adapt_us_quote_payload(
        {
            "jmcode": "NVDA",
            "values": {
                "10": "+198.4200",
                "12": "+1.81",
                "13": "166476665",
                "15": "+15",
                "27": "198.4100",
                "28": "198.4300",
            },
        }
    )

    assert event.symbol == "NVDA"
    assert event.last_price == 198
    assert event.change_rate == 1.81
    assert event.cumulative_volume == 166476665


def test_us_condition_payload_adapts_to_condition_event():
    event = adapt_us_condition_payload(
        {
            "seq": "001",
            "name": "US momentum",
            "jmcode": "NVDA",
            "symbol_name": "NVIDIA",
            "event": "entered",
        }
    )

    assert event.event_type == ConditionEventType.ENTERED
    assert event.condition_id == "001"
    assert event.symbol == "NVDA"
    assert event.source == "kiwoom_us"


def test_no_us_request_builder_performs_network_calls():
    request = build_readonly_request("ust21650", {"fr_dt": "20260701", "to_dt": "20260710"})

    assert request.tr_id == "ust21650"
    assert request.endpoint == "/api/us/acnt"
    assert request.method == "POST"
