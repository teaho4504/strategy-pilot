from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
from typing import Mapping

from platformdirs import user_cache_dir, user_config_dir

from trading_engine.providers.kiwoom_us.safety import UsOrderBlockedError, assert_order_disabled


class MissingCredentialError(RuntimeError):
    pass


class KiwoomCliProfileError(MissingCredentialError):
    pass


KEYRING_READ_TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class KiwoomUsCredentialConfig:
    app_key: str | None = None
    app_secret: str | None = None
    account_no: str | None = None
    token: str | None = None
    source: str = "unset"
    read_only: bool = True
    order_enabled: bool = False

    @classmethod
    def from_mapping(cls, values: Mapping[str, str | None], *, source: str = "mapping") -> "KiwoomUsCredentialConfig":
        config = cls(
            app_key=_blank_to_none(values.get("KIWOOM_US_APP_KEY") or values.get("KIWOOM_APP_KEY")),
            app_secret=_blank_to_none(values.get("KIWOOM_US_APP_SECRET") or values.get("KIWOOM_SECRET_KEY")),
            account_no=_blank_to_none(values.get("KIWOOM_US_ACCOUNT_NO") or values.get("KIWOOM_ACCOUNT_NO")),
            token=_blank_to_none(values.get("KIWOOM_US_ACCESS_TOKEN")),
            source=source,
            read_only=_env_bool(values.get("KIWOOM_US_READ_ONLY"), default=True),
            order_enabled=_env_bool(values.get("KIWOOM_US_ENABLE_ORDER"), default=False),
        )
        config.validate_policy()
        return config

    @classmethod
    def from_env(cls) -> "KiwoomUsCredentialConfig":
        return cls.from_mapping(os.environ, source="env")

    @classmethod
    def from_keyring(cls, profile: str | None = None, mode: str | None = None) -> "KiwoomUsCredentialConfig":
        return cls.from_kiwoomcli_profile(profile=profile, mode=mode)

    @classmethod
    def from_kiwoomcli_profile(
        cls,
        profile: str | None = None,
        mode: str | None = None,
        *,
        values: Mapping[str, str | None] | None = None,
        config_dir: Path | None = None,
        cache_dir: Path | None = None,
        keyring_getter=None,
    ) -> "KiwoomUsCredentialConfig":
        env = values or os.environ
        selected = _resolve_kiwoomcli_profile(
            profile=profile or _blank_to_none(env.get("KIWOOM_US_PROFILE")) or _blank_to_none(env.get("KIWOOM_PROFILE")),
            mode=mode or _blank_to_none(env.get("KIWOOM_US_MODE")) or _blank_to_none(env.get("KIWOOM_MODE")),
            config_dir=config_dir,
        )
        token = _read_profile_token(selected.mode, selected.alias, cache_dir=cache_dir)
        try:
            app_key, app_secret = _read_profile_keyring(selected.alias, keyring_getter=keyring_getter)
        except KiwoomCliProfileError:
            if not token:
                raise
            app_key, app_secret = None, None
        config = cls(
            app_key=app_key,
            app_secret=app_secret,
            account_no=_blank_to_none(env.get("KIWOOM_US_ACCOUNT_NO") or env.get("KIWOOM_ACCOUNT_NO")),
            token=token,
            source=f"kiwoomcli-profile:{selected.alias}",
            read_only=_env_bool(env.get("KIWOOM_US_READ_ONLY"), default=True),
            order_enabled=_env_bool(env.get("KIWOOM_US_ENABLE_ORDER"), default=False),
        )
        config.validate_policy()
        return config

    def validate_policy(self) -> None:
        assert_order_disabled(self.order_enabled)
        if not self.read_only:
            raise UsOrderBlockedError("US Kiwoom credentials must be read-only in this phase")

    def require_app_credentials(self) -> None:
        missing = []
        if not self.app_key:
            missing.append("app_key")
        if not self.app_secret:
            missing.append("app_secret")
        if missing:
            raise MissingCredentialError(f"missing US Kiwoom credential fields: {', '.join(missing)}")

    def require_account(self) -> None:
        if not self.account_no:
            raise MissingCredentialError("missing US Kiwoom credential field: account_no")

    def require_token(self) -> None:
        if not self.token:
            raise MissingCredentialError("missing US Kiwoom credential field: token")

    def redacted_summary(self) -> dict[str, object]:
        return {
            "source": self.source,
            "readOnly": self.read_only,
            "orderEnabled": self.order_enabled,
            "appKeyConfigured": bool(self.app_key),
            "appSecretConfigured": bool(self.app_secret),
            "accountConfigured": bool(self.account_no),
            "tokenConfigured": bool(self.token),
        }


def _env_bool(value: str | None, *, default: bool) -> bool:
    if value is None or not str(value).strip():
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


@dataclass(frozen=True)
class _KiwoomCliProfile:
    alias: str
    mode: str


def _resolve_kiwoomcli_profile(*, profile: str | None, mode: str | None, config_dir: Path | None) -> _KiwoomCliProfile:
    payload = _load_kiwoomcli_settings(config_dir)
    profiles = payload.get("profiles", {})
    if not isinstance(profiles, dict):
        raise KiwoomCliProfileError("kiwoomcli settings profiles must be an object")
    selected_alias = _validate_profile_alias(profile) if profile else _blank_to_none(payload.get("current_profile"))
    if not selected_alias:
        raise KiwoomCliProfileError("missing kiwoomcli profile alias")
    raw_profile = profiles.get(selected_alias)
    if not isinstance(raw_profile, dict):
        raise KiwoomCliProfileError("kiwoomcli profile not found")
    selected_mode = _normalize_mode(str(raw_profile.get("mode", "")).strip())
    requested_mode = _normalize_mode(mode) if mode else None
    if requested_mode and requested_mode != selected_mode:
        raise KiwoomCliProfileError("requested mode does not match kiwoomcli profile mode")
    return _KiwoomCliProfile(alias=selected_alias, mode=selected_mode)


def _load_kiwoomcli_settings(config_dir: Path | None) -> dict[str, object]:
    path = (config_dir or _default_kiwoom_config_dir()) / "settings.json"
    if not path.exists():
        raise KiwoomCliProfileError("kiwoomcli settings file not found")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KiwoomCliProfileError("kiwoomcli settings file cannot be read") from exc
    if not isinstance(payload, dict):
        raise KiwoomCliProfileError("kiwoomcli settings file must contain an object")
    return payload


def _read_profile_keyring(alias: str, *, keyring_getter=None) -> tuple[str, str]:
    getter = keyring_getter or _default_keyring_getter()
    service_name = _profile_keyring_service_name(alias)
    app_key = _blank_to_none(getter(service_name, "appkey"))
    app_secret = _blank_to_none(getter(service_name, "secretkey"))
    if not app_key or not app_secret:
        raise KiwoomCliProfileError("kiwoomcli profile credentials are missing")
    return app_key, app_secret


def _read_profile_token(mode: str, alias: str, *, cache_dir: Path | None) -> str | None:
    path = _profile_token_path(mode, alias, cache_dir=cache_dir)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KiwoomCliProfileError("kiwoomcli token cache cannot be read") from exc
    if not isinstance(payload, dict):
        raise KiwoomCliProfileError("kiwoomcli token cache must contain an object")
    if payload.get("mode") != mode:
        raise KiwoomCliProfileError("kiwoomcli token mode mismatch")
    token_profile = payload.get("profile")
    if token_profile is not None and token_profile != alias:
        raise KiwoomCliProfileError("kiwoomcli token profile mismatch")
    expires_at = _parse_datetime(_blank_to_none(payload.get("expires_at")))
    if expires_at and expires_at <= datetime.now(timezone.utc):
        return None
    return _blank_to_none(payload.get("access_token"))


def _profile_token_path(mode: str, alias: str, *, cache_dir: Path | None) -> Path:
    digest = hashlib.sha256(alias.encode("utf-8")).hexdigest()[:16]
    return (cache_dir or _default_kiwoom_cache_dir()) / "profiles" / f"profile-{digest}-token.json"


def _profile_keyring_service_name(alias: str) -> str:
    digest = hashlib.sha256(alias.encode("utf-8")).hexdigest()[:16]
    return f"kiwoom-profile-{digest}"


def _default_keyring_getter():
    try:
        import keyring  # type: ignore
    except ImportError as exc:
        if sys.platform == "darwin":
            return _macos_security_get_password
        raise KiwoomCliProfileError("keyring package is not installed in this Python environment") from exc
    return keyring.get_password


def _macos_security_get_password(service_name: str, username: str) -> str | None:
    try:
        result = subprocess.run(
            ["/usr/bin/security", "find-generic-password", "-s", service_name, "-a", username, "-w"],
            check=False,
            capture_output=True,
            text=True,
            timeout=KEYRING_READ_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise KiwoomCliProfileError("kiwoomcli token expiry has invalid format") from exc
    if parsed.tzinfo is None:
        raise KiwoomCliProfileError("kiwoomcli token expiry must include timezone")
    return parsed.astimezone(timezone.utc)


def _normalize_mode(value: str | None) -> str:
    cleaned = str(value or "").strip().lower()
    if cleaned in {"real", "live", "prd", "production"}:
        return "real"
    if cleaned in {"demo", "mock", "paper"}:
        return "demo"
    raise KiwoomCliProfileError("unsupported kiwoomcli mode")


def _validate_profile_alias(alias: str | None) -> str:
    normalized = str(alias or "").strip()
    if not normalized:
        raise KiwoomCliProfileError("missing kiwoomcli profile alias")
    if len(normalized) > 64:
        raise KiwoomCliProfileError("kiwoomcli profile alias is too long")
    if normalized in {".", ".."} or any(character in normalized for character in {"/", "\\", ":"}):
        raise KiwoomCliProfileError("kiwoomcli profile alias contains unsupported characters")
    if any(ord(character) < 32 for character in normalized):
        raise KiwoomCliProfileError("kiwoomcli profile alias contains control characters")
    if not any(character.isalnum() for character in normalized):
        raise KiwoomCliProfileError("kiwoomcli profile alias must contain a letter or digit")
    invalid = [
        character
        for character in normalized
        if not character.isalnum() and character not in {" ", ".", "_", "-"}
    ]
    if invalid:
        raise KiwoomCliProfileError("kiwoomcli profile alias contains unsupported characters")
    return normalized


def _default_kiwoom_config_dir() -> Path:
    # Match kwcli's platform_paths.config_dir() exactly on every OS.
    return Path(user_config_dir("kiwoom"))


def _default_kiwoom_cache_dir() -> Path:
    # Match kwcli's platform_paths.cache_dir() so profile token lookup uses
    # the same location as the CLI and the dashboard session loader.
    return Path(user_cache_dir("kiwoom"))
