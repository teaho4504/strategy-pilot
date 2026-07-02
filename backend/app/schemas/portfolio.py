from pydantic import BaseModel


class IntradayPoint(BaseModel):
    t: str
    v: float


class Portfolio(BaseModel):
    equity: int
    cash: int
    dayPnl: int
    dayPnlPct: float
    cumulativePnl: int
    cashRatio: float
    intradayCurve: list[IntradayPoint]
    updatedAt: str


class MarketIndex(BaseModel):
    code: str
    name: str
    value: float
    changePct: float


class WatchTicker(BaseModel):
    code: str
    name: str
    price: int
    changePct: float
    updatedAt: str
