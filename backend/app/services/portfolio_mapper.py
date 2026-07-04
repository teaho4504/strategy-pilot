from datetime import datetime, timezone
from typing import Any

from app.schemas.account import Account, AccountPerformance, Holding
from app.schemas.portfolio import MarketIndex, MarketWatchlistResponse, PortfolioSnapshot


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return int(value)
    cleaned = str(value).replace(",", "").replace("원", "").replace("+", "").strip()
    if cleaned in {"", "-"}:
        return default
    try:
        return int(float(cleaned))
    except ValueError:
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).replace(",", "").replace("%", "").replace("+", "").strip()
    if cleaned in {"", "-"}:
        return default
    try:
        return float(cleaned)
    except ValueError:
        return default


def _pick(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return default


def _extract_rows(page: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = [
        "acnt_prft_rt",
        "account_profit_rate",
        "output",
        "output1",
        "list",
        "items",
        "계좌수익률",
        "계좌수익률현황",
    ]
    for key in candidates:
        value = page.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    if all(isinstance(v, (str, int, float, type(None))) for v in page.values()):
        return [page]
    return []


def mask_account(account_no: str | None) -> str:
    if not account_no:
        return "****-**-mock"
    digits = account_no.replace("-", "")
    tail = digits[-4:] if len(digits) >= 4 else "****"
    return f"****-**-{tail}"


def mock_accounts() -> list[Account]:
    return [Account(id="acc-demo-1", broker="키움증권", label="데모계좌", isDemo=True, maskedNumber="****-**-1234")]


def mock_ka10085_pages() -> list[dict[str, Any]]:
    return [
        {
            "acnt_prft_rt": [
                {"stk_cd": "005930", "stk_nm": "삼성전자", "rmnd_qty": "20", "avg_prc": "70300", "cur_prc": "71800", "evlt_amt": "1436000", "evltv_prft": "30000", "prft_rt": "2.13"},
                {"stk_cd": "000660", "stk_nm": "SK하이닉스", "rmnd_qty": "4", "avg_prc": "194000", "cur_prc": "198500", "evlt_amt": "794000", "evltv_prft": "18000", "prft_rt": "2.32"},
                {"stk_cd": "034020", "stk_nm": "두산에너빌리티", "rmnd_qty": "15", "avg_prc": "20800", "cur_prc": "21350", "evlt_amt": "320250", "evltv_prft": "8250", "prft_rt": "2.64"},
            ]
        }
    ]


def map_ka10085_to_performance(pages: list[dict[str, Any]], source: str) -> AccountPerformance:
    updated_at = now_iso()
    rows: list[dict[str, Any]] = []
    for page in pages:
        rows.extend(_extract_rows(page))

    holdings: list[Holding] = []
    total_eval = 0
    total_purchase = 0
    total_pnl = 0

    for row in rows:
        code = str(_pick(row, "stk_cd", "code", "종목코드", default="")).replace("A", "")
        name = str(_pick(row, "stk_nm", "name", "종목명", default=code or "Unknown"))
        quantity = _to_int(_pick(row, "rmnd_qty", "qty", "quantity", "보유수량"))
        average_price = _to_int(_pick(row, "avg_prc", "avg_price", "averagePrice", "평균매입가"))
        current_price = _to_int(_pick(row, "cur_prc", "current_price", "currentPrice", "현재가"))
        valuation = _to_int(_pick(row, "evlt_amt", "valuationAmount", "평가금액"), quantity * current_price)
        pnl = _to_int(_pick(row, "evltv_prft", "pnl", "평가손익"), valuation - quantity * average_price)
        return_pct = _to_float(_pick(row, "prft_rt", "returnPct", "수익률"))

        total_eval += valuation
        total_purchase += quantity * average_price
        total_pnl += pnl
        holdings.append(
            Holding(
                code=code,
                name=name,
                quantity=quantity,
                averagePrice=average_price,
                currentPrice=current_price,
                valuationAmount=valuation,
                pnl=pnl,
                returnPct=return_pct,
                weightPct=0,
                updatedAt=updated_at,
            )
        )

    for holding in holdings:
        holding.weightPct = round((holding.valuationAmount / total_eval) * 100, 2) if total_eval else 0

    total_return_pct = round((total_pnl / total_purchase) * 100, 2) if total_purchase else 0
    return AccountPerformance(
        totalEvaluationAmount=total_eval,
        totalPurchaseAmount=total_purchase,
        totalPnl=total_pnl,
        totalReturnPct=total_return_pct,
        dayPnl=312_500 if source == "mock" else total_pnl,
        dayPnlPct=0.61 if source == "mock" else total_return_pct,
        holdings=holdings,
        source=source,
        updatedAt=updated_at,
    )


def portfolio_from_performance(performance: AccountPerformance) -> PortfolioSnapshot:
    cash = 18_420_000 if performance.source == "mock" else 0
    equity = performance.totalEvaluationAmount + cash
    curve = []
    base = equity - performance.dayPnl
    for i in range(38):
        hour = 9 + i // 6
        minute = (i % 6) * 10
        drift = (performance.dayPnl * (i + 1)) / 38
        wave = ((i % 7) - 3) * 8500
        curve.append({"t": f"{hour:02d}:{minute:02d}", "v": round((base + drift + wave) / 1_000_000, 3)})

    return PortfolioSnapshot(
        equity=equity,
        cash=cash,
        dayPnl=performance.dayPnl,
        dayPnlPct=performance.dayPnlPct,
        cumulativePnl=2_184_300 if performance.source == "mock" else performance.totalPnl,
        cashRatio=round(cash / equity, 3) if equity else 0,
        intradayCurve=curve,
        updatedAt=performance.updatedAt,
    )


def mock_market_watchlist() -> MarketWatchlistResponse:
    return MarketWatchlistResponse(
        indices=[
            MarketIndex(code="KOSPI", name="KOSPI", value=2684.21, changePct=0.42),
            MarketIndex(code="KOSDAQ", name="KOSDAQ", value=862.04, changePct=-0.31),
            MarketIndex(code="USDKRW", name="USD/KRW", value=1372.5, changePct=0.18),
        ],
        watchlist=[
            {"code": "005930", "name": "삼성전자", "price": 71800, "changePct": 0.84},
            {"code": "000660", "name": "SK하이닉스", "price": 198500, "changePct": 1.92},
            {"code": "035420", "name": "NAVER", "price": 184200, "changePct": -0.65},
        ],
        updatedAt=now_iso(),
    )
