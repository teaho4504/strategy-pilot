from pydantic import BaseModel


class IntradayPoint(BaseModel):
    t: str
    v: int


class Portfolio(BaseModel):
    equity: int
    cash: int
    dayPnl: int
    dayPnlPct: float
    cumulativePnl: int
    cashRatio: float
    intradayCurve: list[IntradayPoint]
    source: str
    updatedAt: str


class Holding(BaseModel):
    code: str
    name: str
    quantity: int
    averagePrice: int
    currentPrice: int
    valuationAmount: int
    profitLoss: int
    returnRate: float
    weight: float
    updatedAt: str
