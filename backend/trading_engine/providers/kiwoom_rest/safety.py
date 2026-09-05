from __future__ import annotations

from dataclasses import dataclass
from typing import Any


SECRET_FIELD_NAMES = {
    "appkey",
    "app_key",
    "secretkey",
    "secret_key",
    "token",
    "access_token",
    "authorization",
    "account",
    "account_no",
    "acctno",
    "acct_no",
}


@dataclass(frozen=True)
class KiwoomProviderSafety:
    live_provider_enabled: bool = False
    order_enabled: bool = False

    def assert_live_allowed(self) -> None:
        if not self.live_provider_enabled:
            raise RuntimeError("Kiwoom live provider is disabled")

    def assert_order_blocked(self) -> None:
        raise RuntimeError("Kiwoom order execution is disabled in trading engine skeleton")

    def assert_no_order(self, api_id: str) -> None:
        if self.order_enabled:
            raise RuntimeError("Order execution remains unavailable even when order_enabled is true")
        if api_id.startswith("kt100"):
            raise RuntimeError(f"Order TR is blocked: {api_id}")


def mask_secret(value: object) -> str:
    text = str(value) if value is not None else ""
    if not text:
        return ""
    if len(text) <= 4:
        return "****"
    return f"{text[:2]}****{text[-2:]}"


def sanitize_mapping(payload: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in payload.items():
        if key.strip().lower() in SECRET_FIELD_NAMES:
            safe[key] = "<redacted>"
        elif isinstance(value, dict):
            safe[key] = sanitize_mapping(value)
        else:
            safe[key] = value
    return safe
