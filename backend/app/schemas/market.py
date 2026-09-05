from typing import Literal

from pydantic import BaseModel


class WatchTicker(BaseModel):
    code: str
    name: str
    price: int
    changePct: float


class MarketRankItem(BaseModel):
    rank: int
    code: str
    name: str
    price: float
    changeRate: float
    volume: int | None = None
    tradingValue: float | None = None
    exchange: str | None = None
    reason: str


class MarketRankingResponse(BaseModel):
    trId: str
    title: str
    market: str
    source: str
    updatedAt: str
    items: list[MarketRankItem]
    notes: list[str] = []


class UsQuoteResponse(BaseModel):
    trId: str = "usa10100"
    symbol: str
    exchange: str
    name: str | None = None
    price: float | None = None
    changeRate: float | None = None
    volume: int | None = None
    source: str = "kiwoom-us-security-info"
    updatedAt: str


class UsChartCandle(BaseModel):
    close: float
    volume: int
    open: float
    high: float
    low: float
    executedAt: str | None = None
    businessDate: str | None = None


class UsChartResponse(BaseModel):
    trId: str
    code: str
    exchange: str
    timeframe: str
    source: str
    updatedAt: str
    candles: list[UsChartCandle]
    continuationComplete: bool = True
    continuationPages: int = 1


class UsConditionItem(BaseModel):
    seq: str
    name: str


class UsConditionSearchMatch(BaseModel):
    code: str
    name: str | None = None
    exchange: str | None = None
    price: float | None = None
    changeRate: float | None = None
    volume: int | None = None


class UsConditionSearchResponse(BaseModel):
    source: str
    listTrId: str
    searchTrId: str
    realtimeTrId: str
    clearTrId: str
    updatedAt: str
    conditions: list[UsConditionItem]
    selectedSeq: str | None = None
    selectedName: str | None = None
    matches: list[UsConditionSearchMatch]
    schemaKeys: list[str]


class UsAutoTradeCriterion(BaseModel):
    key: str
    label: str
    status: str
    value: str | None = None
    reason: str


class UsAutoTradeOrderTicket(BaseModel):
    side: str
    exchange: str
    symbol: str
    quantity: int
    tradeType: str
    referencePrice: float
    targetProfitPct: float
    takeProfitPrice: float
    submitEndpoint: str
    submitBlocked: bool
    submitBlockReason: str | None = None


class UsAutoTradeProcessStep(BaseModel):
    step: str
    label: str
    status: str
    trId: str | None = None
    detail: str


class UsAutoTradePlanResponse(BaseModel):
    source: str
    strategy: str
    strategyName: str | None = None
    conditionSeq: str | None = None
    conditionName: str | None = None
    enabled: bool = True
    timeframe: str | None = None
    tickScope: str | None = None
    rankingTrId: str
    chartTrId: str
    orderPrecheckTrId: str
    updatedAt: str
    targetRank: int
    target: MarketRankItem | None = None
    criteria: list[UsAutoTradeCriterion]
    minPassedCriteria: int = 4
    passedCriteriaCount: int = 0
    criticalFailedCriteria: list[str] = []
    readyForEntry: bool
    stopLossPct: float = 2.0
    orderTicket: UsAutoTradeOrderTicket | None = None
    takeProfitOrderTicket: UsAutoTradeOrderTicket | None = None
    oneShareProcessReady: bool = False
    liveOrderBlockedReasons: list[str] = []
    processSteps: list[UsAutoTradeProcessStep] = []
    executionState: str
    nextAction: str


class UsAutoTradePlanListResponse(BaseModel):
    source: str
    updatedAt: str
    selectedStrategy: str | None = None
    plans: list[UsAutoTradePlanResponse]
    candidatePlans: list[UsAutoTradePlanResponse] = []


class UsRealtimeWindowItem(BaseModel):
    symbol: str
    tickCount: int
    orderbookCount: int
    latestPrice: float | None = None
    latestVolume: int | None = None
    volume10sDelta: int | None = None
    volume10sIncreasing: bool | None = None
    tradeStrength: float | None = None
    tradeStrengthIncreasing: bool | None = None
    bid: float | None = None
    ask: float | None = None
    spreadPct: float | None = None
    spreadWithin01Pct: bool | None = None
    lastEventAt: str | None = None
    sourceEventTime: str | None = None
    receiveDelayMs: int | None = None
    persistedEventCount: int = 0
    dbEvents10s: int = 0
    dbEvents1m: int = 0
    dbEvents5m: int = 0
    dbVolume10sDelta: int | None = None
    dbVolume1mDelta: int | None = None
    dbVolume5mDelta: int | None = None
    dbTradeStrength1mChange: float | None = None
    dbSpreadPct: float | None = None


class UsRealtimeWindowResponse(BaseModel):
    source: str
    channels: list[str]
    updatedAt: str
    monitorRunning: bool = False
    monitorConnected: bool = False
    monitoredSymbols: list[str] = []
    monitorLastError: str | None = None
    monitorLastConnectedAt: str | None = None
    monitorLastHeartbeatAt: str | None = None
    monitorReconnectCount: int = 0
    monitorNextRetrySeconds: int | None = None
    marketSession: str = "closed"
    qualityState: Literal["idle", "healthy", "degraded", "stale"] = "idle"
    expectedSymbolCount: int = 0
    freshSymbolCount: int = 0
    staleSymbolCount: int = 0
    missingSymbolCount: int = 0
    delayedSymbolCount: int = 0
    coveragePct: float = 0
    averageReceiveDelayMs: int | None = None
    maxReceiveDelayMs: int | None = None
    items: list[UsRealtimeWindowItem]
