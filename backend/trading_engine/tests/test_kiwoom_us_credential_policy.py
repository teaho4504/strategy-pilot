from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest

from trading_engine.providers.kiwoom_us import credentials as credential_module
from trading_engine.providers.kiwoom_us.credentials import KiwoomUsCredentialConfig, MissingCredentialError
from trading_engine.providers.kiwoom_us.safety import UsOrderBlockedError, UsSecretExposureError, assert_no_secret_in_payload


def test_default_kiwoom_paths_match_official_platformdirs(monkeypatch, tmp_path):
    config_path = tmp_path / "official-config"
    cache_path = tmp_path / "official-cache"
    monkeypatch.setattr(credential_module, "user_config_dir", lambda app_name: str(config_path))
    monkeypatch.setattr(credential_module, "user_cache_dir", lambda app_name: str(cache_path))

    assert credential_module._default_kiwoom_config_dir() == config_path
    assert credential_module._default_kiwoom_cache_dir() == cache_path


def test_us_credential_config_defaults_are_readonly_and_order_disabled():
    config = KiwoomUsCredentialConfig()

    assert config.read_only is True
    assert config.order_enabled is False
    assert config.source == "unset"


def test_us_credential_mapping_normalizes_policy_flags():
    config = KiwoomUsCredentialConfig.from_mapping(
        {
            "KIWOOM_US_APP_KEY": "configured",
            "KIWOOM_US_APP_SECRET": "configured",
            "KIWOOM_US_ACCOUNT_NO": "configured",
            "KIWOOM_US_READ_ONLY": "true",
            "KIWOOM_US_ENABLE_ORDER": "false",
        },
        source="test",
    )

    assert config.redacted_summary() == {
        "source": "test",
        "readOnly": True,
        "orderEnabled": False,
        "appKeyConfigured": True,
        "appSecretConfigured": True,
        "accountConfigured": True,
        "tokenConfigured": False,
    }


def test_us_credential_order_enabled_is_blocked():
    with pytest.raises(UsOrderBlockedError):
        KiwoomUsCredentialConfig.from_mapping({"KIWOOM_US_ENABLE_ORDER": "true"})


def test_us_credential_non_readonly_mode_is_blocked():
    with pytest.raises(UsOrderBlockedError):
        KiwoomUsCredentialConfig.from_mapping({"KIWOOM_US_READ_ONLY": "false"})


def test_us_credential_missing_fields_raise_clear_errors():
    config = KiwoomUsCredentialConfig()

    with pytest.raises(MissingCredentialError, match="app_key"):
        config.require_app_credentials()

    with pytest.raises(MissingCredentialError, match="account_no"):
        config.require_account()


def test_us_kiwoomcli_profile_loader_reads_keyring_and_token_cache(tmp_path):
    config_dir = tmp_path / "config"
    cache_dir = tmp_path / "cache"
    config_dir.mkdir()
    token_dir = cache_dir / "profiles"
    token_dir.mkdir(parents=True)
    alias = "실전계좌"
    digest = hashlib.sha256(alias.encode("utf-8")).hexdigest()[:16]
    (config_dir / "settings.json").write_text(
        json.dumps(
            {
                "current_profile": alias,
                "profiles": {
                    alias: {
                        "mode": "real",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (token_dir / f"profile-{digest}-token.json").write_text(
        json.dumps(
            {
                "access_token": "configured-token",
                "token_type": "bearer",
                "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                "mode": "real",
                "profile": alias,
            }
        ),
        encoding="utf-8",
    )

    def fake_keyring_getter(service_name: str, username: str) -> str | None:
        assert service_name == f"kiwoom-profile-{digest}"
        return {"appkey": "configured-key", "secretkey": "configured-secret"}.get(username)

    config = KiwoomUsCredentialConfig.from_kiwoomcli_profile(
        values={
            "KIWOOM_US_PROFILE": alias,
            "KIWOOM_US_READ_ONLY": "true",
            "KIWOOM_US_ENABLE_ORDER": "false",
        },
        config_dir=config_dir,
        cache_dir=cache_dir,
        keyring_getter=fake_keyring_getter,
    )

    assert config.app_key == "configured-key"
    assert config.app_secret == "configured-secret"
    assert config.token == "configured-token"
    assert config.source == f"kiwoomcli-profile:{alias}"
    assert config.redacted_summary()["tokenConfigured"] is True


def test_us_kiwoomcli_profile_loader_redacted_summary_hides_values(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    alias = "실전계좌"
    digest = hashlib.sha256(alias.encode("utf-8")).hexdigest()[:16]
    (config_dir / "settings.json").write_text(
        json.dumps({"current_profile": alias, "profiles": {alias: {"mode": "real"}}}),
        encoding="utf-8",
    )

    def fake_keyring_getter(service_name: str, username: str) -> str | None:
        assert service_name == f"kiwoom-profile-{digest}"
        return {"appkey": "secret-key-value", "secretkey": "secret-value"}.get(username)

    config = KiwoomUsCredentialConfig.from_kiwoomcli_profile(
        values={"KIWOOM_US_PROFILE": alias},
        config_dir=config_dir,
        cache_dir=tmp_path / "missing-cache",
        keyring_getter=fake_keyring_getter,
    )

    summary = str(config.redacted_summary())
    assert "secret-key-value" not in summary
    assert "secret-value" not in summary
    assert "kiwoomcli-profile" in summary


def test_us_kiwoomcli_profile_loader_blocks_mode_mismatch(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    alias = "실전계좌"
    (config_dir / "settings.json").write_text(
        json.dumps({"current_profile": alias, "profiles": {alias: {"mode": "real"}}}),
        encoding="utf-8",
    )

    with pytest.raises(MissingCredentialError, match="mode"):
        KiwoomUsCredentialConfig.from_kiwoomcli_profile(
            values={"KIWOOM_US_PROFILE": alias, "KIWOOM_US_MODE": "demo"},
            config_dir=config_dir,
            cache_dir=tmp_path / "cache",
            keyring_getter=lambda *_: "configured",
        )


def test_us_kiwoomcli_profile_loader_accepts_live_as_real_mode(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    alias = "실전계좌"
    digest = hashlib.sha256(alias.encode("utf-8")).hexdigest()[:16]
    (config_dir / "settings.json").write_text(
        json.dumps({"current_profile": alias, "profiles": {alias: {"mode": "real"}}}),
        encoding="utf-8",
    )

    def fake_keyring_getter(service_name: str, username: str) -> str | None:
        assert service_name == f"kiwoom-profile-{digest}"
        return {"appkey": "configured-key", "secretkey": "configured-secret"}.get(username)

    config = KiwoomUsCredentialConfig.from_kiwoomcli_profile(
        values={"KIWOOM_US_PROFILE": alias, "KIWOOM_US_MODE": "live"},
        config_dir=config_dir,
        cache_dir=tmp_path / "missing-cache",
        keyring_getter=fake_keyring_getter,
    )

    assert config.app_key == "configured-key"
    assert config.app_secret == "configured-secret"


def test_us_kiwoomcli_profile_loader_allows_token_cache_when_keyring_is_unavailable(tmp_path):
    config_dir = tmp_path / "config"
    cache_dir = tmp_path / "cache"
    config_dir.mkdir()
    token_dir = cache_dir / "profiles"
    token_dir.mkdir(parents=True)
    alias = "실전계좌"
    digest = hashlib.sha256(alias.encode("utf-8")).hexdigest()[:16]
    (config_dir / "settings.json").write_text(
        json.dumps({"current_profile": alias, "profiles": {alias: {"mode": "real"}}}),
        encoding="utf-8",
    )
    (token_dir / f"profile-{digest}-token.json").write_text(
        json.dumps(
            {
                "access_token": "configured-token",
                "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                "mode": "real",
                "profile": alias,
            }
        ),
        encoding="utf-8",
    )

    config = KiwoomUsCredentialConfig.from_kiwoomcli_profile(
        values={"KIWOOM_US_PROFILE": alias},
        config_dir=config_dir,
        cache_dir=cache_dir,
        keyring_getter=lambda *_: None,
    )

    assert config.app_key is None
    assert config.app_secret is None
    assert config.token == "configured-token"
    assert config.redacted_summary()["tokenConfigured"] is True


def test_us_macos_security_keyring_timeout_returns_none(monkeypatch):
    def fake_run(*args, **kwargs):
        assert kwargs["timeout"] == credential_module.KEYRING_READ_TIMEOUT_SECONDS
        raise credential_module.subprocess.TimeoutExpired(cmd=["security"], timeout=kwargs["timeout"])

    monkeypatch.setattr(credential_module.subprocess, "run", fake_run)

    assert credential_module._macos_security_get_password("service", "appkey") is None


def test_secret_like_payload_fields_are_blocked():
    with pytest.raises(UsSecretExposureError):
        assert_no_secret_in_payload({"appkey": "configured"})

    with pytest.raises(UsSecretExposureError):
        assert_no_secret_in_payload({"nested": {"account_no": "configured"}})


def test_redacted_secret_placeholders_are_allowed():
    assert_no_secret_in_payload({"Authorization": "Bearer <redacted>", "token": "<redacted>"})
