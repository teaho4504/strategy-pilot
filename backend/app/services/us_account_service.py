from __future__ import annotations

import asyncio
import os
import json
from datetime import date, timedelta

from app.core.config import get_settings
from app.schemas.us_account import UsDailyAccountReturnRow, UsDailyAccountReturnSummary, UsHoldingForOrder, UsReadOnlyTrSummary
from app.core.time import now_iso
from app.services.runtime_state import mark_success
from app.services.kiwoom_session import get_active_or_latest_kiwoom_session
from trading_engine.providers.kiwoom_us.credentials import KiwoomUsCredentialConfig, MissingCredentialError
from trading_engine.providers.kiwoom_us.http_sender import (
    KiwoomUsHttpSenderBlockedError,
    KiwoomUsHttpSenderError,
    KiwoomUsUrllibHttpSender,
)
from trading_engine.providers.kiwoom_us.http_transport import KiwoomUsHttpReadOnlyTransport, KiwoomUsTransportError
from trading_engine.providers.kiwoom_us.response_mapper import UsMappingError, map_daily_account_return_response
from trading_engine.providers.kiwoom_us.rest_client import KiwoomUsRestClientSkeleton
from trading_engine.providers.kiwoom_us.schemas import UsReadOnlyTrResponse
from trading_engine.providers.kiwoom_us.smoke_plan import US_READONLY_HTTP_SENDER_CONFIRM


class UsReadOnlyConfigurationError(RuntimeError):
    pass


US_READONLY_MAX_CONTINUATION_PAGES = 20


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not str(value).strip():
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _date_range(from_date: str | None, to_date: str | None) -> tuple[str, str]:
    today = date.today()
    start = from_date or (today - timedelta(days=7)).strftime("%Y%m%d")
    end = to_date or today.strftime("%Y%m%d")
    for name, value in (("fromDate", start), ("toDate", end)):
        if len(value) != 8 or not value.isdigit():
            raise UsReadOnlyConfigurationError(f"{name} must be YYYYMMDD")
    return start, end


def _summary(response: UsReadOnlyTrResponse) -> UsReadOnlyTrSummary:
    return UsReadOnlyTrSummary(
        trId=response.tr_id,
        returnCode=response.return_code,
        returnMessage=response.return_msg,
        schemaKeys=sorted(response.data.keys()),
        data=response.data,
        normalized=_normalized_summary(response.tr_id, response.data),
        source=f"kiwoom-us-readonly-{response.tr_id}",
        updatedAt=now_iso(),
    )


def _result_rows(data: dict[str, object]) -> list[dict[str, object]]:
    raw = data.get("result_list") or data.get("result_lsit") or []
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _stable_row_identity(row: dict[str, object]) -> str:
    return json.dumps(
        row,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _empty_response(tr_id: str, return_code: str, return_msg: str) -> UsReadOnlyTrResponse:
    data: dict[str, object] = {"noData": True}
    return UsReadOnlyTrResponse(
        tr_id=tr_id,
        return_code=return_code,
        return_msg=return_msg,
        data=data,
        unknown_fields=data,
    )


def _normalized_summary(tr_id: str, data: dict[str, object]) -> dict[str, object] | None:
    row = _first_mapping(data.get("result_list") or data.get("result_lsit"))
    source = row or data
    if tr_id == "ust21110":
        cash = _first_field(source, "fc_entra", "frgn_stk_entr", "entr", "krw_entra", "cash")
        orderable = _first_field(source, "fc_ord_alowa", "fc_pymn_alowa", "ord_alowa", "ord_alow_amt", "ord_psbl_amt")
        return {
            "cashAmount": cash.value,
            "cashField": cash.key,
            "orderableAmount": orderable.value,
            "orderableField": orderable.key,
            "currency": _first_field(source, "crnc_code", "crnc_nm", "currency").value or "USD",
            "displayUnit": "raw",
        }
    if tr_id == "ust21120":
        valuation = _first_field(source, "aset_evlt_amt", "tot_aset_amt", "tot_evlt_amt", "evlt_amt_tot", "chg_evlt_amt")
        profit_loss = _first_field(source, "pl_amt", "tot_pl_tot", "lspft_amt", "evltv_prft")
        deposit = _first_field(source, "dast", "prsm_dpst_aset_amt", "deposit_asset")
        return {
            "valuationAmount": valuation.value,
            "valuationField": valuation.key,
            "profitLossAmount": profit_loss.value,
            "profitLossField": profit_loss.key,
            "depositAsset": deposit.value,
            "depositAssetField": deposit.key,
            "currency": _first_field(source, "crnc_code", "crnc_nm", "currency").value or "KRW",
            "displayUnit": "raw",
        }
    if tr_id == "ust21070":
        rows = _result_rows(data)
        sellable_count = 0
        total_sellable_quantity = 0
        quantity_field: str | None = None
        exchange_field: str | None = None
        price_field: str | None = None
        for item in rows:
            quantity = _first_field(item, "sell_alowq", "poss_qty", "qty", "sell_psbl_qty")
            exchange = _first_field(item, "stex_tp", "stex_nm", "ovrs_excg_cd", "excg_cd", "exchange")
            price = _first_field(item, "now_pric", "cur_prc", "last", "evlt_pric")
            quantity_value = _safe_int(quantity.value)
            if quantity.key and quantity_field is None:
                quantity_field = quantity.key
            if exchange.key and exchange_field is None:
                exchange_field = exchange.key
            if price.key and price_field is None:
                price_field = price.key
            if quantity_value and quantity_value > 0:
                sellable_count += 1
                total_sellable_quantity += quantity_value
        return {
            "holdingRows": len(rows),
            "sellableRows": sellable_count,
            "totalSellableQuantity": total_sellable_quantity,
            "quantityField": quantity_field,
            "exchangeField": exchange_field,
            "priceField": price_field,
            "currency": _first_field(source, "crnc_code", "crnc_nm", "currency").value or "USD",
            "displayUnit": "raw",
        }
    return None


class _FieldValue:
    def __init__(self, key: str | None, value: object | None) -> None:
        self.key = key
        self.value = value


def _first_mapping(value: object) -> dict[str, object] | None:
    if not isinstance(value, list):
        return None
    for item in value:
        if isinstance(item, dict):
            return item
    return None


def _first_field(data: dict[str, object], *keys: str) -> _FieldValue:
    for key in keys:
        value = data.get(key)
        if value is not None and str(value).strip():
            return _FieldValue(key, value)
    return _FieldValue(None, None)


def _safe_symbol(value: str | None) -> str:
    cleaned = "".join(ch for ch in str(value or "").upper().strip() if ch.isalnum() or ch in {".", "-"})
    return cleaned[:12]


def _safe_int(value: object) -> int | None:
    try:
        parsed = int(float(str(value).replace(",", "").replace("+", "").strip()))
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _safe_float(value: object) -> float | None:
    try:
        parsed = float(str(value).replace(",", "").replace("+", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _dedupe_reasons(reasons: list[str]) -> list[str]:
    deduped: list[str] = []
    for reason in reasons:
        if reason and reason not in deduped:
            deduped.append(reason)
    return deduped


def _first_positive_int(row: dict[str, object], *keys: str) -> tuple[str | None, int | None]:
    for key in keys:
        value = _safe_int(row.get(key))
        if value is not None and value > 0:
            return key, value
    return None, None


def _exchange_for_order(row: dict[str, object], *keys: str) -> tuple[str | None, str | None, str | None]:
    for key in keys:
        raw_value = row.get(key)
        if raw_value is None or not str(raw_value).strip():
            continue
        value = str(raw_value).strip()
        exchange = _normalize_us_exchange_for_order(value)
        if exchange:
            return key, exchange, value
        return key, None, value
    return None, None, None


def _normalize_us_exchange_for_order(value: str) -> str | None:
    normalized = str(value or "").strip().upper().replace(" ", "").replace("_", "").replace("-", "")
    if not normalized:
        return None
    aliases = {
        "NA": "NA",
        "AMEX": "NA",
        "AMERICAN": "NA",
        "AMERICANSTOCKEXCHANGE": "NA",
        "NYSEAMERICAN": "NA",
        "아멕스": "NA",
        "아메리칸": "NA",
        "ND": "ND",
        "NAS": "ND",
        "NASD": "ND",
        "NASDAQ": "ND",
        "NASDAQGS": "ND",
        "NASDAQGSM": "ND",
        "NASDAQGLOBALSELECT": "ND",
        "NASDAQGLOBALSELECTMARKET": "ND",
        "나스닥": "ND",
        "NY": "NY",
        "NYS": "NY",
        "NYSE": "NY",
        "NEWYORK": "NY",
        "NEWYORKSTOCKEXCHANGE": "NY",
        "뉴욕": "NY",
        "뉴욕증권거래소": "NY",
    }
    if normalized in aliases:
        return aliases[normalized]
    if "NASDAQ" in normalized or "나스닥" in normalized:
        return "ND"
    if "NYSE" in normalized or "NEWYORK" in normalized or "뉴욕" in normalized:
        return "NY"
    if "AMEX" in normalized or "AMERICAN" in normalized or "아멕스" in normalized:
        return "NA"
    return None


def map_holdings_for_order(data: dict[str, object], *, max_quantity: int | None = None) -> list[UsHoldingForOrder]:
    holdings: list[UsHoldingForOrder] = []
    for row in _result_rows(data):
        symbol = _safe_symbol(str(row.get("stk_code") or row.get("stk_cd") or row.get("symbol") or row.get("jmcode") or ""))
        quantity_field, quantity = _first_positive_int(
            row,
            "sell_alowq",
            "poss_qty",
            "sell_psbl_qty",
            "ord_psbl_qty",
            "rmnd_qty",
            "cur_qty",
            "hldg_qty",
            "jan_qty",
            "qty",
        )
        exchange_field, exchange, exchange_value = _exchange_for_order(row, "stex_tp", "stex_nm", "ovrs_excg_cd", "excg_cd", "exchange")
        price = _safe_float(row.get("now_pric") or row.get("cur_prc") or row.get("last") or row.get("evlt_pric"))
        blockers: list[str] = []
        if not symbol:
            blockers.append("SYMBOL_FIELD_MISSING")
        if quantity is None or quantity <= 0:
            blockers.append("QUANTITY_FIELD_MISSING")
        if exchange is None and exchange_field:
            blockers.append("UNSUPPORTED_EXCHANGE_VALUE")
        elif exchange is None:
            blockers.append("EXCHANGE_FIELD_MISSING")
        if max_quantity is not None and quantity is not None and quantity > max_quantity:
            blockers.append("MAX_ORDER_QUANTITY_EXCEEDED")
        if symbol and quantity and quantity > 0:
            holdings.append(
                UsHoldingForOrder(
                    symbol=symbol,
                    exchange=exchange,
                    sellableQuantity=quantity,
                    price=price,
                    rawQuantityField=quantity_field,
                    rawExchangeField=exchange_field,
                    rawExchangeValue=exchange_value,
                    blockedReasons=_dedupe_reasons(blockers),
                )
            )
    return holdings


class UsAccountService:
    async def get_cash(self) -> UsReadOnlyTrSummary:
        return _summary(await self._execute("ust21110"))

    async def get_valuation(self) -> UsReadOnlyTrSummary:
        return _summary(await self._execute("ust21120"))

    async def get_holdings(self, exchange: str = "", symbol: str = "") -> UsReadOnlyTrSummary:
        clean_exchange = exchange if exchange in {"ND", "NY", "NA"} else ""
        body = {
            "stex_tp": clean_exchange,
            "stk_cd": _safe_symbol(symbol) if symbol else "",
        }
        return _summary(await self._execute("ust21070", body))

    async def get_current_quote(self, exchange: str, symbol: str) -> UsReadOnlyTrSummary:
        clean_exchange = exchange if exchange in {"ND", "NY", "NA"} else "ND"
        clean_symbol = _safe_symbol(symbol)
        if not clean_symbol:
            raise KiwoomUsTransportError("usa10100", "400", "US quote symbol is required")
        return _summary(await self._execute("usa10100", {"stex_tp": clean_exchange, "stk_cd": clean_symbol}))

    async def get_holdings_for_order(self, *, max_quantity: int | None = None) -> list[UsHoldingForOrder]:
        summary = await self.get_holdings()
        return map_holdings_for_order(summary.data, max_quantity=max_quantity)

    async def get_realized_pnl(self, fc_krw_tp: str = "1") -> UsReadOnlyTrSummary:
        try:
            return _summary(await self._execute("ust21630", {"fc_krw_tp": fc_krw_tp}))
        except KiwoomUsTransportError as exc:
            if str(exc.return_code) == "20":
                mark_success()
                return _summary(_empty_response("ust21630", str(exc.return_code), str(exc.return_msg)))
            raise

    async def get_period_return(self, from_date: str | None = None, to_date: str | None = None) -> UsReadOnlyTrSummary:
        start, end = _date_range(from_date, to_date)
        try:
            return _summary(await self._execute("ust21650", {"fr_dt": start, "to_dt": end}))
        except KiwoomUsTransportError as exc:
            if str(exc.return_code) == "20":
                mark_success()
                return _summary(_empty_response("ust21650", str(exc.return_code), str(exc.return_msg)))
            raise

    async def get_daily_returns(self, from_date: str | None = None, to_date: str | None = None) -> UsDailyAccountReturnSummary:
        start, end = _date_range(from_date, to_date)
        response = await self._execute("usa21670", {"from": start, "to": end})
        mapped = map_daily_account_return_response(
            {
                "return_code": response.return_code,
                "return_msg": response.return_msg,
                **response.data,
            }
        )
        rows = [
            UsDailyAccountReturnRow(
                baseDate=row.base_dt,
                stockValuation=row.stk_evlta,
                profitLossAmount=row.pl_amt,
                dividendAmount=row.dvid_amt,
                commissionAndTax=row.cmsn_tax,
                accumulatedProfitLoss=row.acum_pl_amt,
                withdrawalAmount=row.pymn_amt,
                depositAsset=row.dast,
                overdueAmount=row.dly_amt,
                sellAmount=row.sell_amt,
                buyAmount=row.buy_amt,
                returnRate=row.prft_rt,
                foreignStockOutboundAmount=row.frgn_stk_outq_amt,
                foreignStockInboundAmount=row.frgn_stk_inq_amt,
                depositAmount=row.ina_amt,
                exchangeRate=row.exrt,
                unknownFields=row.unknown_fields,
            )
            for row in mapped.rows
        ]
        return UsDailyAccountReturnSummary(
            trId=mapped.tr_id,
            returnCode=response.return_code,
            returnMessage=response.return_msg,
            schemaKeys=sorted(response.data.keys()),
            rows=rows,
            source="kiwoom-us-readonly-usa21670",
            updatedAt=now_iso(),
        )

    async def get_today_order_fills(self, *, symbol: str | None = None, exchange: str | None = None, side: str = "0") -> UsReadOnlyTrSummary:
        body: dict[str, object] = {
            "slby_tp": side if side in {"0", "1", "2"} else "0",
            "stex_tp": exchange if exchange in {"NA", "ND", "NY"} else "",
            "stk_cd": _safe_symbol(symbol) if symbol else "",
        }
        return _summary(await self._execute_all("ust21510", body))

    async def get_open_orders(self, *, symbol: str | None = None, side: str = "0") -> UsReadOnlyTrSummary:
        body: dict[str, object] = {
            "ord_dt": "",
            "slby_tp": side if side in {"0", "1", "2"} else "0",
            "stk_code": _safe_symbol(symbol) if symbol else "",
        }
        try:
            return _summary(await self._execute_all("ust21050", body))
        except KiwoomUsTransportError as exc:
            if str(exc.return_code) == "20":
                mark_success()
                return _summary(_empty_response("ust21050", str(exc.return_code), str(exc.return_msg)))
            raise

    async def _execute(
        self,
        tr_id: str,
        body: dict[str, object] | None = None,
        *,
        cont_yn: str = "N",
        next_key: str = "",
    ) -> UsReadOnlyTrResponse:
        client = self._live_client()
        response = client.execute_readonly_tr(
            tr_id,
            body or {},
            cont_yn=cont_yn,
            next_key=next_key,
        )
        mark_success()
        return response

    async def _execute_all(
        self,
        tr_id: str,
        body: dict[str, object] | None = None,
        *,
        max_pages: int = US_READONLY_MAX_CONTINUATION_PAGES,
        page_delay_seconds: float = 0.0,
        require_complete: bool = True,
    ) -> UsReadOnlyTrResponse:
        page_limit = max(1, min(int(max_pages), US_READONLY_MAX_CONTINUATION_PAGES))
        page_delay = max(0.0, min(float(page_delay_seconds), 5.0))
        first = await self._execute(tr_id, body or {})
        rows = _result_rows(first.data)
        row_ids = {_stable_row_identity(row) for row in rows}
        current = first
        page_count = 1
        seen_next_keys: set[str] = set()

        for _ in range(page_limit - 1):
            if str(getattr(current, "cont_yn", "N")).strip().upper() != "Y":
                break
            next_key = str(getattr(current, "next_key", "")).strip()
            if not next_key or next_key in seen_next_keys:
                raise UsReadOnlyConfigurationError(
                    f"{tr_id} continuation metadata is incomplete"
                )
            seen_next_keys.add(next_key)
            if page_delay:
                await asyncio.sleep(page_delay)
            current = await self._execute(
                tr_id,
                body or {},
                cont_yn="Y",
                next_key=next_key,
            )
            page_count += 1
            for row in _result_rows(current.data):
                identity = _stable_row_identity(row)
                if identity in row_ids:
                    continue
                row_ids.add(identity)
                rows.append(row)
        else:
            if require_complete and str(getattr(current, "cont_yn", "N")).strip().upper() == "Y":
                raise UsReadOnlyConfigurationError(
                    f"{tr_id} continuation page limit exceeded ({page_limit})"
                )

        data = dict(first.data)
        data.pop("result_lsit", None)
        data["result_list"] = rows
        return UsReadOnlyTrResponse(
            tr_id=first.tr_id,
            return_code=first.return_code,
            return_msg=first.return_msg,
            data=data,
            unknown_fields=data,
            cont_yn=str(getattr(current, "cont_yn", "N") or "N"),
            next_key=str(getattr(current, "next_key", "") or ""),
            page_count=page_count,
        )

    def _live_client(self) -> KiwoomUsRestClientSkeleton:
        active_session = get_active_or_latest_kiwoom_session()
        if active_session is not None:
            transport = KiwoomUsHttpReadOnlyTransport(
                token_provider=lambda: active_session.access_token,
                sender=KiwoomUsUrllibHttpSender(
                    network_enabled=True,
                    confirm_phrase=US_READONLY_HTTP_SENDER_CONFIRM,
                ),
                base_url=active_session.base_url,
            )
            return KiwoomUsRestClientSkeleton(
                access_token_present=True,
                live_provider_enabled=True,
                read_only=True,
                order_enabled=False,
                transport=transport,
            )

        env = dict(os.environ)
        # This client is only used for read-only TR calls. Live order enablement
        # is handled separately by us_order_service and must not block quotes,
        # account reads, or chart/ranking TR requests.
        env["KIWOOM_US_ENABLE_ORDER"] = "false"
        env["KIWOOM_US_READ_ONLY"] = "true"
        credential_source = str(env.get("KIWOOM_US_CREDENTIAL_SOURCE", "")).strip().lower()
        if credential_source == "kiwoomcli":
            config = KiwoomUsCredentialConfig.from_kiwoomcli_profile(values=env)
        else:
            config = KiwoomUsCredentialConfig.from_mapping(env, source="env")
        config.require_token()
        transport = KiwoomUsHttpReadOnlyTransport(
            token_provider=lambda: config.token,
            sender=KiwoomUsUrllibHttpSender(
                network_enabled=_env_bool("KIWOOM_US_HTTP_SENDER_ENABLED", False),
                confirm_phrase=env.get("KIWOOM_US_HTTP_SENDER_CONFIRM"),
            ),
        )
        return KiwoomUsRestClientSkeleton(
            access_token_present=bool(config.token),
            live_provider_enabled=_env_bool("KIWOOM_US_LIVE_PROVIDER", False),
            read_only=config.read_only,
            order_enabled=config.order_enabled,
            transport=transport,
        )

us_account_service = UsAccountService()


US_READONLY_SERVICE_ERRORS = (
    UsReadOnlyConfigurationError,
    MissingCredentialError,
    KiwoomUsHttpSenderBlockedError,
    KiwoomUsHttpSenderError,
    KiwoomUsTransportError,
    UsMappingError,
)
