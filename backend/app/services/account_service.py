from __future__ import annotations

from app.core.config import get_settings
from app.schemas.account import Account, CashBalance, PerformanceItem, PerformanceSummary
from app.schemas.portfolio import Holding, Portfolio
from app.services.kiwoom_client import kiwoom_client
from app.services.mock_data import mock_accounts, mock_cash_balance, mock_holdings, mock_performance, mock_portfolio, now_iso
from app.services.runtime_state import mark_success


class MapperValidationError(ValueError):
    def __init__(self, mapper_name: str, missing_fields: list[str]) -> None:
        self.mapper_name = mapper_name
        self.missing_fields = missing_fields
        super().__init__(f"{mapper_name} mapper missing required fields: {', '.join(missing_fields)}")


def _has_value(body: dict[str, object], key: str) -> bool:
    value = body.get(key)
    return value is not None and str(value).strip() != ""


def _require_fields(mapper_name: str, body: dict[str, object], fields: list[str]) -> None:
    missing = [field for field in fields if not _has_value(body, field)]
    if missing:
        raise MapperValidationError(mapper_name, missing)


def _require_one_of(mapper_name: str, body: dict[str, object], field_group: list[str]) -> None:
    if not any(_has_value(body, field) for field in field_group):
        raise MapperValidationError(mapper_name, ["|".join(field_group)])


def parse_int(value: object) -> int:
    if value is None:
        return 0
    text = str(value).strip().replace(",", "")
    if not text:
        return 0
    sign = -1 if text.startswith("-") else 1
    digits = "".join(ch for ch in text if ch.isdigit())
    return sign * int(digits or "0")


def parse_float(value: object) -> float:
    if value is None:
        return 0.0
    text = str(value).strip().replace(",", "")
    try:
        return float(text)
    except ValueError:
        return 0.0


def clean_code(value: object) -> str:
    text = str(value or "").strip()
    return text[1:] if text.startswith("A") else text


def map_account_response(body: dict[str, object]) -> Account:
    _require_fields("ka00001", body, ["acctNo"])
    has_account = bool(body.get("acctNo"))
    return Account(
        id="kiwoom-live-readonly",
        broker="키움증권",
        label="실계좌 조회 전용",
        isDemo=False,
        maskedNumber="configured" if has_account else "unavailable",
        mode="live",
        updatedAt=now_iso(),
    )


def map_cash_response(body: dict[str, object], source: str = "kiwoom-live-readonly-kt00001") -> CashBalance:
    _require_fields("kt00001", body, ["entr"])
    _require_one_of("kt00001", body, ["pymn_alow_amt", "wdra_alow_amt"])
    _require_one_of("kt00001", body, ["ord_alow_amt", "ord_alowa"])
    return CashBalance(
        cash=parse_int(body.get("entr")),
        withdrawableAmount=parse_int(body.get("pymn_alow_amt") or body.get("wdra_alow_amt")),
        orderableAmount=parse_int(body.get("ord_alow_amt") or body.get("ord_alowa")),
        source=source,
        updatedAt=now_iso(),
    )


def map_portfolio_response(
    body: dict[str, object],
    cash: int,
    source: str = "kiwoom-live-readonly-kt00004",
) -> Portfolio:
    _require_one_of("kt00004", body, ["aset_evlt_amt", "prsm_dpst_aset_amt"])
    _require_fields("kt00004", body, ["tdy_lspft", "lspft"])
    equity = parse_int(body.get("aset_evlt_amt") or body.get("prsm_dpst_aset_amt"))
    day_pnl = parse_int(body.get("tdy_lspft"))
    cumulative_pnl = parse_int(body.get("lspft"))
    return Portfolio(
        equity=equity,
        cash=cash,
        dayPnl=day_pnl,
        dayPnlPct=parse_float(body.get("tdy_lspft_rt")),
        cumulativePnl=cumulative_pnl,
        cashRatio=round(cash / equity, 4) if equity else 0.0,
        intradayCurve=mock_portfolio().intradayCurve,
        source=source,
        updatedAt=now_iso(),
    )


def map_holdings_response(rows: list[dict[str, object]]) -> list[Holding]:
    for row in rows:
        _require_fields("kt00005", row, ["stk_cd", "stk_nm", "cur_prc", "evlt_amt"])
        _require_one_of("kt00005", row, ["cur_qty", "rmnd_qty"])
        _require_one_of("kt00005", row, ["buy_uv", "avg_prc"])
    total = sum(parse_int(row.get("evlt_amt")) for row in rows)
    holdings: list[Holding] = []
    for row in rows:
        valuation = parse_int(row.get("evlt_amt"))
        holdings.append(
            Holding(
                code=clean_code(row.get("stk_cd")),
                name=str(row.get("stk_nm") or ""),
                quantity=parse_int(row.get("cur_qty") or row.get("rmnd_qty")),
                averagePrice=parse_int(row.get("buy_uv") or row.get("avg_prc")),
                currentPrice=parse_int(row.get("cur_prc")),
                valuationAmount=valuation,
                profitLoss=parse_int(row.get("evltv_prft") or row.get("pl_amt")),
                returnRate=parse_float(row.get("pl_rt")),
                weight=round(valuation / total, 4) if total else 0.0,
                updatedAt=now_iso(),
            )
        )
    return holdings


def map_performance_response(rows: list[dict[str, object]]) -> PerformanceSummary:
    items: list[PerformanceItem] = []
    for row in rows:
        _require_fields("ka10085", row, ["stk_cd", "stk_nm", "cur_prc"])
        _require_one_of("ka10085", row, ["rmnd_qty", "quantity"])
        _require_one_of("ka10085", row, ["pur_pric", "averagePrice"])
        _require_one_of("ka10085", row, ["pur_amt", "purchaseAmount"])
        quantity = parse_int(row.get("rmnd_qty") or row.get("quantity"))
        average = parse_int(row.get("pur_pric") or row.get("averagePrice"))
        current = parse_int(row.get("cur_prc") or row.get("currentPrice"))
        purchase = parse_int(row.get("pur_amt") or row.get("purchaseAmount") or average * quantity)
        valuation = current * quantity
        pnl = valuation - purchase
        rate = round((pnl / purchase) * 100, 4) if purchase else 0.0
        items.append(
            PerformanceItem(
                code=clean_code(row.get("stk_cd") or row.get("code")),
                name=str(row.get("stk_nm") or row.get("name") or ""),
                quantity=quantity,
                purchaseAmount=purchase,
                currentPrice=current,
                averagePrice=average,
                valuationAmount=valuation,
                profitLoss=pnl,
                returnRate=rate,
            )
        )
    purchase_total = sum(item.purchaseAmount for item in items)
    valuation_total = sum(item.valuationAmount for item in items)
    pnl_total = valuation_total - purchase_total
    return PerformanceSummary(
        accountId="kiwoom-live-readonly",
        totalPurchaseAmount=purchase_total,
        totalValuationAmount=valuation_total,
        totalProfitLoss=pnl_total,
        totalReturnRate=round((pnl_total / purchase_total) * 100, 4) if purchase_total else 0.0,
        items=items,
        source="kiwoom-live-readonly-ka10085",
        updatedAt=now_iso(),
    )


class AccountService:
    async def get_accounts(self) -> list[Account]:
        settings = get_settings()
        if settings.kiwoom_mode != "live":
            mark_success()
            return mock_accounts()
        response = await kiwoom_client.request_tr("ka00001")
        mark_success()
        return [map_account_response(response.body)]

    async def get_cash(self) -> CashBalance:
        settings = get_settings()
        if settings.kiwoom_mode != "live":
            mark_success()
            return mock_cash_balance()
        response = await kiwoom_client.request_tr("kt00001", {"qry_tp": settings.kiwoom_cash_qry_tp})
        mark_success()
        return map_cash_response(response.body)

    async def get_portfolio(self) -> Portfolio:
        settings = get_settings()
        if settings.kiwoom_mode != "live":
            mark_success()
            return mock_portfolio()
        response = await kiwoom_client.request_tr(
            "kt00004",
            {"qry_tp": settings.kiwoom_portfolio_qry_tp, "dmst_stex_tp": settings.kiwoom_dmst_stex_tp},
        )
        cash_response = await kiwoom_client.request_tr("kt00001", {"qry_tp": settings.kiwoom_cash_qry_tp})
        mark_success()
        return map_portfolio_response(response.body, parse_int(cash_response.body.get("entr")))

    async def get_holdings(self) -> list[Holding]:
        settings = get_settings()
        if settings.kiwoom_mode != "live":
            mark_success()
            return mock_holdings()
        response = await kiwoom_client.request_tr_all("kt00005", {"dmst_stex_tp": settings.kiwoom_dmst_stex_tp})
        rows = response.body.get("stk_cntr_remn") or []
        mark_success()
        return map_holdings_response(rows)

    async def get_performance(self) -> PerformanceSummary:
        settings = get_settings()
        if settings.kiwoom_mode != "live":
            mark_success()
            return mock_performance()
        response = await kiwoom_client.request_tr_all("ka10085", {"stex_tp": settings.kiwoom_stex_tp})
        rows = response.body.get("acnt_prft_rt") or []
        mark_success()
        return map_performance_response(rows)


account_service = AccountService()
