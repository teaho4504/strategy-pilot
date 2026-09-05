from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace

from scripts import verify_us_account_shapes as audit_module
from scripts.verify_us_account_shapes import build_safe_account_shape_summary
from trading_engine.providers.kiwoom_us.schemas import UsReadOnlyTrResponse


def _response(tr_id: str, data: dict[str, object]) -> UsReadOnlyTrResponse:
    return UsReadOnlyTrResponse(
        tr_id=tr_id,
        return_code="0",
        return_msg="OK",
        data=data,
        unknown_fields=data,
    )


def test_safe_account_summary_exposes_shape_without_values() -> None:
    summary = build_safe_account_shape_summary(
        _response(
            "ust21110",
            {
                "krw_entra": "sensitive-cash",
                "result_list": [
                    {
                        "crnc_code": "USD",
                        "fc_entra": "sensitive-deposit",
                        "fc_ord_alowa": "sensitive-orderable",
                    }
                ],
            },
        )
    )

    text = str(summary)
    assert summary["top_level_contract_present"] is True
    assert summary["row_contract_present"] is True
    assert "sensitive-cash" not in text
    assert "sensitive-deposit" not in text
    assert "sensitive-orderable" not in text


def test_account_audit_calls_only_readonly_account_trs(monkeypatch) -> None:
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
            top_required, _ = audit_module.ACCOUNT_TR_CONTRACTS[tr_id]
            return _response(tr_id, {key: [] if key == "result_list" else "" for key in top_required})

    monkeypatch.setattr(audit_module, "KiwoomSessionManager", FakeSessionManager)
    monkeypatch.setattr(audit_module, "KiwoomUsUrllibHttpSender", FakeSender)
    monkeypatch.setattr(audit_module, "KiwoomUsHttpReadOnlyTransport", FakeTransport)
    monkeypatch.setattr(audit_module, "KiwoomUsRestClientSkeleton", FakeClient)

    summaries = asyncio.run(
        audit_module.run_audit(
            profile="safe-profile",
            today=date(2026, 7, 31),
        )
    )

    assert [tr_id for tr_id, _ in calls] == [
        "ust21110",
        "ust21120",
        "ust21630",
        "ust21650",
        "usa21670",
    ]
    assert all(not tr_id.startswith("ust200") for tr_id, _ in calls)
    assert calls[2][1] == {"stex_tp": "", "stk_cd": "", "fc_krw_tp": "1"}
    assert calls[3][1] == {"fr_dt": "20260724", "to_dt": "20260731"}
    assert calls[4][1] == {"from": "20260724", "to": "20260731"}
    assert "TOKEN-MUST-NOT-LEAK" not in str(summaries)
