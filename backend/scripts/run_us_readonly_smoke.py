from __future__ import annotations

import argparse
import os
from pathlib import Path

from trading_engine.providers.kiwoom_us.credentials import KiwoomUsCredentialConfig, MissingCredentialError
from trading_engine.providers.kiwoom_us.http_sender import KiwoomUsUrllibHttpSender
from trading_engine.providers.kiwoom_us.http_transport import KiwoomUsHttpReadOnlyTransport
from trading_engine.providers.kiwoom_us.rest_client import KiwoomUsRestClientSkeleton
from trading_engine.providers.kiwoom_us.schemas import UsReadOnlyTrResponse
from trading_engine.providers.kiwoom_us.smoke_plan import (
    US_READONLY_SMOKE_STEPS,
    safe_smoke_result_summary,
    select_us_readonly_smoke_steps,
    resolve_us_readonly_smoke_body,
    validate_us_readonly_http_sender_environment,
    validate_us_readonly_smoke_environment,
    validate_us_readonly_smoke_plan,
)
from trading_engine.providers.kiwoom_us.transport import FakeKiwoomUsTransport


BACKEND_DIR = Path(__file__).resolve().parents[1]


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


def build_fake_transport(steps=US_READONLY_SMOKE_STEPS) -> FakeKiwoomUsTransport:
    return FakeKiwoomUsTransport(
        responses={
            step.tr_id: UsReadOnlyTrResponse(
                tr_id=step.tr_id,
                return_code="0",
                return_msg="OK",
                data={"fixture_schema_key": True},
                unknown_fields={"fixture_schema_key": True},
            )
            for step in US_READONLY_SMOKE_STEPS
        }
    )


def run_smoke(*, fake: bool, live_http: bool, tr_id: str | None = None) -> int:
    load_backend_env_file()
    env = dict(os.environ)
    validate_us_readonly_smoke_environment(env)
    validate_us_readonly_smoke_plan()
    selected_steps = select_us_readonly_smoke_steps(tr_id)
    config = _load_credential_config(env)
    _require_configured_credential_source(config, env)

    if fake and live_http:
        raise RuntimeError("choose either --fake or --live-http, not both")

    if live_http:
        validate_us_readonly_http_sender_environment(env)
        config.require_token()
        transport = KiwoomUsHttpReadOnlyTransport(
            token_provider=lambda: config.token,
            sender=KiwoomUsUrllibHttpSender(
                network_enabled=True,
                confirm_phrase=env.get("KIWOOM_US_HTTP_SENDER_CONFIRM"),
            ),
        )
        network_used = True
        transport_name = "urllib-http"
    elif fake:
        transport = build_fake_transport(selected_steps)
        network_used = False
        transport_name = "fake"
    else:
        raise RuntimeError("US read-only smoke runner requires --fake or --live-http")

    client = KiwoomUsRestClientSkeleton(
        access_token_present=bool(config.token),
        live_provider_enabled=True,
        read_only=config.read_only,
        order_enabled=config.order_enabled,
        transport=transport,
    )

    print("Kiwoom US read-only smoke runner")
    print(f"network_used={network_used}")
    print(f"transport={transport_name}")
    print(f"selected_trs={[step.tr_id for step in selected_steps]}")
    for step in selected_steps:
        print(f"{step.tr_id}: start {step.purpose}")
        response = client.execute_readonly_tr(step.tr_id, resolve_us_readonly_smoke_body(step))
        print(safe_smoke_result_summary(response.tr_id, response.return_code, response.return_msg, response.data))
    print("smoke_runner_completed=True")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="US Kiwoom read-only smoke runner skeleton")
    parser.add_argument("--fake", action="store_true", help="Use fake local transport.")
    parser.add_argument("--live-http", action="store_true", help="Use guarded real HTTP sender for read-only smoke tests.")
    parser.add_argument("--tr", help="Run one allowed read-only smoke TR only, e.g. ust21110.")
    args = parser.parse_args(argv)
    try:
        return run_smoke(fake=args.fake, live_http=args.live_http, tr_id=args.tr)
    except (RuntimeError, MissingCredentialError) as exc:
        print("Kiwoom US read-only smoke runner")
        print("network_used=False")
        print("smoke_runner_completed=False")
        print(f"error_type={type(exc).__name__}")
        print(f"error={_sanitize_error(exc)}")
        return 2


def _sanitize_error(exc: Exception) -> str:
    return str(exc).replace("\n", " ").replace("\r", " ")[:160]


def _load_credential_config(env: dict[str, str]) -> KiwoomUsCredentialConfig:
    if str(env.get("KIWOOM_US_CREDENTIAL_SOURCE", "")).strip().lower() == "kiwoomcli":
        return KiwoomUsCredentialConfig.from_kiwoomcli_profile(values=env)
    return KiwoomUsCredentialConfig.from_mapping(env, source="env")


def _require_configured_credential_source(config: KiwoomUsCredentialConfig, env: dict[str, str]) -> None:
    if str(env.get("KIWOOM_US_CREDENTIAL_SOURCE", "")).strip().lower() == "kiwoomcli":
        config.require_token()
        return
    config.require_app_credentials()


if __name__ == "__main__":
    raise SystemExit(main())
