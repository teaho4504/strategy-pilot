from __future__ import annotations

import os
from pathlib import Path

from trading_engine.providers.kiwoom_us.credentials import KiwoomUsCredentialConfig, MissingCredentialError
from trading_engine.providers.kiwoom_us.safety import UsOrderBlockedError, assert_us_order_tr_blocked
from trading_engine.providers.kiwoom_us.smoke_plan import (
    US_READONLY_SMOKE_STEPS,
    safe_smoke_result_summary,
    validate_us_readonly_smoke_environment,
    validate_us_readonly_smoke_plan,
)


BACKEND_DIR = Path(__file__).resolve().parents[1]
BLOCKED_US_ORDER_TRS = ("ust20000", "ust20001", "ust20002", "ust20003", "F4")


def load_backend_env_file(path: Path | None = None) -> None:
    env_path = path or BACKEND_DIR / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def run_precheck() -> int:
    load_backend_env_file()
    env = dict(os.environ)
    validate_us_readonly_smoke_environment(env)
    config = _load_credential_config(env)
    _require_configured_credential_source(config, env)
    validate_us_readonly_smoke_plan()
    _assert_order_trs_blocked()
    _print_safe_summary(config)
    return 0


def _assert_order_trs_blocked() -> None:
    for tr_id in BLOCKED_US_ORDER_TRS:
        try:
            assert_us_order_tr_blocked(tr_id)
        except UsOrderBlockedError:
            continue
        raise RuntimeError(f"US order TR was not blocked: {tr_id}")


def _print_safe_summary(config: KiwoomUsCredentialConfig) -> None:
    print("Kiwoom US read-only precheck")
    print("network_used=False")
    print(f"credential_summary={config.redacted_summary()}")
    print(f"smoke_steps={[step.tr_id for step in US_READONLY_SMOKE_STEPS]}")
    print(f"blocked_order_trs={list(BLOCKED_US_ORDER_TRS)}")
    example = safe_smoke_result_summary("ust21110", "0", "OK", {"krw_entra": "redacted", "ord_alow_amt": "redacted"})
    print(f"safe_output_example={example}")
    print("precheck_passed=True")


def _load_credential_config(env: dict[str, str]) -> KiwoomUsCredentialConfig:
    if str(env.get("KIWOOM_US_CREDENTIAL_SOURCE", "")).strip().lower() == "kiwoomcli":
        return KiwoomUsCredentialConfig.from_kiwoomcli_profile(values=env)
    return KiwoomUsCredentialConfig.from_mapping(env, source="env")


def _require_configured_credential_source(config: KiwoomUsCredentialConfig, env: dict[str, str]) -> None:
    if str(env.get("KIWOOM_US_CREDENTIAL_SOURCE", "")).strip().lower() == "kiwoomcli":
        if config.token:
            return
        # A valid CLI profile may have no reusable token cache yet.  Its OS
        # keyring credentials are still sufficient for the backend to issue a
        # fresh session token without exposing either value.
        config.require_app_credentials()
        return
    config.require_app_credentials()


def main() -> int:
    try:
        return run_precheck()
    except (RuntimeError, MissingCredentialError, UsOrderBlockedError) as exc:
        print("Kiwoom US read-only precheck")
        print("network_used=False")
        print("precheck_passed=False")
        print(f"error_type={type(exc).__name__}")
        print(f"error={_sanitize_error(exc)}")
        return 2


def _sanitize_error(exc: Exception) -> str:
    message = str(exc).replace("\n", " ").replace("\r", " ")
    return message[:160]


if __name__ == "__main__":
    raise SystemExit(main())
