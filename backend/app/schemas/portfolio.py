from pydantic import BaseModel, Field


class CurvePoint(BaseModel):
    t: str
    v: float


class PortfolioSnapshot(BaseModel):
    equity: int = Field(description="평가자산")
    cash: int = Field(description="현금 또는 예수금")
    dayPnl: int = Field(description="당일 손익")
    dayPnlPct: float = Field(description="당일 수익률")
    cumulativePnl: int = Field(description="누적 손익")
    cashRatio: float = Field(description="현금 비중, 0-1")
    intradayCurve: list[CurvePoint]
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


class MarketWatchlistResponse(BaseModel):
    indices: list[MarketIndex]
    watchlist: list[WatchTicker]
    updatedAt: str


class HealthResponse(BaseModel):
    status: str
    mode: str
    kiwoom: dict[str, str | bool | None]
    lastSuccessAt: str | None
    error: str | None
