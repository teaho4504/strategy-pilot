from __future__ import annotations

import argparse
import asyncio
from datetime import date, timedelta
import re

from app.services.kiwoom_session import KiwoomSessionError, KiwoomSessionManager
from trading_engine.providers.kiwoom_us.http_sender import (
    KiwoomUsHttpSenderError,
    KiwoomUsUrllibHttpSender,
)
from trading_engine.providers.kiwoom_us.http_transport import (
    KiwoomUsHttpReadOnlyTransport,
    KiwoomUsTransportError,
)
from trading_engine.providers.kiwoom_us.rest_client import KiwoomUsRestClientSkeleton
from trading_engine.providers.kiwoom_us.schemas import UsReadOnlyTrResponse
from trading_engine.providers.kiwoom_us.smoke_plan import US_READONLY_HTTP_SENDER_CONFIRM


ACCOUNT_SHAPE_AUDIT_CONFIRM = "I_UNDERSTAND_US_ACCOUNT_READ_ONLY"
ACCOUNT_TR_CONTRACTS: dict[str, tuple[set[str], set[str]]] = {
    "ust21110": (
        {"krw_entra", "result_list"},
        {"crnc_code", "fc_entra", "fc_ord_alowa"},
    ),
    "ust21120": (
        {"aset_evlt_amt", "result_list"},
        {"crnc_code", "evlt_amt"},
    ),
    "ust21630": (
        {"tot_tdy_pl_amt", "tot_tdy_pl_amt_krw", "result_list"},
        {"stk_cd", "crnc_code", "tdy_pl_amt", "pl_rt"},
    ),
    "ust21650": (
        {"fr_tot_evltv", "to_tot_evltv", "evlt_profit", "profit_rate"},
        set(),
    ),
    "usa21670": (
        {"result_list"},
        {"base_dt", "stk_evlta", "pl_amt", "prft_rt"},
    ),
}


def build_safe_account_shape_summary(
    response: UsReadOnlyTrResponse,
) -> dict[str, object]:
    top_required, row_required = ACCOUNT_TR_CONTRACTS[response.tr_id]
    payload = response.data
    rows = payload.get("result_list") or payload.get("result_lsit") or []
    row_keys = sorted(
        {
            str(key)
            for row in rows
            if isinstance(row, dict)
            for key in row.keys()
        }
    ) if isinstance(rows, list) else []
    return {
        "tr_id": response.tr_id,
        "return_code": response.return_code,
        "top_level_keys": sorted(payload.keys()),
        "top_level_contract_present": top_required.issubset(payload.keys()),
        "result_list_is_list": isinstance(rows, list),
        "rows_present": bool(rows) if isinstance(rows, list) else False,
        "row_schema_keys": row_keys,
        "row_contract_present": (
            row_required.issubset(row_keys) if row_keys and row_required else None
        ),
    }


async def run_audit(
    *,
    profile: str | None,
    today: date | None = None,
) -> list[dict[str, object]]:
    session = await KiwoomSessionManager().create_session_from_cli_profile(profile)
    transport = KiwoomUsHttpReadOnlyTransport(
        token_provider=lambda: session.access_token,
        sender=KiwoomUsUrllibHttpSender(
            network_enabled=True,
            confirm_phrase=US_READONLY_HTTP_SENDER_CONFIRM,
        ),
        base_url=session.base_url,
    )
    client = KiwoomUsRestClientSkeleton(
        access_token_present=True,
        live_provider_enabled=True,
        read_only=True,
        order_enabled=False,
        transport=transport,
    )
    end = today or date.today()
    start = end - timedelta(days=7)
    requests = (
        ("ust21110", {}),
        ("ust21120", {"cmsn_incl_tp": "", "exrt_tp": ""}),
        ("ust21630", {"stex_tp": "", "stk_cd": "", "fc_krw_tp": "1"}),
        ("ust21650", {"fr_dt": start.strftime("%Y%m%d"), "to_dt": end.strftime("%Y%m%d")}),
        ("usa21670", {"from": start.strftime("%Y%m%d"), "to": end.strftime("%Y%m%d")}),
    )
    responses = [
        _execute_or_no_data(client, tr_id, body)
        for tr_id, body in requests
    ]
    return [build_safe_account_shape_summary(response) for response in responses]


def _execute_or_no_data(
    client: KiwoomUsRestClientSkeleton,
    tr_id: str,
    body: dict[str, object],
) -> UsReadOnlyTrResponse:
    try:
        return client.execute_readonly_tr(tr_id, body)
    except KiwoomUsTransportError as exc:
        if str(exc.return_code) != "20":
            raise
        return UsReadOnlyTrResponse(
            tr_id=tr_id,
            return_code=str(exc.return_code),
            return_msg="NO_DATA",
            data={"noData": True},
            unknown_fields={"noData": True},
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Shape-only Kiwoom US account read-only audit"
    )
    parser.add_argument("--profile")
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args(argv)
    if args.confirm != ACCOUNT_SHAPE_AUDIT_CONFIRM:
        print("account_shape_audit_completed=False")
        print("error_type=ConfirmationError")
        return 2
    try:
        summaries = asyncio.run(run_audit(profile=args.profile))
    except (
        KiwoomSessionError,
        KiwoomUsHttpSenderError,
        KiwoomUsTransportError,
        RuntimeError,
        ValueError,
    ) as exc:
        print("account_shape_audit_completed=False")
        print(f"error_type={type(exc).__name__}")
        if isinstance(exc, KiwoomUsTransportError):
            print(f"failed_tr_id={exc.tr_id}")
            print(f"return_code={exc.return_code}")
            print(f"return_message={_safe_error_message(exc.return_msg)}")
        return 2
    print("Kiwoom US account shape read-only audit")
    print("network_used=True")
    print("order_enabled=False")
    for summary in summaries:
        print(summary)
    print("account_shape_audit_completed=True")
    return 0


def _safe_error_message(value: object) -> str:
    text = " ".join(str(value or "").strip().split())[:160]
    text = re.sub(r"[A-Za-z0-9_-]{20,}", "[redacted]", text)
    text = re.sub(r"\d{6,}", "[redacted]", text)
    return text or "UNAVAILABLE"


if __name__ == "__main__":
    raise SystemExit(main())
