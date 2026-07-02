from typing import Literal

from pydantic import BaseModel


class Account(BaseModel):
    id: str
    broker: str
    label: str
    isDemo: bool
    maskedNumber: str


class ConnectionStatus(BaseModel):
    api: Literal["connected", "disconnected", "error"]
    websocket: Literal["connected", "connecting", "reconnecting", "disconnected"]
    mode: Literal["mock", "live"]
    lastUpdatedAt: str | None


class HealthStatus(BaseModel):
    ok: bool
    mode: Literal["mock", "live"]
    kiwoomConfigured: bool
    kiwoomMissing: list[str]
    readOnly: bool
    orderEnabled: bool
    lastUpdatedAt: str | None
    lastError: str | None
    connection: ConnectionStatus


class CashBalance(BaseModel):
    deposit: int
    orderableAmount: int
    withdrawableAmount: int
    updatedAt: str


class PerformancePosition(BaseModel):
    code: str
    name: str
    currentPrice: int
    avgPrice: int
    quantity: int
    purchaseAmount: int
    daySellPnl: int
    pnl: int
    pnlPct: float


class PerformanceSummary(BaseModel):
    totalPnl: int
    totalPnlPct: float
    positions: list[PerformancePosition]
    updatedAt: str
