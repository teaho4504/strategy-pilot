from pydantic import BaseModel, Field


class Account(BaseModel):
    id: str
    broker: str
    label: str
    isDemo: bool
    maskedNumber: str


class Holding(BaseModel):
    code: str = Field(description="종목코드")
    name: str = Field(description="종목명")
    quantity: int = Field(description="보유수량")
    averagePrice: int = Field(description="평균 매입가")
    currentPrice: int = Field(description="현재가")
    valuationAmount: int = Field(description="평가금액")
    pnl: int = Field(description="평가손익")
    returnPct: float = Field(description="수익률")
    weightPct: float = Field(description="포트폴리오 비중")
    updatedAt: str


class AccountPerformance(BaseModel):
    totalEvaluationAmount: int
    totalPurchaseAmount: int
    totalPnl: int
    totalReturnPct: float
    dayPnl: int
    dayPnlPct: float
    holdings: list[Holding]
    source: str
    updatedAt: str
