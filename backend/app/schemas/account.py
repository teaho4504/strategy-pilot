from pydantic import BaseModel


class Account(BaseModel):
    id: str
    broker: str
    label: str
    isDemo: bool
    maskedNumber: str
    mode: str
    updatedAt: str


class CashBalance(BaseModel):
    cash: int
    withdrawableAmount: int
    orderableAmount: int
    source: str
    updatedAt: str


class PerformanceItem(BaseModel):
    code: str
    name: str
    quantity: int
    purchaseAmount: int
    currentPrice: int
    averagePrice: int
    valuationAmount: int
    profitLoss: int
    returnRate: float


class PerformanceSummary(BaseModel):
    accountId: str
    totalPurchaseAmount: int
    totalValuationAmount: int
    totalProfitLoss: int
    totalReturnRate: float
    items: list[PerformanceItem]
    source: str
    updatedAt: str
