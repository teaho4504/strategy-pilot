from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class UsReadOnlyTrSummary(BaseModel):
    trId: str
    returnCode: str
    returnMessage: str
    schemaKeys: list[str]
    data: dict[str, Any]
    normalized: dict[str, Any] | None = None
    source: str
    updatedAt: str


class UsHoldingForOrder(BaseModel):
    symbol: str
    exchange: str | None = None
    sellableQuantity: int
    price: float | None = None
    rawQuantityField: str | None = None
    rawExchangeField: str | None = None
    rawExchangeValue: str | None = None
    blockedReasons: list[str]


class UsDailyAccountReturnRow(BaseModel):
    baseDate: Optional[str] = None
    stockValuation: Optional[str] = None
    profitLossAmount: Optional[str] = None
    dividendAmount: Optional[str] = None
    commissionAndTax: Optional[str] = None
    accumulatedProfitLoss: Optional[str] = None
    withdrawalAmount: Optional[str] = None
    depositAsset: Optional[str] = None
    overdueAmount: Optional[str] = None
    sellAmount: Optional[str] = None
    buyAmount: Optional[str] = None
    returnRate: Optional[str] = None
    foreignStockOutboundAmount: Optional[str] = None
    foreignStockInboundAmount: Optional[str] = None
    depositAmount: Optional[str] = None
    exchangeRate: Optional[str] = None
    unknownFields: dict[str, Any]


class UsDailyAccountReturnSummary(BaseModel):
    trId: str
    returnCode: str
    returnMessage: str
    schemaKeys: list[str]
    rows: list[UsDailyAccountReturnRow]
    source: str
    updatedAt: str
