from __future__ import annotations

import asyncio
from types import SimpleNamespace

from scripts import verify_us_order_state_shapes as audit_module
from scripts.verify_us_order_state_shapes import build_safe_shape_summary
from trading_engine.providers.kiwoom_us.schemas import UsReadOnlyTrResponse


def _response(tr_id: str, data: dict[str, object]) -> UsReadOnlyTrResponse:
    return UsReadOnlyTrResponse(
        tr_id=tr_id,
        return_code="0",
        return_msg="OK",
        data=data,
        unknown_fields=data,
    )


def test_ust21050_safe_summary_exposes_keys_without_values() -> None:
    summary = build_safe_shape_summary(
        _response(
            "ust21050",
            {
                "result_list": [
                    {
                        "ord_no": "sensitive-order-id",
                        "orig_ord_no": "sensitive-original-id",
                        "stk_code": "NVDA",
                        "slby_tp": "2",
                        "ord_qty": "1",
                        "cntr_qty": "0",
                        "cncl_qty": "0",
                        "ord_remnq": "1",
                        "ord_stat": "접수",
                    }
                ]
            },
        )
    )

    text = str(summary)
    assert summary["required_row_fields_present"] is True
    assert "sensitive-order-id" not in text
    assert "sensitive-original-id" not in text
    assert "NVDA" not in text


def test_ust31490_safe_summary_reports_shape_not_amounts() -> None:
    summary = build_safe_shape_summary(
        _response(
            "ust31490",
            {
                "min_ord_alowq": "12",
                "min_ord_alowa": "1234.56",
                "crnc_code": "USD",
            },
        )
    )

    text = str(summary)
    assert summary["required_fields_present"] is True
    assert summary["quantity_is_numeric"] is True
    assert summary["amount_is_numeric"] is True
    assert summary["currency_is_usd"] is True
    assert "1234.56" not in text


def test_ust21510_safe_summary_exposes_fill_shape_without_values() -> None:
    summary = build_safe_shape_summary(
        _response(
            "ust21510",
            {
                "result_list": [
                    {
                        "ord_no": "sensitive-order-id",
                        "stk_cd": "NVDA",
                        "cntr_qty": "1",
                        "cntr_uv": "123.45",
                        "ord_stat": "filled",
                    }
                ]
            },
        )
    )

    text = str(summary)
    assert summary["rows_present"] is True
    assert summary["required_row_fields_present"] is True
    assert "sensitive-order-id" not in text
    assert "NVDA" not in text
    assert "123.45" not in text


def test_ust21070_safe_summary_exposes_holding_shape_without_values() -> None:
    summary = build_safe_shape_summary(
        _response(
            "ust21070",
            {
                "result_list": [
                    {
                        "stk_code": "NVDA",
                        "sell_alowq": "2",
                        "stex_tp": "ND",
                    }
                ]
            },
        )
    )

    text = str(summary)
    assert summary["rows_present"] is True
    assert summary["required_row_fields_present"] is True
    assert "NVDA" not in text
    assert "ND" not in text


def test_order_state_audit_calls_only_readonly_account_trs(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    class FakeSessionManager:
        async def create_session_from_cli_profile(self, profile):
            assert profile == "safe-profile"
            return SimpleNamespace(
                access_token="TOKEN-MUST-NOT-LEAK",
                base_url="https://api.kiwoom.com",
            )

    class FakeSender:
        def __init__(self, **kwargs):
            assert kwargs["network_enabled"] is True

    class FakeTransport:
        def __init__(self, **kwargs):
            assert kwargs["base_url"] == "https://api.kiwoom.com"

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs["read_only"] is True
            assert kwargs["order_enabled"] is False

        def execute_readonly_tr(self, tr_id, body):
            calls.append((tr_id, body))
            return _response(tr_id, {"result_list": []})

    monkeypatch.setattr(
        audit_module,
        "KiwoomSessionManager",
        FakeSessionManager,
    )
    monkeypatch.setattr(
        audit_module,
        "KiwoomUsUrllibHttpSender",
        FakeSender,
    )
    monkeypatch.setattr(
        audit_module,
        "KiwoomUsHttpReadOnlyTransport",
        FakeTransport,
    )
    monkeypatch.setattr(
        audit_module,
        "KiwoomUsRestClientSkeleton",
        FakeClient,
    )

    summaries = asyncio.run(
        audit_module.run_audit(
            profile="safe-profile",
            symbol="NVDA",
            exchange="ND",
            price="1",
        )
    )

    assert [tr_id for tr_id, _ in calls] == [
        "ust21050",
        "ust21510",
        "ust21070",
        "ust31490",
    ]
    assert calls[1][1] == {
        "slby_tp": "0",
        "stex_tp": "ND",
        "stk_cd": "NVDA",
    }
    assert all(not tr_id.startswith("ust200") for tr_id, _ in calls)
    assert [summary["tr_id"] for summary in summaries] == [
        "ust21050",
        "ust21510",
        "ust21070",
        "ust31490",
    ]
    assert "TOKEN-MUST-NOT-LEAK" not in str(summaries)
