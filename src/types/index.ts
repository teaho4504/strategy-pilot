export interface UsReadOnlyTrSummary {
  trId: string;
  returnCode: string;
  returnMessage: string;
  schemaKeys: string[];
  data: Record<string, unknown>;
  normalized?: Record<string, unknown> | null;
  source: string;
  updatedAt: string;
}

export interface UsDailyAccountReturnRow {
  baseDate: string | null;
  stockValuation: string | null;
  profitLossAmount: string | null;
  dividendAmount: string | null;
  commissionAndTax: string | null;
  accumulatedProfitLoss: string | null;
  withdrawalAmount: string | null;
  depositAsset: string | null;
  overdueAmount: string | null;
  sellAmount: string | null;
  buyAmount: string | null;
  returnRate: string | null;
  foreignStockOutboundAmount: string | null;
  foreignStockInboundAmount: string | null;
  depositAmount: string | null;
  exchangeRate: string | null;
  unknownFields: Record<string, unknown>;
}

export interface UsDailyAccountReturnSummary {
  trId: "usa21670" | string;
  returnCode: string;
  returnMessage: string;
  schemaKeys: string[];
  rows: UsDailyAccountReturnRow[];
  source: string;
  updatedAt: string;
}

export interface MarketRankItem {
  rank: number;
  code: string;
  name: string;
  price: number;
  changeRate: number;
  volume: number | null;
  tradingValue: number | null;
  exchange: string | null;
  reason: string;
}

export interface MarketRankingResponse {
  trId: string;
  title: string;
  market: "KR" | "US" | string;
  source: string;
  updatedAt: string;
  items: MarketRankItem[];
  notes?: string[];
}

export interface UsConditionItem {
  seq: string;
  name: string;
}

export interface UsConditionSearchMatch {
  code: string;
  name: string | null;
  exchange: string | null;
  price: number | null;
  changeRate: number | null;
  volume: number | null;
}

export interface UsConditionSearchResponse {
  source: string;
  listTrId: "usa20280" | string;
  searchTrId: "usa20281" | string;
  realtimeTrId: "usa20290" | string;
  clearTrId: "usa20291" | string;
  updatedAt: string;
  conditions: UsConditionItem[];
  selectedSeq: string | null;
  selectedName: string | null;
  matches: UsConditionSearchMatch[];
  schemaKeys: string[];
}

export interface UsAutoTradeCriterion {
  key: string;
  label: string;
  status: "pass" | "fail" | "unavailable" | string;
  value: string | null;
  reason: string;
}

export interface UsAutoTradeOrderTicket {
  side: string;
  exchange: string;
  symbol: string;
  quantity: number;
  tradeType: string;
  referencePrice: number;
  targetProfitPct: number;
  takeProfitPrice: number;
  submitEndpoint: string;
  submitBlocked: boolean;
  submitBlockReason: string | null;
}

export interface UsAutoTradeProcessStep {
  step: string;
  label: string;
  status: "ready" | "blocked" | "waiting" | string;
  trId: string | null;
  detail: string;
}

export interface UsAutoTradePlanResponse {
  source: string;
  strategy: string;
  strategyName: string | null;
  conditionSeq: string | null;
  conditionName: string | null;
  enabled: boolean;
  timeframe: string | null;
  tickScope: string | null;
  rankingTrId: string;
  chartTrId: string;
  orderPrecheckTrId: string;
  updatedAt: string;
  targetRank: number;
  target: MarketRankItem | null;
  criteria: UsAutoTradeCriterion[];
  minPassedCriteria: number;
  passedCriteriaCount: number;
  criticalFailedCriteria: string[];
  readyForEntry: boolean;
  stopLossPct: number;
  orderTicket: UsAutoTradeOrderTicket | null;
  takeProfitOrderTicket: UsAutoTradeOrderTicket | null;
  oneShareProcessReady: boolean;
  liveOrderBlockedReasons: string[];
  processSteps: UsAutoTradeProcessStep[];
  executionState: string;
  nextAction: string;
}

export interface UsAutoTradePlanListResponse {
  source: string;
  updatedAt: string;
  selectedStrategy: string | null;
  plans: UsAutoTradePlanResponse[];
  candidatePlans: UsAutoTradePlanResponse[];
}

export interface UsAutoTradeDiagnosticsResponse {
  decision: string;
  canAttemptEntry: boolean;
  canAttemptExit: boolean;
  blockingStage: string | null;
  blockerReasons: string[];
  requiredAction: string;
  status: {
    enabled: boolean;
    mode: string;
    entryConfirmBypassEnabled: boolean;
    autoExitEnabled: boolean;
    runnerEnabled: boolean;
    runnerRunning: boolean;
    runnerIntervalSeconds: number;
    runnerStartedAt: string | null;
    runnerLastTickAt: string | null;
    runnerLastError: string | null;
    runnerTickCount: number;
    startedAt: string | null;
    stoppedAt: string | null;
    maxOrderQuantity: number;
    maxOrderNotional: number;
    capitalUsagePct: number;
    blockedReasons: string[];
    source: string;
    updatedAt: string;
  };
  pipeline: {
    todayDate: string;
    ordersToday: number;
    eventsToday: number;
    realtimeEventsToday: number;
    latestOrderAt: string | null;
    latestEventAt: string | null;
    latestRealtimeAt: string | null;
    latestEventAction: string | null;
    latestEventStatus: string | null;
    dataFlowOk: boolean;
    orderFlowOk: boolean;
    runnerHealthy: boolean;
    warning: string | null;
  };
  plan: UsAutoTradePlanResponse | null;
  latestEvent: {
    id: number;
    action: string;
    status: string;
    symbol: string | null;
    exchange: string | null;
    side: "buy" | "sell" | null;
    trId: string | null;
    sourceOrderId: number | null;
    blockedReasons: string[];
    createdAt: string;
  } | null;
  planError: string | null;
  source: string;
  updatedAt: string;
}

export interface UsRealtimeWindowItem {
  symbol: string;
  tickCount: number;
  orderbookCount: number;
  latestPrice: number | null;
  latestChangeRate: number | null;
  latestVolume: number | null;
  volume10sDelta: number | null;
  volume10sIncreasing: boolean | null;
  tradeStrength: number | null;
  tradeStrengthIncreasing: boolean | null;
  bid: number | null;
  ask: number | null;
  spreadPct: number | null;
  spreadWithin01Pct: boolean | null;
  lastEventAt: string | null;
  sourceEventTime: string | null;
  receiveDelayMs: number | null;
  persistedEventCount: number;
  dbEvents10s: number;
  dbEvents1m: number;
  dbEvents5m: number;
  dbVolume10sDelta: number | null;
  dbVolume1mDelta: number | null;
  dbVolume5mDelta: number | null;
  dbTradeStrength1mChange: number | null;
  dbSpreadPct: number | null;
}

export interface UsRealtimeWindowResponse {
  source: string;
  channels: string[];
  updatedAt: string;
  monitorRunning: boolean;
  monitorConnected: boolean;
  monitoredSymbols: string[];
  monitorLastError: string | null;
  monitorLastConnectedAt: string | null;
  monitorLastHeartbeatAt: string | null;
  monitorReconnectCount: number;
  monitorNextRetrySeconds: number | null;
  marketSession: "premarket" | "regular" | "afterhours" | "closed" | string;
  qualityState: "idle" | "healthy" | "degraded" | "stale";
  expectedSymbolCount: number;
  freshSymbolCount: number;
  staleSymbolCount: number;
  missingSymbolCount: number;
  delayedSymbolCount: number;
  coveragePct: number;
  averageReceiveDelayMs: number | null;
  maxReceiveDelayMs: number | null;
  items: UsRealtimeWindowItem[];
}

export interface UsLiquidityWall {
  side: "bid" | "ask";
  level: number;
  price: number;
  quantity: number;
  notionalKrw: number;
  state: "appeared" | "growing" | "stable" | "shrinking" | "disappeared";
  exitInference: "likely-execution" | "possible-execution" | "likely-cancel" | "unknown" | null;
}

export interface UsLiquidityTimeframe {
  timeframe: "1m" | "5m" | "1h";
  seconds: number;
  candleCount: number;
  latestClose: number | null;
  ema9: number | null;
  ema20: number | null;
  changePct: number | null;
  trend: "bullish" | "bearish" | "flat" | "unavailable";
  pullback: boolean;
  dataSufficient: boolean;
  source?: string;
  trId?: string;
  tickScope?: string;
  latestCandleAt?: string | null;
  latestCandleAtUtc?: string | null;
  timestampConvention?: "kiwoom-us-extended-kst-observed";
  continuationComplete?: boolean;
  continuationPages?: number;
  candles: Array<{
    timestamp: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volumeDelta: number;
  }>;
}

export interface UsLiquidityAnalysisResponse {
  source: string;
  symbol: string;
  thresholdKrw: number;
  fxKrwPerUsd: number;
  fxSource: string;
  fxAsOf: string | null;
  fxStaleDays: number | null;
  streamOwner: string;
  channels: string[];
  updatedAt: string;
  orderbookSnapshotCount: number;
  tickEventCount: number;
  latest: {
    bidWallKrw: number;
    askWallKrw: number;
    imbalancePct: number | null;
    dominantSide: "bid" | "ask" | "balanced";
    wallCount: number;
  };
  timeline: Array<{ timestamp: string; walls: UsLiquidityWall[] }>;
  timeframes: UsLiquidityTimeframe[];
  chartContext: {
    source: "kiwoom-usa06011" | "persisted-fe-fallback" | string;
    requestedScopes?: string[];
    availableTimeframes: string[];
    unavailableTimeframes?: string[];
    cachedForSeconds?: number;
    updatedAt?: string;
  };
  observationQuality: {
    state: "ready" | "off_hours" | "reconnecting" | "stale" | "missing" | "degraded";
    signalEligible: boolean;
    marketSession: "premarket" | "regular" | "afterhours" | "closed";
    marketDate: string;
    marketTimeZone: "America/New_York";
    calendarMode: "weekday-session-approximation";
    monitorRunning: boolean;
    monitorConnected: boolean;
    latestEventAt: string | null;
    eventAgeSeconds: number | null;
    maxEventAgeSeconds: number;
    requiredTimeframes: string[];
    availableTimeframes: string[];
    missingTimeframes: string[];
    chartAgeSeconds: Record<string, number | null>;
    staleTimeframes: string[];
    reasons: string[];
  };
  signal: {
    action: "BUY_WATCH" | "SELL_WATCH" | "WATCH";
    confidence: "observation-only";
    reasons: string[];
    executionAuthorized: false;
    expiresAt: string | null;
  };
  signalHistory: Array<{
    action: "BUY_WATCH" | "SELL_WATCH" | "WATCH";
    sourceEventAt: string | null;
    reasons: string[];
    executionAuthorized: false;
    createdAt: string;
  }>;
  executionAuthorized: false;
  limitations: string[];
  monitor: {
    running: boolean;
    connected: boolean;
    channels: string[];
    lastError: string | null;
  };
}
