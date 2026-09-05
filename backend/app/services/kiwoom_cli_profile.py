from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

import keyring
from keyring.errors import KeyringError, NoKeyringError
from platformdirs import user_config_dir


KiwoomCliMode = Literal["real"]


class KiwoomCliProfileError(RuntimeError):
    pass


@dataclass(frozen=True)
class KiwoomCliCredential:
    profile: str
    mode: KiwoomCliMode
    app_key: str
    secret_key: str


def load_kiwoom_cli_credential(profile: Optional[str] = None) -> KiwoomCliCredential:
    selected_profile = _resolve_profile(profile)
    mode = _profile_mode(selected_profile)
    service_name = _profile_service_name(selected_profile)
    try:
        app_key = keyring.get_password(service_name, "appkey")
        secret_key = keyring.get_password(service_name, "secretkey")
    except (NoKeyringError, KeyringError) as exc:
        raise KiwoomCliProfileError("kiwoomcli keyring credentials are not available") from exc

    if not app_key or not secret_key:
        raise KiwoomCliProfileError("kiwoomcli profile credentials are missing")

    return KiwoomCliCredential(
        profile=selected_profile,
        mode=mode,
        app_key=app_key,
        secret_key=secret_key,
    )


def safe_kiwoom_cli_profiles() -> list[dict[str, object]]:
    payload = _settings_payload()
    current = payload.get("current_profile")
    profiles = payload.get("profiles", {})
    if not isinstance(profiles, dict):
        return []
    result: list[dict[str, object]] = []
    for alias, raw in profiles.items():
        if not isinstance(alias, str) or not isinstance(raw, dict):
            continue
        mode = raw.get("mode")
        if mode != "real":
            continue
        result.append({
            "profile": alias,
            "mode": mode,
            "current": alias == current,
            "accountLabel": _safe_account_label(alias, raw),
        })
    return result


def safe_kiwoom_cli_account_label(profile: str) -> str:
    profiles = _settings_payload().get("profiles", {})
    raw = profiles.get(profile) if isinstance(profiles, dict) else None
    if not isinstance(raw, dict):
        return _mask_account(profile) or "configured"
    label = _safe_account_label(profile, raw)
    return "configured" if label == "계좌번호 미등록" else label


def _safe_account_label(alias: str, raw: dict[str, object]) -> str:
    configured_label = _local_account_labels().get(alias)
    if configured_label:
        return configured_label
    for key in ("account", "account_no", "accountNo", "acct_no", "acctNo", "계좌번호"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return _mask_account(value)
    return _mask_account(alias) or "계좌번호 미등록"


def _local_account_labels() -> dict[str, str]:
    path = Path.home() / ".strategy-pilot" / "kiwoom_profile_labels.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    result: dict[str, str] = {}
    for profile, label in payload.items():
        if isinstance(profile, str) and isinstance(label, str) and label.strip():
            result[profile] = label.strip()
    return result


def _mask_account(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) >= 4:
        return f"****-{digits[-4:]}"
    return ""


def _resolve_profile(profile: Optional[str]) -> str:
    if profile and profile.strip():
        return _validate_profile_alias(profile)
    payload = _settings_payload()
    current = payload.get("current_profile")
    if isinstance(current, str) and current.strip():
        return _validate_profile_alias(current)
    raise KiwoomCliProfileError("kiwoomcli current profile is not configured")


def _profile_mode(profile: str) -> KiwoomCliMode:
    profiles = _settings_payload().get("profiles", {})
    if not isinstance(profiles, dict):
        raise KiwoomCliProfileError("kiwoomcli profiles are not configured")
    raw = profiles.get(profile)
    if not isinstance(raw, dict):
        raise KiwoomCliProfileError("kiwoomcli profile was not found")
    mode = raw.get("mode")
    if mode != "real":
        raise KiwoomCliProfileError("Only real kiwoomcli profiles are supported")
    return "real"


def _profile_service_name(profile: str) -> str:
    digest = hashlib.sha256(profile.encode("utf-8")).hexdigest()[:16]
    return f"kiwoom-profile-{digest}"


def _settings_payload() -> dict:
    path = _settings_path()
    if not path.exists():
        raise KiwoomCliProfileError("kiwoomcli settings file was not found")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KiwoomCliProfileError("kiwoomcli settings file is not readable") from exc
    if not isinstance(payload, dict):
        raise KiwoomCliProfileError("kiwoomcli settings file is invalid")
    return payload


def _settings_path() -> Path:
    # Keep this identical to Kiwoom's official kwcli implementation.  On
    # Windows platformdirs resolves into the current user's AppData tree; on
    # macOS it resolves into Library/Application Support.  Credentials remain
    # in the OS keyring (Windows Credential Manager / macOS Keychain).
    return Path(user_config_dir("kiwoom")) / "settings.json"


def _validate_profile_alias(alias: str) -> str:
    normalized = alias.strip()
    if not normalized or "/" in normalized or "\\" in normalized or ":" in normalized:
        raise KiwoomCliProfileError("kiwoomcli profile alias is invalid")
    return normalized
