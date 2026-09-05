from __future__ import annotations

import hashlib
import json

from app.services import kiwoom_cli_profile as profile_module


def _write_profile_settings(path, *, alias: str = "windows-real") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "current_profile": alias,
                "profiles": {alias: {"mode": "real"}},
            }
        ),
        encoding="utf-8",
    )


def test_settings_path_uses_official_platformdirs_location(monkeypatch, tmp_path):
    expected_directory = tmp_path / "AppData" / "Local" / "kiwoom"
    monkeypatch.setattr(profile_module, "user_config_dir", lambda app_name: str(expected_directory))

    assert profile_module._settings_path() == expected_directory / "settings.json"


def test_windows_profile_uses_official_keyring_service_name(monkeypatch, tmp_path):
    alias = "windows-real"
    settings_path = tmp_path / "settings.json"
    _write_profile_settings(settings_path, alias=alias)
    monkeypatch.setattr(profile_module, "_settings_path", lambda: settings_path)

    service_name = f"kiwoom-profile-{hashlib.sha256(alias.encode('utf-8')).hexdigest()[:16]}"
    requested: list[tuple[str, str]] = []

    def fake_get_password(service: str, username: str) -> str:
        requested.append((service, username))
        return "test-app-key" if username == "appkey" else "test-secret-key"

    monkeypatch.setattr(profile_module.keyring, "get_password", fake_get_password)

    credential = profile_module.load_kiwoom_cli_credential()

    assert credential.profile == alias
    assert credential.mode == "real"
    assert requested == [(service_name, "appkey"), (service_name, "secretkey")]


def test_safe_profile_summary_never_reads_or_returns_secrets(monkeypatch, tmp_path):
    settings_path = tmp_path / "settings.json"
    _write_profile_settings(settings_path)
    monkeypatch.setattr(profile_module, "_settings_path", lambda: settings_path)
    monkeypatch.setattr(
        profile_module.keyring,
        "get_password",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("keyring must not be read")),
    )

    summaries = profile_module.safe_kiwoom_cli_profiles()

    assert summaries == [
        {
            "profile": "windows-real",
            "mode": "real",
            "current": True,
            "accountLabel": "계좌번호 미등록",
        }
    ]
    assert "appkey" not in repr(summaries).lower()
    assert "secret" not in repr(summaries).lower()


def test_safe_profile_summary_returns_all_three_real_profiles_with_masked_labels(monkeypatch, tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "current_profile": "real-b",
                "profiles": {
                    "real-a": {"mode": "real", "account": "9000-1001"},
                    "real-b": {"mode": "real", "account_no": "9000-1002"},
                    "real-c": {"mode": "real", "accountNo": "9000-1003"},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(profile_module, "_settings_path", lambda: settings_path)
    monkeypatch.setattr(profile_module, "_local_account_labels", lambda: {})

    summaries = profile_module.safe_kiwoom_cli_profiles()

    assert [item["profile"] for item in summaries] == ["real-a", "real-b", "real-c"]
    assert [item["accountLabel"] for item in summaries] == ["****-1001", "****-1002", "****-1003"]
    assert [item["current"] for item in summaries] == [False, True, False]
    assert "9000-1001" not in repr(summaries)
    assert "9000-1002" not in repr(summaries)
    assert "9000-1003" not in repr(summaries)
