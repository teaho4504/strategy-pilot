from __future__ import annotations

import asyncio
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Callable, Optional


CONFIRM_VALUE = "I_UNDERSTAND_READ_ONLY"
BACKEND_DIR = Path(__file__).resolve().parents[1]

SENSITIVE_ENV_NAMES = {
    "KIWOOM_APP_KEY",
    "KIWOOM_SECRET_KEY",
    "KIWOOM_APP_SECRET",
    "KIWOOM_ACCOUNT_NO",
    "KIWOOM_ACCESS_TOKEN",
}


class LiveVerifyBlocked(RuntimeError):
    pass


def load_backend_env_file(path: Optional[Path] = None) -> None:
    env_path = path or BACKEND_DIR / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


@dataclass(frozen=True)
class VerifyStep:
    api_id: str
    description: str
    call: Callable[[], object]
    validate: Callable[[Any], None]


def validate_live_verify_environment(env: dict[str, str]) -> None:
    required = {
        "KIWOOM_MODE": "live",
        "KIWOOM_READ_ONLY": "true",
        "KIWOOM_ENABLE_ORDER": "false",
        "KIWOOM_LIVE_VERIFY_CONFIRM": CONFIRM_VALUE,
    }
    failed = [name for name, expected in required.items() if env.get(name) != expected]
    if failed:
        raise LiveVerifyBlocked(f"Live read-only verification blocked. Invalid or missing: {', '.join(failed)}")


def schema_keys(body: dict[str, object]) -> list[str]:
    return sorted(str(key) for key in body.keys())


def print_safe_step_result(api_id: str, body: dict[str, object]) -> None:
    print(f"{api_id}: success schema_keys={schema_keys(body)}")


def print_safe_failure(api_id: str, exc: Exception) -> None:
    if isinstance(exc, MapperValidationError):
        print(f"{api_id}: mapper_validation_error missing_fields={exc.missing_fields}")
        return
    print(f"{api_id}: failed error_type={type(exc).__name__}")


async def request_token_only() -> object:
    from app.services.kiwoom_client import KiwoomResponse
    from app.services.token_manager import token_manager

    await token_manager.get_access_token()
    return KiwoomResponse(api_id="au10001", body={"token_cached": True}, cont_yn="N", next_key="")


async def request_single(api_id: str, payload: Optional[dict[str, object]] = None) -> object:
    from app.services.kiwoom_client import kiwoom_client

    return await kiwoom_client.request_tr(api_id, payload)


async def request_all(api_id: str, payload: Optional[dict[str, object]] = None) -> object:
    from app.services.kiwoom_client import kiwoom_client

    return await kiwoom_client.request_tr_all(api_id, payload)


def validate_token_response(response: object) -> None:
    from app.services.account_service import MapperValidationError

    if response.body.get("token_cached") is not True:
        raise MapperValidationError("au10001", ["token_cached"])


def validate_account_response(response: object) -> None:
    from app.services.account_service import map_account_response

    map_account_response(response.body)


def validate_cash_response(response: object) -> None:
    from app.services.account_service import map_cash_response

    map_cash_response(response.body)


def validate_portfolio_response(response: object) -> None:
    from app.services.account_service import map_portfolio_response, parse_int

    # The live verification only validates the kt00004 shape. Cash is checked by kt00001.
    map_portfolio_response(response.body, cash=parse_int(response.body.get("entr")))


def validate_holdings_response(response: object) -> None:
    from app.services.account_service import MapperValidationError, map_holdings_response

    rows = response.body.get("stk_cntr_remn") or []
    if not isinstance(rows, list):
        raise MapperValidationError("kt00005", ["stk_cntr_remn"])
    map_holdings_response(rows)


def validate_performance_response(response: object) -> None:
    from app.services.account_service import MapperValidationError, map_performance_response

    rows = response.body.get("acnt_prft_rt") or []
    if not isinstance(rows, list):
        raise MapperValidationError("ka10085", ["acnt_prft_rt"])
    map_performance_response(rows)


def build_steps() -> list[VerifyStep]:
    from app.core.config import get_settings

    settings = get_settings()
    return [
        VerifyStep("au10001", "access token issue", request_token_only, validate_token_response),
        VerifyStep("ka00001", "account lookup", lambda: request_single("ka00001"), validate_account_response),
        VerifyStep("kt00001", "cash lookup", lambda: request_single("kt00001", {"qry_tp": settings.kiwoom_cash_qry_tp}), validate_cash_response),
        VerifyStep(
            "kt00004",
            "account valuation lookup",
            lambda: request_single("kt00004", {"qry_tp": settings.kiwoom_portfolio_qry_tp, "dmst_stex_tp": settings.kiwoom_dmst_stex_tp}),
            validate_portfolio_response,
        ),
        VerifyStep("kt00005", "holdings lookup", lambda: request_all("kt00005", {"dmst_stex_tp": settings.kiwoom_dmst_stex_tp}), validate_holdings_response),
        VerifyStep("ka10085", "account performance lookup", lambda: request_all("ka10085", {"stex_tp": settings.kiwoom_stex_tp}), validate_performance_response),
    ]


async def run_live_readonly_verification() -> int:
    validate_live_verify_environment(dict(os.environ))
    from app.core.config import get_settings
    from app.services.account_service import MapperValidationError
    from app.services.kiwoom_client import KiwoomClientError
    from app.services.token_manager import TokenManagerError

    settings = get_settings()
    print("Kiwoom live read-only verification")
    print(f"mode={settings.kiwoom_mode} readOnly={settings.kiwoom_read_only} orderEnabled={settings.order_enabled}")

    for step in build_steps():
        print(f"{step.api_id}: start {step.description}")
        try:
            response = await step.call()
            step.validate(response)
            print_safe_step_result(step.api_id, response.body)
        except (KiwoomClientError, TokenManagerError, MapperValidationError) as exc:
            print_safe_failure(step.api_id, exc)
            print("verification stopped")
            return 1
    print("verification completed")
    return 0


def main() -> int:
    try:
        load_backend_env_file()
        return asyncio.run(run_live_readonly_verification())
    except LiveVerifyBlocked as exc:
        print(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
