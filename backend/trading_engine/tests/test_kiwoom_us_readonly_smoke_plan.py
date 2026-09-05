from __future__ import annotations

from datetime import date

import pytest

from trading_engine.providers.kiwoom_us import (
    US_READONLY_HTTP_SENDER_CONFIRM,
    US_READONLY_SMOKE_CONFIRM,
    resolve_us_readonly_smoke_body,
    safe_smoke_result_summary,
    select_us_readonly_smoke_steps,
    validate_us_readonly_http_sender_environment,
    validate_us_readonly_smoke_environment,
    validate_us_readonly_smoke_plan,
)
from trading_engine.providers.kiwoom_us.safety import us_blocked_order_tr_codes


def test_us_readonly_smoke_plan_contains_only_readonly_trs():
    steps = validate_us_readonly_smoke_plan()
    blocked = us_blocked_order_tr_codes()

    assert [step.tr_id for step in steps] == ["ust21110", "ust21120", "ust21630", "ust21650", "usa21670"]
    assert not any(step.tr_id in blocked for step in steps)
    assert all(step.stop_on_error for step in steps)


def test_us_readonly_smoke_plan_resolves_required_bodies():
    steps = {step.tr_id: step for step in validate_us_readonly_smoke_plan()}

    assert resolve_us_readonly_smoke_body(steps["ust21630"]) == {"fc_krw_tp": "1"}
    assert resolve_us_readonly_smoke_body(steps["ust21650"], today=date(2026, 7, 11)) == {
        "fr_dt": "20260704",
        "to_dt": "20260711",
    }
    assert resolve_us_readonly_smoke_body(steps["usa21670"], today=date(2026, 7, 11)) == {
        "from": "20260704",
        "to": "20260711",
    }


def test_us_readonly_smoke_environment_requires_confirmation_and_safe_flags():
    valid_env = {
        "KIWOOM_US_READ_ONLY": "true",
        "KIWOOM_US_ENABLE_ORDER": "false",
        "KIWOOM_US_LIVE_PROVIDER": "true",
        "KIWOOM_US_SMOKE_CONFIRM": US_READONLY_SMOKE_CONFIRM,
    }

    validate_us_readonly_smoke_environment(valid_env)


def test_us_readonly_smoke_step_selection_allows_one_safe_tr_only():
    steps = select_us_readonly_smoke_steps("ust21110")

    assert [step.tr_id for step in steps] == ["ust21110"]


def test_us_readonly_smoke_step_selection_blocks_unknown_or_order_tr():
    with pytest.raises(RuntimeError, match="not allowed"):
        select_us_readonly_smoke_steps("ust20000")

    with pytest.raises(RuntimeError, match="not allowed"):
        select_us_readonly_smoke_steps("unknown")


def test_us_readonly_smoke_environment_blocks_missing_or_order_enabled_values():
    with pytest.raises(RuntimeError, match="KIWOOM_US_SMOKE_CONFIRM"):
        validate_us_readonly_smoke_environment(
            {
                "KIWOOM_US_READ_ONLY": "true",
                "KIWOOM_US_ENABLE_ORDER": "false",
                "KIWOOM_US_LIVE_PROVIDER": "true",
            }
        )

    with pytest.raises(RuntimeError, match="KIWOOM_US_ENABLE_ORDER"):
        validate_us_readonly_smoke_environment(
            {
                "KIWOOM_US_READ_ONLY": "true",
                "KIWOOM_US_ENABLE_ORDER": "true",
                "KIWOOM_US_LIVE_PROVIDER": "true",
                "KIWOOM_US_SMOKE_CONFIRM": US_READONLY_SMOKE_CONFIRM,
            }
        )


def test_us_readonly_http_sender_environment_requires_extra_confirmation():
    base_env = {
        "KIWOOM_US_READ_ONLY": "true",
        "KIWOOM_US_ENABLE_ORDER": "false",
        "KIWOOM_US_LIVE_PROVIDER": "true",
        "KIWOOM_US_SMOKE_CONFIRM": US_READONLY_SMOKE_CONFIRM,
    }

    with pytest.raises(RuntimeError, match="KIWOOM_US_HTTP_SENDER_ENABLED"):
        validate_us_readonly_http_sender_environment(base_env)

    validate_us_readonly_http_sender_environment(
        {
            **base_env,
            "KIWOOM_US_HTTP_SENDER_ENABLED": "true",
            "KIWOOM_US_HTTP_SENDER_CONFIRM": US_READONLY_HTTP_SENDER_CONFIRM,
        }
    )


def test_us_readonly_smoke_summary_exposes_schema_keys_only():
    summary = safe_smoke_result_summary(
        "ust21110",
        "0",
        "OK",
        {
            "krw_entra": "1000",
            "ord_alow_amt": "900",
        },
    )

    assert summary == {
        "tr_id": "ust21110",
        "return_code": "0",
        "return_msg": "OK",
        "schema_keys": ["krw_entra", "ord_alow_amt"],
    }
    assert "1000" not in str(summary)
    assert "900" not in str(summary)
