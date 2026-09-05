from __future__ import annotations

from trading_engine.providers.kiwoom_us.smoke_plan import US_READONLY_SMOKE_CONFIRM
from trading_engine.providers.kiwoom_us.credentials import KiwoomUsCredentialConfig


def test_cli_precheck_accepts_keyring_credentials_without_cached_token():
    from scripts.verify_us_readonly_precheck import _require_configured_credential_source

    config = KiwoomUsCredentialConfig(
        app_key="configured-app-key",
        app_secret="configured-secret-key",
        token=None,
        source="kiwoomcli-profile:test",
        read_only=True,
        order_enabled=False,
    )

    _require_configured_credential_source(config, {"KIWOOM_US_CREDENTIAL_SOURCE": "kiwoomcli"})


def test_us_readonly_precheck_blocks_without_confirmation(monkeypatch, capsys):
    from scripts import verify_us_readonly_precheck

    monkeypatch.delenv("KIWOOM_US_SMOKE_CONFIRM", raising=False)
    monkeypatch.setenv("KIWOOM_US_READ_ONLY", "true")
    monkeypatch.setenv("KIWOOM_US_ENABLE_ORDER", "false")
    monkeypatch.setenv("KIWOOM_US_LIVE_PROVIDER", "true")

    result = verify_us_readonly_precheck.main()
    output = capsys.readouterr().out

    assert result == 2
    assert "network_used=False" in output
    assert "KIWOOM_US_SMOKE_CONFIRM" in output


def test_us_readonly_precheck_passes_with_safe_configuration(monkeypatch, capsys):
    from scripts import verify_us_readonly_precheck

    monkeypatch.setenv("KIWOOM_US_READ_ONLY", "true")
    monkeypatch.setenv("KIWOOM_US_ENABLE_ORDER", "false")
    monkeypatch.setenv("KIWOOM_US_LIVE_PROVIDER", "true")
    monkeypatch.setenv("KIWOOM_US_SMOKE_CONFIRM", US_READONLY_SMOKE_CONFIRM)
    monkeypatch.setenv("KIWOOM_US_APP_KEY", "configured")
    monkeypatch.setenv("KIWOOM_US_APP_SECRET", "configured")

    result = verify_us_readonly_precheck.main()
    output = capsys.readouterr().out

    assert result == 0
    assert "network_used=False" in output
    assert "precheck_passed=True" in output
    assert "ust21110" in output
    assert "ust20000" in output
    assert "configured" not in output


def test_us_readonly_precheck_blocks_order_enabled(monkeypatch, capsys):
    from scripts import verify_us_readonly_precheck

    monkeypatch.setenv("KIWOOM_US_READ_ONLY", "true")
    monkeypatch.setenv("KIWOOM_US_ENABLE_ORDER", "true")
    monkeypatch.setenv("KIWOOM_US_LIVE_PROVIDER", "true")
    monkeypatch.setenv("KIWOOM_US_SMOKE_CONFIRM", US_READONLY_SMOKE_CONFIRM)
    monkeypatch.setenv("KIWOOM_US_APP_KEY", "configured")
    monkeypatch.setenv("KIWOOM_US_APP_SECRET", "configured")

    result = verify_us_readonly_precheck.main()
    output = capsys.readouterr().out

    assert result == 2
    assert "network_used=False" in output
    assert "KIWOOM_US_ENABLE_ORDER" in output
