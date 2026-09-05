from __future__ import annotations

import argparse
import asyncio
from decimal import Decimal, InvalidOperation
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
from trading_engine.providers.kiwoom_us.smoke_plan import (
    US_READONLY_HTTP_SENDER_CONFIRM,
)


ORDER_STATE_AUDIT_CONFIRM = "I_UNDERSTAND_US_ORDER_STATE_READ_ONLY"
UST21050_ROW_FIELDS = {
    "ord_no",
    "orig_ord_no",
    "stk_code",
    "slby_tp",
    "ord_qty",
    "cntr_qty",
    "cncl_qty",
    "ord_remnq",
    "ord_stat",
}
UST21510_ROW_FIELDS = {
    "ord_no",
    "cntr_qty",
    "cntr_uv",
    "ord_stat",
}
UST21070_SYMBOL_FIELDS = {"stk_code", "stk_cd"}
UST21070_QUANTITY_FIELDS = {
    "sell_alowq",
    "poss_qty",
    "sell_psbl_qty",
}
UST21070_EXCHANGE_FIELDS = {
    "stex_tp",
    "stex_nm",
    "ovrs_excg_cd",
    "excg_cd",
}
UST31490_FIELDS = {"min_ord_alowq", "min_ord_alowa", "crnc_code"}


def build_safe_shape_summary(response: UsReadOnlyTrResponse) -> dict[str, object]:
    payload = response.data
    summary: dict[str, object] = {
        "tr_id": response.tr_id,
        "return_code": response.return_code,
        "top_level_keys": sorted(payload.keys()),
    }
    if response.tr_id in {"ust21050", "ust21510", "ust21070"}:
        rows = payload.get("result_list") or payload.get("result_lsit") or []
        row_keys = sorted(
            {
                str(key)
                for row in rows
                if isinstance(row, dict)
                for key in row.keys()
            }
        ) if isinstance(rows, list) else []
        required_fields_present: bool | None = None
        if row_keys:
            row_key_set = set(row_keys)
            if response.tr_id == "ust21050":
                required_fields_present = UST21050_ROW_FIELDS.issubset(
                    row_key_set
                )
            elif response.tr_id == "ust21510":
                required_fields_present = UST21510_ROW_FIELDS.issubset(
                    row_key_set
                ) and bool(UST21070_SYMBOL_FIELDS & row_key_set)
            else:
                required_fields_present = (
                    bool(UST21070_SYMBOL_FIELDS & row_key_set)
                    and bool(UST21070_QUANTITY_FIELDS & row_key_set)
                    and bool(UST21070_EXCHANGE_FIELDS & row_key_set)
                )
        summary.update(
            {
                "result_list_is_list": isinstance(rows, list),
                "rows_present": bool(rows) if isinstance(rows, list) else False,
                "row_schema_keys": row_keys,
                "required_row_fields_present": required_fields_present,
            }
        )
    elif response.tr_id == "ust31490":
        summary.update(
            {
                "required_fields_present": UST31490_FIELDS.issubset(payload.keys()),
                "quantity_is_numeric": _is_nonnegative_number(payload.get("min_ord_alowq")),
                "amount_is_numeric": _is_nonnegative_number(payload.get("min_ord_alowa")),
                "currency_is_usd": str(payload.get("crnc_code") or "").strip().upper() == "USD",
            }
        )
    return summary


async def run_audit(
    *,
    profile: str | None,
    symbol: str,
    exchange: str,
    price: str,
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
    responses: list[UsReadOnlyTrResponse] = []
    responses.append(_execute_or_no_data(
        client,
        "ust21050",
        {"ord_dt": "", "slby_tp": "0", "stk_code": symbol},
    ))
    responses.append(_execute_or_no_data(
        client,
        "ust21510",
        {"slby_tp": "0", "stex_tp": exchange, "stk_cd": symbol},
    ))
    responses.append(_execute_or_no_data(
        client,
        "ust21070",
        {"stex_tp": exchange, "stk_cd": symbol},
    ))
    responses.append(
        client.execute_readonly_tr(
            "ust31490",
            {"stex_tp": exchange, "stk_cd": symbol, "uv": price},
        )
    )
    return [build_safe_shape_summary(response) for response in responses]


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
        description="Shape-only Kiwoom US order-state read-only audit"
    )
    parser.add_argument("--profile")
    parser.add_argument("--symbol", default="NVDA")
    parser.add_argument("--exchange", choices=("ND", "NY", "NA"), default="ND")
    parser.add_argument("--price", default="1")
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args(argv)

    if args.confirm != ORDER_STATE_AUDIT_CONFIRM:
        print("order_state_audit_completed=False")
        print("error_type=ConfirmationError")
        return 2

    try:
        symbol = _safe_symbol(args.symbol)
        price = _positive_price(args.price)
        summaries = asyncio.run(
            run_audit(
                profile=args.profile,
                symbol=symbol,
                exchange=args.exchange,
                price=price,
            )
        )
    except (
        KiwoomSessionError,
        KiwoomUsHttpSenderError,
        KiwoomUsTransportError,
        RuntimeError,
        ValueError,
    ) as exc:
        print("order_state_audit_completed=False")
        print(f"error_type={type(exc).__name__}")
        if isinstance(exc, KiwoomUsTransportError):
            print(f"failed_tr_id={exc.tr_id}")
            print(f"return_code={exc.return_code}")
            print(f"return_message={_safe_error_message(exc.return_msg)}")
        return 2

    print("Kiwoom US order-state read-only audit")
    print("network_used=True")
    print("order_enabled=False")
    for summary in summaries:
        print(summary)
    print("order_state_audit_completed=True")
    return 0


def _safe_symbol(value: str) -> str:
    symbol = "".join(
        character
        for character in str(value).strip().upper()
        if character.isalnum() or character in {".", "-"}
    )[:12]
    if not symbol:
        raise ValueError("symbol is required")
    return symbol


def _positive_price(value: str) -> str:
    try:
        price = Decimal(str(value).strip())
    except InvalidOperation as exc:
        raise ValueError("price must be numeric") from exc
    if not price.is_finite() or price <= 0:
        raise ValueError("price must be positive")
    return format(price.normalize(), "f")


def _is_nonnegative_number(value: object) -> bool:
    try:
        number = Decimal(str(value).replace(",", "").strip())
    except InvalidOperation:
        return False
    return number.is_finite() and number >= 0


def _safe_error_message(value: object) -> str:
    text = " ".join(str(value or "").strip().split())[:160]
    text = re.sub(r"[A-Za-z0-9_-]{20,}", "[redacted]", text)
    text = re.sub(r"\d{6,}", "[redacted]", text)
    return text or "UNAVAILABLE"


if __name__ == "__main__":
    raise SystemExit(main())
