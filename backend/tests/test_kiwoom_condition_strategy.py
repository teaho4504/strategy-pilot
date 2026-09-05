from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.schemas.market import UsConditionItem, UsConditionSearchResponse
from app.services.kiwoom_condition_strategy_service import KiwoomConditionStrategyService


def _catalog(*conditions: UsConditionItem) -> UsConditionSearchResponse:
    return UsConditionSearchResponse(
        source="kiwoom-us-condition-list",
        listTrId="usa20280",
        searchTrId="usa20281",
        realtimeTrId="usa20290",
        clearTrId="usa20291",
        updatedAt="2026-08-13T00:00:00+00:00",
        conditions=list(conditions),
        matches=[],
        schemaKeys=[],
    )


def test_kiwoom_condition_strategy_defaults_off_and_builds_direct_entry(tmp_path):
    service = KiwoomConditionStrategyService(tmp_path / "conditions.sqlite3")
    condition = UsConditionItem(seq="007", name="HTS 급등 조건")

    service.sync([condition])

    assert service.is_enabled("007") is False
    assert service.set_enabled("007", True) is True
    assert service.enabled_sequences() == {"007"}
    config = service.runtime_configs([condition])[0]
    assert config["strategy"] == "kiwoom-condition-007"
    assert config["condition_direct_entry"] is True
    assert "live_execution_allowed" not in config
    assert "pullback_entry_pattern" not in config["required_criteria"]


def test_condition_catalog_uses_list_tr_without_realtime_registration(monkeypatch):
    from app.services import us_condition_service as condition_module

    sent_packets: list[dict[str, object]] = []

    async def fake_send(access_token, mode, packet):
        sent_packets.append(packet)
        return {
            "trnm": "CNSRLST",
            "data": [{"seq": "003", "name": "HTS 거래량 조건"}],
        }, ["data", "trnm"]

    monkeypatch.setattr(
        condition_module,
        "get_active_or_latest_kiwoom_session",
        lambda: SimpleNamespace(access_token="server-token", mode="live"),
    )
    monkeypatch.setattr(condition_module, "_send_condition_request", fake_send)

    response = asyncio.run(condition_module.us_condition_service.get_condition_list())
    refreshed = asyncio.run(
        condition_module.us_condition_service.get_condition_list(force_refresh=True)
    )

    assert response.listTrId == "usa20280"
    assert response.selectedSeq is None
    assert response.conditions == [UsConditionItem(seq="003", name="HTS 거래량 조건")]
    assert refreshed.conditions == response.conditions
    assert len(sent_packets) == 2
    assert sent_packets[0]["trnm"] == "GCNSRLST"


def test_strategy_status_lists_only_synced_kiwoom_conditions(monkeypatch, tmp_path):
    from app.services import us_order_service as order_module

    catalog = _catalog(
        UsConditionItem(seq="001", name="HTS 돌파 조건"),
        UsConditionItem(seq="002", name="HTS 거래량 조건"),
    )

    async def fake_catalog():
        return catalog

    monkeypatch.setattr(
        order_module.kiwoom_condition_strategy_service,
        "db_path",
        tmp_path / "condition-status.sqlite3",
    )
    monkeypatch.setattr(order_module.us_condition_service, "get_condition_list", fake_catalog)
    monkeypatch.setattr(
        order_module.us_condition_service,
        "monitor_status",
        lambda seq: {
            "active": False,
            "selectedSeq": seq,
            "selectedName": None,
            "matchCount": 0,
            "error": None,
        },
    )

    response = asyncio.run(order_module.us_order_service.get_auto_trade_strategy_status())

    assert [item.strategy for item in response.strategies] == [
        "kiwoom-condition-001",
        "kiwoom-condition-002",
    ]
    assert all(item.enabled is False for item in response.strategies)
    assert response.source == "kiwoom-us-condition-strategy-status"


def test_strategy_status_keeps_stored_conditions_when_live_catalog_is_temporarily_empty(
    monkeypatch,
    tmp_path,
):
    from app.services import us_order_service as order_module

    db_path = tmp_path / "condition-status-empty-live.sqlite3"
    monkeypatch.setattr(
        order_module.kiwoom_condition_strategy_service,
        "db_path",
        db_path,
    )
    order_module.kiwoom_condition_strategy_service.sync(
        [UsConditionItem(seq="007", name="HTS 저장 조건")]
    )
    order_module.kiwoom_condition_strategy_service.set_enabled("007", True)

    async def empty_catalog():
        return _catalog()

    async def unavailable_monitor(seq):
        raise order_module.UsConditionSearchError("temporary websocket outage")

    monkeypatch.setattr(
        order_module.us_condition_service,
        "get_condition_list",
        empty_catalog,
    )
    monkeypatch.setattr(
        order_module.us_condition_service,
        "get_condition_search",
        unavailable_monitor,
    )
    monkeypatch.setattr(
        order_module.us_condition_service,
        "monitor_status",
        lambda seq: {
            "active": False,
            "selectedSeq": seq,
            "selectedName": None,
            "matchCount": 0,
            "error": "temporary websocket outage",
        },
    )

    response = asyncio.run(order_module.us_order_service.get_auto_trade_strategy_status())

    assert [item.conditionSeq for item in response.strategies] == ["007"]
    assert response.strategies[0].enabled is True
    assert response.strategies[0].conditionConnected is False


def test_kiwoom_condition_buy_uses_default_two_percent_auto_exit_profile():
    from app.services.us_order_service import _auto_exit_profile_for_order

    profile = _auto_exit_profile_for_order({"strategy": "kiwoom-condition-007"})

    assert profile == {"targetProfitPct": 2.0, "stopLossPct": 2.0}
