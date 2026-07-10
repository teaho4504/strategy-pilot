from __future__ import annotations

from trading_engine.providers.kiwoom_us.tr_codes import US_TR_INVENTORY, UsTrCategory, UsTrSpec, get_us_tr_spec


class UsOrderBlockedError(RuntimeError):
    pass


class UsLiveProviderDisabledError(RuntimeError):
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


def assert_us_live_provider_enabled(live_provider_enabled: bool) -> None:
    if not live_provider_enabled:
        raise UsLiveProviderDisabledError("US Kiwoom live provider is disabled")


def us_readonly_tr_codes() -> set[str]:
    return {tr_id for tr_id, spec in US_TR_INVENTORY.items() if spec.read_only and not spec.order_related}


def us_blocked_order_tr_codes() -> set[str]:
    return {tr_id for tr_id, spec in US_TR_INVENTORY.items() if spec.order_related or spec.category == UsTrCategory.ORDER}
