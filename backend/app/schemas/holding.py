from pydantic import BaseModel


class Holding(BaseModel):
    code: str
    name: str
    quantity: int
    avgPrice: int
    currentPrice: int
    marketValue: int
    pnl: int
    pnlPct: float
    weightPct: float
    updatedAt: str
