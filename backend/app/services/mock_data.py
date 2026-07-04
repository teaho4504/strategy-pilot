from datetime import datetime, timezone

from app.schemas.account import Account, CashBalance, PerformanceItem, PerformanceSummary
from app.schemas.market import WatchTicker
from app.schemas.portfolio import Holding, IntradayPoint, Portfolio


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def mock_accounts() -> list[Account]:
    return [
        Account(
            id="demo-kiwoom-001",
            broker="키움증권",
            label="데모계좌",
            isDemo=True,
            maskedNumber="****-**-1234",
            mode="mock",
            updatedAt=now_iso(),
        )
    ]


def mock_portfolio() -> Portfolio:
    return Portfolio(
        equity=52_184_300,
        cash=18_420_000,
        dayPnl=312_500,
        dayPnlPct=0.61,
        cumulativePnl=2_184_300,
        cashRatio=0.35,
        intradayCurve=[
            IntradayPoint(t="09:00", v=51_820_000),
            IntradayPoint(t="10:00", v=52_040_000),
            IntradayPoint(t="11:00", v=52_110_000),
            IntradayPoint(t="12:00", v=51_980_000),
            IntradayPoint(t="13:00", v=52_160_000),
            IntradayPoint(t="14:00", v=52_255_000),
            IntradayPoint(t="15:00", v=52_184_300),
        ],
        source="mock",
        updatedAt=now_iso(),
    )


def mock_cash_balance() -> CashBalance:
    return CashBalance(
        cash=18_420_000,
        withdrawableAmount=11_230_000,
        orderableAmount=12_550_000,
        source="mock",
        updatedAt=now_iso(),
    )


def mock_holdings() -> list[Holding]:
    updated_at = now_iso()
    return [
        Holding(
            code="005930",
            name="삼성전자",
            quantity=20,
            averagePrice=71_350,
            currentPrice=71_800,
            valuationAmount=1_436_000,
            profitLoss=9_000,
            returnRate=0.63,
            weight=0.0275,
            updatedAt=updated_at,
        ),
        Holding(
            code="000660",
            name="SK하이닉스",
            quantity=4,
            averagePrice=195_200,
            currentPrice=198_500,
            valuationAmount=794_000,
            profitLoss=13_200,
            returnRate=1.69,
            weight=0.0152,
            updatedAt=updated_at,
        ),
    ]


def mock_performance() -> PerformanceSummary:
    holdings = mock_holdings()
    items = [
        PerformanceItem(
            code=item.code,
            name=item.name,
            quantity=item.quantity,
            purchaseAmount=item.averagePrice * item.quantity,
            currentPrice=item.currentPrice,
            averagePrice=item.averagePrice,
            valuationAmount=item.valuationAmount,
            profitLoss=item.profitLoss,
            returnRate=item.returnRate,
        )
        for item in holdings
    ]
    purchase = sum(item.purchaseAmount for item in items)
    valuation = sum(item.valuationAmount for item in items)
    pnl = valuation - purchase
    rate = round((pnl / purchase) * 100, 4) if purchase else 0.0
    return PerformanceSummary(
        accountId="demo-kiwoom-001",
        totalPurchaseAmount=purchase,
        totalValuationAmount=valuation,
        totalProfitLoss=pnl,
        totalReturnRate=rate,
        items=items,
        source="mock",
        updatedAt=now_iso(),
    )


def mock_watchlist() -> list[WatchTicker]:
    return [
        WatchTicker(code="005930", name="삼성전자", price=71_800, changePct=0.84),
        WatchTicker(code="000660", name="SK하이닉스", price=198_500, changePct=1.92),
        WatchTicker(code="035420", name="NAVER", price=184_200, changePct=-0.65),
    ]
