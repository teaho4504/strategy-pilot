from __future__ import annotations

from trading_engine.providers.kiwoom_us.smoke_plan import US_READONLY_HTTP_SENDER_CONFIRM, US_READONLY_SMOKE_CONFIRM


def _set_safe_env(monkeypatch) -> None:
    monkeypatch.setenv("KIWOOM_US_READ_ONLY", "true")
    monkeypatch.setenv("KIWOOM_US_ENABLE_ORDER", "false")
    monkeypatch.setenv("KIWOOM_US_LIVE_PROVIDER", "true")
    monkeypatch.setenv("KIWOOM_US_SMOKE_CONFIRM", US_READONLY_SMOKE_CONFIRM)
    monkeypatch.setenv("KIWOOM_US_APP_KEY", "configured")
    monkeypatch.setenv("KIWOOM_US_APP_SECRET", "configured")


def test_us_smoke_runner_blocks_without_fake_transport(monkeypatch, capsys):
    from scripts import run_us_readonly_smoke

    _set_safe_env(monkeypatch)

    result = run_us_readonly_smoke.main([])
    output = capsys.readouterr().out

    assert result == 2
    assert "network_used=False" in output
    assert "requires --fake or --live-http" in output


def test_us_smoke_runner_fake_transport_completes_without_network(monkeypatch, capsys):
    from scripts import run_us_readonly_smoke

    _set_safe_env(monkeypatch)

    result = run_us_readonly_smoke.main(["--fake"])
    output = capsys.readouterr().out

    assert result == 0
    assert "network_used=False" in output
    assert "transport=fake" in output
    assert "ust21110" in output
    assert "ust21650" in output
    assert "smoke_runner_completed=True" in output
    assert "configured" not in output


def test_us_smoke_runner_fake_transport_can_run_one_tr_only(monkeypatch, capsys):
    from scripts import run_us_readonly_smoke

    _set_safe_env(monkeypatch)

    result = run_us_readonly_smoke.main(["--fake", "--tr", "ust21110"])
    output = capsys.readouterr().out

    assert result == 0
    assert "network_used=False" in output
    assert "selected_trs=['ust21110']" in output
    assert "ust21110" in output
    assert "ust21120" not in output
    assert "smoke_runner_completed=True" in output


def test_us_smoke_runner_blocks_order_tr_selection(monkeypatch, capsys):
    from scripts import run_us_readonly_smoke

    _set_safe_env(monkeypatch)

    result = run_us_readonly_smoke.main(["--fake", "--tr", "ust20000"])
    output = capsys.readouterr().out

    assert result == 2
    assert "network_used=False" in output
    assert "not allowed" in output


def test_us_smoke_runner_blocks_without_confirmation(monkeypatch, capsys):
    from scripts import run_us_readonly_smoke

    _set_safe_env(monkeypatch)
    monkeypatch.delenv("KIWOOM_US_SMOKE_CONFIRM", raising=False)

    result = run_us_readonly_smoke.main(["--fake"])
    output = capsys.readouterr().out

    assert result == 2
    assert "network_used=False" in output
    assert "KIWOOM_US_SMOKE_CONFIRM" in output


def test_us_smoke_runner_live_http_blocks_without_extra_confirmation(monkeypatch, capsys):
    from scripts import run_us_readonly_smoke

    _set_safe_env(monkeypatch)
    monkeypatch.setenv("KIWOOM_US_ACCESS_TOKEN", "configured")

    result = run_us_readonly_smoke.main(["--live-http"])
    output = capsys.readouterr().out

    assert result == 2
    assert "network_used=False" in output
    assert "KIWOOM_US_HTTP_SENDER_ENABLED" in output
    assert "configured" not in output


def test_us_smoke_runner_live_http_blocks_without_token(monkeypatch, capsys):
    from scripts import run_us_readonly_smoke

    _set_safe_env(monkeypatch)
    monkeypatch.setenv("KIWOOM_US_HTTP_SENDER_ENABLED", "true")
    monkeypatch.setenv("KIWOOM_US_HTTP_SENDER_CONFIRM", US_READONLY_HTTP_SENDER_CONFIRM)
    monkeypatch.delenv("KIWOOM_US_ACCESS_TOKEN", raising=False)

    result = run_us_readonly_smoke.main(["--live-http"])
    output = capsys.readouterr().out

    assert result == 2
    assert "network_used=False" in output
    assert "token" in output
