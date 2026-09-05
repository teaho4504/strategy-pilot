from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from trading_engine.providers.kiwoom_us.safety import assert_us_readonly_tr_allowed


US_READONLY_SMOKE_CONFIRM = "I_UNDERSTAND_US_READ_ONLY_ONLY"
US_READONLY_HTTP_SENDER_CONFIRM = "I_UNDERSTAND_US_READ_ONLY_HTTP_SENDER"


@dataclass(frozen=True)
class UsReadonlySmokeStep:
    order: int
    tr_id: str
    purpose: str
    safe_output_fields: tuple[str, ...]
    body: tuple[tuple[str, str], ...] = ()
    stop_on_error: bool = True


US_READONLY_SMOKE_STEPS: tuple[UsReadonlySmokeStep, ...] = (
    UsReadonlySmokeStep(1, "ust21110", "US cash/deposit read-only check", ("tr_id", "return_code", "return_msg", "schema_keys")),
    UsReadonlySmokeStep(2, "ust21120", "US currency cash and valuation read-only check", ("tr_id", "return_code", "return_msg", "schema_keys")),
    UsReadonlySmokeStep(3, "ust21630", "US realized PnL read-only check", ("tr_id", "return_code", "return_msg", "schema_keys"), (("fc_krw_tp", "1"),)),
    UsReadonlySmokeStep(4, "ust21650", "US period return read-only check", ("tr_id", "return_code", "return_msg", "schema_keys"), (("date_range", "last_7_days"),)),
    UsReadonlySmokeStep(5, "usa21670", "US daily account return read-only check", ("tr_id", "return_code", "return_msg", "schema_keys"), (("date_range_from_to", "last_7_days"),)),
)


def validate_us_readonly_smoke_plan() -> tuple[UsReadonlySmokeStep, ...]:
    for step in US_READONLY_SMOKE_STEPS:
        assert_us_readonly_tr_allowed(step.tr_id)
        if "raw_response" in step.safe_output_fields:
            raise ValueError(f"unsafe smoke output field for {step.tr_id}")
    return US_READONLY_SMOKE_STEPS


def select_us_readonly_smoke_steps(tr_id: str | None = None) -> tuple[UsReadonlySmokeStep, ...]:
    steps = validate_us_readonly_smoke_plan()
    if tr_id is None:
        return steps
    cleaned = str(tr_id).strip()
    for step in steps:
        if step.tr_id == cleaned:
            return (step,)
    raise RuntimeError(f"US read-only smoke TR is not allowed: {cleaned}")


def resolve_us_readonly_smoke_body(step: UsReadonlySmokeStep, *, today: date | None = None) -> dict[str, str]:
    body = dict(step.body)
    if body.pop("date_range", None) == "last_7_days":
        base = today or date.today()
        body["fr_dt"] = (base - timedelta(days=7)).strftime("%Y%m%d")
        body["to_dt"] = base.strftime("%Y%m%d")
    if body.pop("date_range_from_to", None) == "last_7_days":
        base = today or date.today()
        body["from"] = (base - timedelta(days=7)).strftime("%Y%m%d")
        body["to"] = base.strftime("%Y%m%d")
    return body


def validate_us_readonly_smoke_environment(env: dict[str, str | None]) -> None:
    required = {
        "KIWOOM_US_READ_ONLY": "true",
        "KIWOOM_US_ENABLE_ORDER": "false",
        "KIWOOM_US_LIVE_PROVIDER": "true",
        "KIWOOM_US_SMOKE_CONFIRM": US_READONLY_SMOKE_CONFIRM,
    }
    missing_or_invalid = [key for key, expected in required.items() if str(env.get(key, "")).strip() != expected]
    if missing_or_invalid:
        raise RuntimeError(f"US read-only smoke test blocked by environment: {', '.join(missing_or_invalid)}")


def validate_us_readonly_http_sender_environment(env: dict[str, str | None]) -> None:
    validate_us_readonly_smoke_environment(env)
    required = {
        "KIWOOM_US_HTTP_SENDER_ENABLED": "true",
        "KIWOOM_US_HTTP_SENDER_CONFIRM": US_READONLY_HTTP_SENDER_CONFIRM,
    }
    missing_or_invalid = [key for key, expected in required.items() if str(env.get(key, "")).strip() != expected]
    if missing_or_invalid:
        raise RuntimeError(f"US read-only HTTP sender blocked by environment: {', '.join(missing_or_invalid)}")


def safe_smoke_result_summary(tr_id: str, return_code: str, return_msg: str, payload: dict[str, object]) -> dict[str, object]:
    return {
        "tr_id": tr_id,
        "return_code": return_code,
        "return_msg": return_msg,
        "schema_keys": sorted(payload.keys()),
    }
