from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.market import UsAutoTradePlanResponse, UsConditionSearchMatch


UsOrderSide = Literal["buy", "sell"]
UsOrderTradeType = Literal["00", "03", "26", "27", "30", "36", "37"]


class UsOrderRequest(BaseModel):
    side: UsOrderSide
    exchange: Literal["NA", "ND", "NY"] = "ND"
    symbol: str = Field(min_length=1, max_length=12)
    quantity: int = Field(gt=0, le=100_000)
    orderPrice: str = Field(default="", max_length=12)
    referencePrice: str = Field(default="", max_length=12)
    tradeType: UsOrderTradeType = "03"
    confirmText: str = Field(default="", max_length=80)
    reason: str | None = Field(default=None, max_length=200)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        cleaned = "".join(ch for ch in value.upper().strip() if ch.isalnum() or ch in {".", "-"})
        if not cleaned:
            raise ValueError("symbol is required")
        return cleaned[:12]

    @field_validator("orderPrice")
    @classmethod
    def validate_order_price(cls, value: str) -> str:
        cleaned = str(value).strip()
        if cleaned and not cleaned.replace(".", "", 1).isdigit():
            raise ValueError("orderPrice must be numeric")
        return cleaned

    @field_validator("referencePrice")
    @classmethod
    def validate_reference_price(cls, value: str) -> str:
        cleaned = str(value).strip()
        if cleaned and not cleaned.replace(".", "", 1).isdigit():
            raise ValueError("referencePrice must be numeric")
        return cleaned

    @model_validator(mode="after")
    def validate_price_required(self) -> "UsOrderRequest":
        if self.tradeType in {"00", "30"} and not self.orderPrice:
            raise ValueError("orderPrice is required for limit/LOC orders")
        return self


class UsOrderResponse(BaseModel):
    trId: str
    side: UsOrderSide
    code: str
    exchange: str
    returnCode: str
    returnMessage: str
    orderNo: str | None = None
    stockName: str | None = None
    source: str
    updatedAt: str


class UsOrderHistoryItem(BaseModel):
    id: int
    trId: str
    side: UsOrderSide
    code: str
    exchange: str
    quantity: int
    orderPrice: str
    referencePrice: str | None = None
    tradeType: str
    strategy: str | None = None
    reason: str | None = None
    returnCode: str
    returnMessage: str
    orderNo: str | None = None
    createdAt: str


class UsStrategyPnlSnapshot(BaseModel):
    strategy: str
    symbol: str
    tradeDate: str
    actualPnl: float
    fillCount: int
    realizedQuantity: int
    buyQuantity: int
    sellQuantity: int
    source: str
    updatedAt: str


class UsStrategyPnlSummary(BaseModel):
    rows: list[UsStrategyPnlSnapshot]
    trId: str
    refreshed: bool
    warning: str | None = None
    source: str
    updatedAt: str


class UsAutoTradeEventItem(BaseModel):
    id: int
    action: str
    status: str
    strategy: str | None = None
    symbol: str | None = None
    exchange: str | None = None
    side: UsOrderSide | None = None
    trId: str | None = None
    sourceOrderId: int | None = None
    blockedReasons: list[str]
    createdAt: str


class UsObservationCriterionCount(BaseModel):
    criterion: str
    count: int


class UsObservationStrategyStats(BaseModel):
    strategy: str
    stateChanges: int
    readyChanges: int
    waitingChanges: int
    uniqueCandidateCount: int
    topFailedCriteria: list[UsObservationCriterionCount]
    lastChangedAt: str | None = None


class UsObservationStatsResponse(BaseModel):
    strategies: list[UsObservationStrategyStats]
    totalStateChanges: int
    source: str
    updatedAt: str


class UsLiquidationHoldingItem(BaseModel):
    symbol: str
    exchange: str | None = None
    quantity: int
    price: float | None = None
    rawQuantityField: str | None = None
    rawExchangeField: str | None = None
    rawExchangeValue: str | None = None
    blockedReasons: list[str]


class UsLiquidationPlanResponse(BaseModel):
    enabled: bool
    action: str
    holdings: list[UsLiquidationHoldingItem]
    executableCount: int
    totalCount: int
    blockedReasons: list[str]
    source: str
    updatedAt: str


class UsLiquidationExecuteResponse(BaseModel):
    enabled: bool
    action: str
    submitted: list[UsOrderResponse]
    skipped: list[UsLiquidationHoldingItem]
    blockedReasons: list[str]
    source: str
    updatedAt: str


class UsTakeProfitPlanResponse(BaseModel):
    hasOpenBuy: bool
    sourceOrderId: int | None = None
    symbol: str | None = None
    exchange: str | None = None
    quantity: int | None = None
    entryReferencePrice: float | None = None
    actualFillPrice: float | None = None
    filledQuantity: int | None = None
    fillStatus: str | None = None
    fillTrId: str | None = None
    targetProfitPct: float
    targetPrice: float | None = None
    sellTradeType: UsOrderTradeType
    submitEndpoint: str
    precheck: UsOrderPrecheckResponse | None = None
    blockedReasons: list[str]
    source: str
    updatedAt: str


class UsTakeProfitMonitorResponse(BaseModel):
    hasOpenBuy: bool
    sourceOrderId: int | None = None
    symbol: str | None = None
    exchange: str | None = None
    quantity: int | None = None
    targetProfitPct: float
    entryReferencePrice: float | None = None
    actualFillPrice: float | None = None
    targetPrice: float | None = None
    stopLossPct: float
    stopLossPrice: float | None = None
    latestPrice: float | None = None
    targetReached: bool
    stopLossTriggered: bool
    spreadToTargetPct: float | None = None
    spreadToStopLossPct: float | None = None
    exitReason: str | None = None
    quoteTrId: str | None = None
    sellTicketReady: bool
    blockedReasons: list[str]
    source: str
    updatedAt: str


class UsAutoExitTickResponse(BaseModel):
    enabled: bool
    action: str
    monitoredPositionCount: int = 0
    sourceOrderId: int | None = None
    exitOrderNo: str | None = None
    exitReason: str | None = None
    trId: str | None = None
    symbol: str | None = None
    exchange: str | None = None
    quantity: int | None = None
    latestPrice: float | None = None
    targetPrice: float | None = None
    stopLossPrice: float | None = None
    retryPlanned: bool = False
    retryCount: int = 0
    warning: str | None = None
    blockedReasons: list[str]
    source: str
    updatedAt: str


class UsAutoEntryTickResponse(BaseModel):
    enabled: bool
    action: str
    strategy: str
    allocationCycleId: int | None = None
    allocationReservationId: int | None = None
    positionSlot: int | None = None
    tranche: int | None = None
    reservedNotional: float | None = None
    remainingCash: float | None = None
    symbol: str | None = None
    exchange: str | None = None
    quantity: int | None = None
    referencePrice: float | None = None
    trId: str | None = None
    entryOrderNo: str | None = None
    targetProfitPct: float | None = None
    takeProfitPrice: float | None = None
    failedCriteria: list[str] = Field(default_factory=list)
    blockedReasons: list[str]
    source: str
    updatedAt: str


class UsAutoTradeRuntimeStatus(BaseModel):
    enabled: bool
    observationEnabled: bool = False
    mode: str
    entryConfirmBypassEnabled: bool
    autoExitEnabled: bool
    runnerEnabled: bool = False
    runnerRunning: bool = False
    runnerMode: str = "off"
    runnerIntervalSeconds: float = 5.0
    runnerStartedAt: str | None = None
    runnerLastTickAt: str | None = None
    runnerLastError: str | None = None
    runnerTickCount: int = 0
    runnerLastObservationAction: str | None = None
    runnerLastObservationStrategy: str | None = None
    runnerLastObservationSymbol: str | None = None
    runnerLastObservationExchange: str | None = None
    runnerLastObservationBlockedReasons: list[str] = Field(default_factory=list)
    runnerLastObservationFailedCriteria: list[str] = Field(default_factory=list)
    runnerLastObservationAt: str | None = None
    startedAt: str | None = None
    stoppedAt: str | None = None
    maxOrderQuantity: int
    maxOrderNotional: float
    capitalUsagePct: float = 100.0
    blockedReasons: list[str]
    source: str
    updatedAt: str


class UsAutoTradeStrategyToggleRequest(BaseModel):
    enabled: bool


class UsAutoTradeStrategyStatusItem(BaseModel):
    strategy: str
    strategyName: str
    enabled: bool
    conditionSeq: str | None = None
    conditionName: str | None = None
    conditionConnected: bool = False
    conditionMatchCount: int = 0
    conditionMatches: list[UsConditionSearchMatch] = Field(default_factory=list)
    conditionError: str | None = None


class UsAutoTradeStrategyStatusResponse(BaseModel):
    strategies: list[UsAutoTradeStrategyStatusItem]
    source: str
    updatedAt: str


class UsAutoTradePipelineSnapshot(BaseModel):
    todayDate: str
    ordersToday: int
    eventsToday: int
    realtimeEventsToday: int
    latestOrderAt: str | None = None
    latestEventAt: str | None = None
    latestRealtimeAt: str | None = None
    latestEventAction: str | None = None
    latestEventStatus: str | None = None
    dataFlowOk: bool
    orderFlowOk: bool
    runnerHealthy: bool
    warning: str | None = None


class UsAutoTradeDiagnosticsResponse(BaseModel):
    decision: str
    canAttemptEntry: bool
    canAttemptExit: bool
    blockingStage: str | None = None
    blockerReasons: list[str]
    requiredAction: str
    status: UsAutoTradeRuntimeStatus
    pipeline: UsAutoTradePipelineSnapshot
    plan: UsAutoTradePlanResponse | None = None
    latestEvent: UsAutoTradeEventItem | None = None
    planError: str | None = None
    source: str
    updatedAt: str


class UsOrderStatus(BaseModel):
    orderEnabled: bool
    readOnly: bool
    runtimeOrderLocked: bool
    sessionPresent: bool
    sessionMode: str | None = None
    accountLabel: str | None = None
    liveOrderConfirmConfigured: bool
    liveOrderUnlockConfigured: bool
    requiredConfirmText: str
    requiredUnlockText: str
    allowedExchanges: list[str]
    allowedTradeTypes: list[str]
    allowedSymbols: list[str]
    maxOrderQuantity: int
    maxOrderNotional: float
    capitalUsagePct: float = 100.0
    blockedReasons: list[str]
    readinessChecklist: list[dict[str, str | bool]]
    source: str
    updatedAt: str


class UsOrderStateMonitorStatus(BaseModel):
    enabled: bool
    running: bool
    connected: bool
    monitoredSymbolCount: int
    channels: list[str]
    lastEventAt: str | None = None
    lastConnectedAt: str | None = None
    lastHeartbeatAt: str | None = None
    lastError: str | None = None
    lastReconcileError: str | None = None
    reconnectCount: int
    nextRetrySeconds: int | None = None
    updatedCount: int
    duplicateCount: int
    source: str
    updatedAt: str


class UsOrderStateMonitorPreflight(BaseModel):
    readyForObservation: bool
    observationState: Literal["no_target", "blocked", "ready"]
    requiredActionCode: str
    monitorConfigured: bool
    sessionPresent: bool
    sessionValid: bool
    runtimeOrderLocked: bool
    submittedReservationCount: int
    eligibleSymbolCount: int
    channels: list[str]
    blockerReasons: list[str]
    source: str
    updatedAt: str


class UsOrderRuntimeLockResponse(BaseModel):
    runtimeOrderLocked: bool
    source: str
    updatedAt: str


class UsOrderPrecheckTrStep(BaseModel):
    trId: str
    label: str
    status: str
    detail: str


class UsOrderPrecheckResponse(BaseModel):
    canSubmit: bool
    blockedReasons: list[str]
    requestSummary: dict[str, str | int]
    trSteps: list[UsOrderPrecheckTrStep] = []
    orderableQuantity: int | None = None
    orderableAmount: float | None = None
    capitalUsagePct: float = 100.0
    managedOrderableAmount: float | None = None
    cashReserveAmount: float | None = None
    currency: str | None = None
    marginRate: str | None = None
    source: str
    updatedAt: str
