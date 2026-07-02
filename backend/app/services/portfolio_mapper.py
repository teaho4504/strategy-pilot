from datetime import datetime, timezone
from typing import Any

from app.schemas.account import CashBalance, PerformancePosition, PerformanceSummary
from app.schemas.holding import Holding
from app.schemas.portfolio import IntradayPoint, Portfolio, WatchTicker


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_kiwoom_int(value: Any) -> int:
    if value is None:
        return 0
    text = str(value).strip().replace(",", "")
    if not text:
        return 0
    sign = -1 if text.startswith("-") else 1
    digits = text.lstrip("+-")
    if not digits:
        return 0
    try:
        return sign * int(float(digits))
    except ValueError:
        return 0


def parse_price(value: Any) -> int:
    return abs(parse_kiwoom_int(value))


def parse_float(value: Any) -> float:
    if value is None:
        return 0.0
    text = str(value).strip().replace(",", "")
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def clean_stock_code(value: Any) -> str:
    code = str(value or "").strip()
    if len(code) == 7 and code[0] in {"A", "J", "Q"}:
        return code[1:]
    return code


def mask_account_no(account_no: str) -> str:
    digits = "".join(ch for ch in account_no if ch.isdigit())
    if len(digits) <= 4:
        return "****"
    return f"****-**-{digits[-4:]}"


def map_cash(raw: dict[str, Any]) -> CashBalance:
    return CashBalance(
        deposit=parse_kiwoom_int(raw.get("entr")),
        orderableAmount=parse_kiwoom_int(raw.get("ord_alow_amt") or raw.get("ord_alowa")),
        withdrawableAmount=parse_kiwoom_int(raw.get("pymn_alow_amt")),
        updatedAt=now_iso(),
    )


def map_portfolio(account_eval: dict[str, Any], performance: dict[str, Any]) -> Portfolio:
    equity = parse_kiwoom_int(account_eval.get("aset_evlt_amt") or account_eval.get("prsm_dpst_aset_amt"))
    cash = parse_kiwoom_int(account_eval.get("entr"))
    day_pnl = parse_kiwoom_int(account_eval.get("tdy_lspft"))
    cumulative_pnl = parse_kiwoom_int(account_eval.get("lspft"))
    day_pnl_pct = parse_float(account_eval.get("tdy_lspft_rt"))
    cash_ratio = cash / equity if equity > 0 else 0
    timestamp = datetime.now(timezone.utc)

    # TODO: Official account snapshot TRs do not provide an intraday equity curve.
    # Persist snapshots in a database and hydrate this with historical points.
    return Portfolio(
        equity=equity,
        cash=cash,
        dayPnl=day_pnl,
        dayPnlPct=day_pnl_pct,
        cumulativePnl=cumulative_pnl,
        cashRatio=round(cash_ratio, 4),
        intradayCurve=[IntradayPoint(t=timestamp.strftime("%H:%M"), v=round(equity / 1_000_000, 2))],
        updatedAt=timestamp.isoformat(),
    )


def map_holdings(balance_raw: dict[str, Any], performance_raw: dict[str, Any]) -> list[Holding]:
    updated_at = now_iso()
    perf_by_code = {
        clean_stock_code(item.get("stk_cd")): item
        for item in performance_raw.get("acnt_prft_rt") or []
        if clean_stock_code(item.get("stk_cd"))
    }

    rows = balance_raw.get("stk_cntr_remn") or balance_raw.get("stk_acnt_evlt_prst") or []
    raw_holdings: list[dict[str, Any]] = []
    for row in rows:
        code = clean_stock_code(row.get("stk_cd"))
        perf = perf_by_code.get(code, {})
        quantity = parse_kiwoom_int(row.get("cur_qty") or row.get("rmnd_qty") or perf.get("rmnd_qty"))
        avg_price = parse_price(row.get("buy_uv") or row.get("avg_prc") or perf.get("pur_pric"))
        current_price = parse_price(row.get("cur_prc") or perf.get("cur_prc"))
        market_value = parse_kiwoom_int(row.get("evlt_amt")) or current_price * quantity
        pnl = parse_kiwoom_int(row.get("evltv_prft") or row.get("pl_amt"))
        if pnl == 0 and avg_price and quantity:
            pnl = market_value - (avg_price * quantity)
        pnl_pct = parse_float(row.get("pl_rt"))
        if pnl_pct == 0 and avg_price and quantity:
            basis = avg_price * quantity
            pnl_pct = (pnl / basis) * 100 if basis else 0
        raw_holdings.append({
            "code": code,
            "name": row.get("stk_nm") or perf.get("stk_nm") or code,
            "quantity": quantity,
            "avgPrice": avg_price,
            "currentPrice": current_price,
            "marketValue": market_value,
            "pnl": pnl,
            "pnlPct": round(pnl_pct, 4),
        })

    total_value = sum(item["marketValue"] for item in raw_holdings)
    return [
        Holding(
            **item,
            weightPct=round((item["marketValue"] / total_value) * 100, 4) if total_value else 0,
            updatedAt=updated_at,
        )
        for item in raw_holdings
    ]


def map_performance(raw: dict[str, Any]) -> PerformanceSummary:
    positions: list[PerformancePosition] = []
    total_purchase = 0
    total_pnl = 0

    for item in raw.get("acnt_prft_rt") or []:
        quantity = parse_kiwoom_int(item.get("rmnd_qty"))
        avg_price = parse_price(item.get("pur_pric"))
        current_price = parse_price(item.get("cur_prc"))
        purchase_amount = parse_kiwoom_int(item.get("pur_amt")) or avg_price * quantity
        market_value = current_price * quantity
        pnl = market_value - purchase_amount
        pnl_pct = (pnl / purchase_amount) * 100 if purchase_amount else 0
        total_purchase += purchase_amount
        total_pnl += pnl
        positions.append(
            PerformancePosition(
                code=clean_stock_code(item.get("stk_cd")),
                name=str(item.get("stk_nm") or ""),
                currentPrice=current_price,
                avgPrice=avg_price,
                quantity=quantity,
                purchaseAmount=purchase_amount,
                daySellPnl=parse_kiwoom_int(item.get("tdy_sel_pl")),
                pnl=pnl,
                pnlPct=round(pnl_pct, 4),
            )
        )

    return PerformanceSummary(
        totalPnl=total_pnl,
        totalPnlPct=round((total_pnl / total_purchase) * 100, 4) if total_purchase else 0,
        positions=positions,
        updatedAt=now_iso(),
    )


def map_watch_ticker(raw: dict[str, Any]) -> WatchTicker:
    return WatchTicker(
        code=clean_stock_code(raw.get("stk_cd")),
        name=str(raw.get("stk_nm") or raw.get("stk_cd") or ""),
        price=parse_price(raw.get("cur_prc")),
        changePct=parse_float(raw.get("flu_rt")),
        updatedAt=now_iso(),
    )
