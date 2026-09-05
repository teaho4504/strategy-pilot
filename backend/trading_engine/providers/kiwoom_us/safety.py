from __future__ import annotations

from trading_engine.providers.kiwoom_us.tr_codes import US_TR_INVENTORY, UsTrCategory, UsTrSpec, get_us_tr_spec


class UsOrderBlockedError(RuntimeError):
    pass


class UsLiveProviderDisabledError(RuntimeError):
    pass


class UsSecretExposureError(RuntimeError):
    pass


def assert_us_read_only(spec: UsTrSpec) -> None:
    if spec.category == UsTrCategory.ORDER or spec.order_related or not spec.read_only:
        raise UsOrderBlockedError(f"US order-related TR is blocked: {spec.tr_id}")


def assert_us_readonly_tr_allowed(tr_code: str) -> UsTrSpec:
    spec = get_us_tr_spec(tr_code)
    assert_us_read_only(spec)
    return spec


def assert_us_order_tr_blocked(tr_code: str) -> None:
    spec = get_us_tr_spec(tr_code)
    if spec.category == UsTrCategory.ORDER or spec.order_related:
        raise UsOrderBlockedError(f"US order-related TR is blocked: {tr_code}")
    raise ValueError(f"TR is not order-related: {tr_code}")


def assert_us_realtime_channel_allowed(channel: str) -> UsTrSpec:
    spec = get_us_tr_spec(channel)
    assert_us_read_only(spec)
    if spec.category != UsTrCategory.REALTIME:
        raise ValueError(f"TR is not a US realtime channel: {channel}")
    return spec


def assert_us_order_blocked(tr_id: str) -> None:
    raise UsOrderBlockedError(f"US live order execution is blocked: {tr_id}")


def assert_order_disabled(order_enabled: bool) -> None:
    if order_enabled:
        raise UsOrderBlockedError("US order execution must remain disabled")


def assert_live_provider_policy(*, live_provider_enabled: bool, read_only: bool, order_enabled: bool) -> None:
    assert_order_disabled(order_enabled)
    if live_provider_enabled and not read_only:
        raise UsLiveProviderDisabledError("US live provider requires read-only mode")


def assert_us_live_provider_enabled(live_provider_enabled: bool) -> None:
    if not live_provider_enabled:
        raise UsLiveProviderDisabledError("US Kiwoom live provider is disabled")


def us_readonly_tr_codes() -> set[str]:
    return {tr_id for tr_id, spec in US_TR_INVENTORY.items() if spec.read_only and not spec.order_related}


def us_blocked_order_tr_codes() -> set[str]:
    return {tr_id for tr_id, spec in US_TR_INVENTORY.items() if spec.order_related or spec.category == UsTrCategory.ORDER}


def assert_no_secret_in_payload(payload: object) -> None:
    sensitive_keys = {"app_key", "appkey", "secret", "app_secret", "secretkey", "token", "access_token", "account_no", "account"}
    if _contains_secret(payload, sensitive_keys):
        raise UsSecretExposureError("payload contains credential-like fields")


def _contains_secret(value: object, sensitive_keys: set[str]) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key).lower()
            if any(sensitive in key_text for sensitive in sensitive_keys):
                if nested is not None and str(nested).strip() and str(nested).strip() != "<redacted>":
                    return True
            if _contains_secret(nested, sensitive_keys):
                return True
    elif isinstance(value, (list, tuple, set)):
        return any(_contains_secret(item, sensitive_keys) for item in value)
    return False
