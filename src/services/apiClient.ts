import type {
  MarketRankingResponse,
  UsDailyAccountReturnSummary,
  UsReadOnlyTrSummary,
  UsRealtimeWindowResponse,
  UsLiquidityAnalysisResponse,
  UsConditionSearchResponse,
} from "@/types";

export interface KiwoomLoginPayload {
  mode: "live";
  accountNo: string;
  appKey: string;
  secretKey: string;
  accessPin: string;
}

export interface KiwoomLoginResult {
  accessToken: string;
  tokenType: "Bearer";
  mode: "live";
  accountLabel: string;
  baseUrl: string;
  readOnly: boolean;
  orderEnabled: boolean;
  expiresAt: string;
}

export interface KiwoomCliProfileSummary {
  profile: string;
  mode: "real";
  current: boolean;
  accountLabel: string;
}

export interface UsQuoteResponse {
  trId: "usa10100" | string;
  symbol: string;
  exchange: string;
  name: string | null;
  price: number | null;
  changeRate: number | null;
  volume: number | null;
  source: string;
  updatedAt: string;
}

export interface UsOrderHistoryItem {
  id: number;
  trId: string;
  side: "buy" | "sell";
  code: string;
  exchange: string;
  quantity: number;
  orderPrice: string;
  referencePrice: string | null;
  tradeType: string;
  strategy: string | null;
  reason: string | null;
  returnCode: string;
  returnMessage: string;
  orderNo: string | null;
  createdAt: string;
}

export interface UsStrategyPnlSnapshot {
  strategy: string;
  symbol: string;
  tradeDate: string;
  actualPnl: number;
  fillCount: number;
  realizedQuantity: number;
  buyQuantity: number;
  sellQuantity: number;
  source: string;
  updatedAt: string;
}

export interface UsStrategyPnlSummary {
  rows: UsStrategyPnlSnapshot[];
  trId: string;
  refreshed: boolean;
  warning: string | null;
  source: string;
  updatedAt: string;
}

export interface UsAutoTradeEventItem {
  id: number;
  action: string;
  status: string;
  strategy: string | null;
  symbol: string | null;
  exchange: string | null;
  side: "buy" | "sell" | null;
  trId: string | null;
  sourceOrderId: number | null;
  blockedReasons: string[];
  createdAt: string;
}

export interface UsAutoExitTick {
  enabled: boolean;
  action: string;
  sourceOrderId: number | null;
  exitOrderNo: string | null;
  exitReason: "take_profit" | "stop_loss" | string | null;
  trId: string | null;
  symbol: string | null;
  exchange: string | null;
  quantity: number | null;
  latestPrice: number | null;
  targetPrice: number | null;
  stopLossPrice: number | null;
  retryPlanned: boolean;
  retryCount: number;
  warning: string | null;
  blockedReasons: string[];
  source: string;
  updatedAt: string;
}

export interface UsAutoEntryTick {
  enabled: boolean;
  action: string;
  strategy: string;
  symbol: string | null;
  exchange: string | null;
  quantity: number | null;
  referencePrice: number | null;
  trId: string | null;
  entryOrderNo: string | null;
  targetProfitPct: number | null;
  takeProfitPrice: number | null;
  blockedReasons: string[];
  source: string;
  updatedAt: string;
}

export interface UsAutoTradeRuntimeStatus {
  enabled: boolean;
  observationEnabled: boolean;
  mode: string;
  entryConfirmBypassEnabled: boolean;
  autoExitEnabled: boolean;
  runnerEnabled: boolean;
  runnerRunning: boolean;
  runnerMode: "off" | "observe" | "live";
  runnerIntervalSeconds: number;
  runnerStartedAt: string | null;
  runnerLastTickAt: string | null;
  runnerLastError: string | null;
  runnerTickCount: number;
  runnerLastObservationAction: string | null;
  runnerLastObservationStrategy: string | null;
  runnerLastObservationSymbol: string | null;
  runnerLastObservationExchange: string | null;
  runnerLastObservationBlockedReasons: string[];
  runnerLastObservationFailedCriteria: string[];
  runnerLastObservationAt: string | null;
  startedAt: string | null;
  stoppedAt: string | null;
  maxOrderQuantity: number;
  maxOrderNotional: number;
  capitalUsagePct: number;
  blockedReasons: string[];
  source: string;
  updatedAt: string;
}

export interface UsAutoTradeStrategyStatusItem {
  strategy: string;
  strategyName: string;
  enabled: boolean;
  conditionSeq: string | null;
  conditionName: string | null;
  conditionConnected: boolean;
  conditionRegistered: boolean;
  conditionMatchCount: number;
  conditionMatches: Array<{
    code: string;
    name: string | null;
    exchange: string | null;
    price: number | null;
    changeRate: number | null;
    volume: number | null;
  }>;
  conditionError: string | null;
  conditionLastConnectedAt: string | null;
  conditionLastReceivedAt: string | null;
  conditionReconnectCount: number;
  conditionNextRetrySeconds: number | null;
}

export interface UsAutoTradeStrategyStatus {
  strategies: UsAutoTradeStrategyStatusItem[];
  source: string;
  updatedAt: string;
}

export interface UsObservationStats {
  strategies: Array<{
    strategy: string;
    stateChanges: number;
    readyChanges: number;
    waitingChanges: number;
    uniqueCandidateCount: number;
    topFailedCriteria: Array<{ criterion: string; count: number }>;
    lastChangedAt: string | null;
  }>;
  totalStateChanges: number;
  source: string;
  updatedAt: string;
}

export interface UsOrderStatus {
  orderEnabled: boolean;
  readOnly: boolean;
  runtimeOrderLocked: boolean;
  sessionPresent: boolean;
  sessionMode: "live" | string | null;
  accountLabel: string | null;
  liveOrderConfirmConfigured: boolean;
  liveOrderUnlockConfigured: boolean;
  requiredConfirmText: string;
  requiredUnlockText: string;
  allowedExchanges: string[];
  allowedTradeTypes: string[];
  allowedSymbols: string[];
  maxOrderQuantity: number;
  maxOrderNotional: number;
  capitalUsagePct: number;
  blockedReasons: string[];
  readinessChecklist: Array<{
    key: string;
    label: string;
    passed: boolean;
    detail: string;
  }>;
  source: string;
  updatedAt: string;
}

export interface UsOrderStateMonitorStatus {
  enabled: boolean;
  running: boolean;
  connected: boolean;
  monitoredSymbolCount: number;
  channels: string[];
  lastEventAt: string | null;
  lastConnectedAt: string | null;
  lastHeartbeatAt: string | null;
  lastError: string | null;
  lastReconcileError: string | null;
  reconnectCount: number;
  nextRetrySeconds: number | null;
  updatedCount: number;
  duplicateCount: number;
  source: string;
  updatedAt: string;
}

export interface UsOrderStateMonitorPreflight {
  readyForObservation: boolean;
  observationState: "no_target" | "blocked" | "ready";
  requiredActionCode: string;
  monitorConfigured: boolean;
  sessionPresent: boolean;
  sessionValid: boolean;
  runtimeOrderLocked: boolean;
  submittedReservationCount: number;
  eligibleSymbolCount: number;
  channels: string[];
  blockerReasons: string[];
  source: string;
  updatedAt: string;
}

export class ApiClientError extends Error {
  endpoint: string;
  status?: number;
  type: "missing_token" | "unauthorized" | "http_error" | "network_error" | "invalid_response";
  returnCode?: string;
  returnMessage?: string;

  constructor(
    endpoint: string,
    status: number | undefined,
    message: string,
    type: ApiClientError["type"] = "http_error",
    extra?: { returnCode?: string; returnMessage?: string },
  ) {
    super(message);
    this.name = "ApiClientError";
    this.endpoint = endpoint;
    this.status = status;
    this.type = type;
    this.returnCode = extra?.returnCode;
    this.returnMessage = extra?.returnMessage;
  }
}

const configuredApiBaseUrl = (import.meta.env.VITE_API_BASE_URL || "").trim();
const API_BASE_URL = configuredApiBaseUrl === "same-origin"
  ? ""
  : configuredApiBaseUrl.replace(/\/$/, "");

export function apiWebSocketUrl(endpoint: string) {
  const base = API_BASE_URL || window.location.origin;
  const url = new URL(endpoint, base);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

let accessTokenProvider: (() => string | null) | null = null;
let unauthorizedHandler: (() => void) | null = null;

export function setAccessTokenProvider(provider: (() => string | null) | null) {
  accessTokenProvider = provider;
}

export function setUnauthorizedHandler(handler: (() => void) | null) {
  unauthorizedHandler = handler;
}

export async function getJson<T>(endpoint: string): Promise<T> {
  const token = accessTokenProvider?.() ?? null;
  if (!token) {
    throw new ApiClientError(endpoint, 401, "AUTH_REQUIRED", "missing_token");
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${endpoint}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    throw new ApiClientError(endpoint, undefined, "BACKEND_OFFLINE", "network_error");
  }

  if (response.status === 401) {
    unauthorizedHandler?.();
    throw new ApiClientError(endpoint, 401, "AUTH_REQUIRED", "unauthorized");
  }

  if (!response.ok) {
    throw new ApiClientError(endpoint, response.status, safeErrorMessage(response.status), "http_error");
  }

  try {
    return await response.json() as T;
  } catch {
    throw new ApiClientError(endpoint, response.status, "INVALID_RESPONSE", "invalid_response");
  }
}

export async function postJson<T>(endpoint: string, payload: unknown): Promise<T> {
  const token = accessTokenProvider?.() ?? null;
  if (!token) {
    throw new ApiClientError(endpoint, 401, "AUTH_REQUIRED", "missing_token");
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${endpoint}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json;charset=UTF-8",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(payload),
    });
  } catch {
    throw new ApiClientError(endpoint, undefined, "BACKEND_OFFLINE", "network_error");
  }

  if (response.status === 401) {
    unauthorizedHandler?.();
    throw new ApiClientError(endpoint, 401, "AUTH_REQUIRED", "unauthorized");
  }

  if (!response.ok) {
    const safeDetail = await readSafeErrorDetail(response);
    throw new ApiClientError(
      endpoint,
      response.status,
      safeDetail.message || safeErrorMessage(response.status),
      "http_error",
      { returnCode: safeDetail.returnCode, returnMessage: safeDetail.returnMessage },
    );
  }

  try {
    return await response.json() as T;
  } catch {
    throw new ApiClientError(endpoint, response.status, "INVALID_RESPONSE", "invalid_response");
  }
}

export async function postKiwoomLogin(payload: KiwoomLoginPayload): Promise<KiwoomLoginResult> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/auth/kiwoom/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json;charset=UTF-8" },
      body: JSON.stringify(payload),
    });
  } catch {
    throw new ApiClientError("/api/auth/kiwoom/login", undefined, "BACKEND_OFFLINE", "network_error");
  }

  if (!response.ok) {
    const safeDetail = await readSafeErrorDetail(response);
    throw new ApiClientError(
      "/api/auth/kiwoom/login",
      response.status,
      safeDetail.message || safeErrorMessage(response.status),
      "http_error",
      { returnCode: safeDetail.returnCode, returnMessage: safeDetail.returnMessage },
    );
  }

  try {
    return await response.json() as KiwoomLoginResult;
  } catch {
    throw new ApiClientError("/api/auth/kiwoom/login", response.status, "INVALID_RESPONSE", "invalid_response");
  }
}

export async function getKiwoomCliProfiles(accessPin: string): Promise<KiwoomCliProfileSummary[]> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/auth/kiwoom/profiles`, {
      headers: { "X-Dashboard-Pin": accessPin },
    });
  } catch {
    throw new ApiClientError("/api/auth/kiwoom/profiles", undefined, "BACKEND_OFFLINE", "network_error");
  }

  if (!response.ok) {
    const safeDetail = await readSafeErrorDetail(response);
    throw new ApiClientError(
      "/api/auth/kiwoom/profiles",
      response.status,
      safeDetail.message || safeErrorMessage(response.status),
      "http_error",
    );
  }

  try {
    return await response.json() as KiwoomCliProfileSummary[];
  } catch {
    throw new ApiClientError("/api/auth/kiwoom/profiles", response.status, "INVALID_RESPONSE", "invalid_response");
  }
}

export async function postKiwoomProfileLogin(profile: string | undefined, accessPin: string): Promise<KiwoomLoginResult> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/auth/kiwoom/profile-login`, {
      method: "POST",
      headers: { "Content-Type": "application/json;charset=UTF-8" },
      body: JSON.stringify({ profile: profile || null, accessPin }),
    });
  } catch {
    throw new ApiClientError("/api/auth/kiwoom/profile-login", undefined, "BACKEND_OFFLINE", "network_error");
  }

  if (!response.ok) {
    const safeDetail = await readSafeErrorDetail(response);
    throw new ApiClientError(
      "/api/auth/kiwoom/profile-login",
      response.status,
      safeDetail.message || safeErrorMessage(response.status),
      "http_error",
      { returnCode: safeDetail.returnCode, returnMessage: safeDetail.returnMessage },
    );
  }

  try {
    return await response.json() as KiwoomLoginResult;
  } catch {
    throw new ApiClientError("/api/auth/kiwoom/profile-login", response.status, "INVALID_RESPONSE", "invalid_response");
  }
}

export async function postKiwoomLogout(): Promise<void> {
  const token = accessTokenProvider?.() ?? null;
  if (!token) return;

  try {
    await fetch(`${API_BASE_URL}/api/auth/kiwoom/logout`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    // Local session cleanup must still complete when the backend is offline.
  }
}

export async function validateKiwoomSession(): Promise<UsOrderStatus> {
  return getJson<UsOrderStatus>("/api/us/orders/status");
}

async function readSafeErrorDetail(response: Response) {
  try {
    const body = await response.json();
    const detail = body?.detail;
    if (detail && typeof detail === "object") {
      return {
        message: typeof detail.message === "string" ? detail.message : "",
        returnCode: detail.returnCode === null || detail.returnCode === undefined ? undefined : String(detail.returnCode),
        returnMessage: detail.returnMessage === null || detail.returnMessage === undefined ? undefined : String(detail.returnMessage),
      };
    }
  } catch {
    return {};
  }
  return {};
}

function safeErrorMessage(status: number): string {
  if (status === 401) return "AUTH_REQUIRED";
  if (status === 403) return "AUTH_FORBIDDEN";
  if (status >= 500) return "BACKEND_ERROR";
  return "API_ERROR";
}

export const readonlyApiClient = {
  usCash: () => getJson<UsReadOnlyTrSummary>("/api/us/account/cash"),
  usValuation: () => getJson<UsReadOnlyTrSummary>("/api/us/account/valuation"),
  usHoldings: () => getJson<UsReadOnlyTrSummary>("/api/us/account/holdings"),
  usRealizedPnl: () => getJson<UsReadOnlyTrSummary>("/api/us/account/realized-pnl"),
  usDailyReturns: (fromDate: string, toDate: string) =>
    getJson<UsDailyAccountReturnSummary>(
      `/api/us/account/daily-returns?fromDate=${encodeURIComponent(fromDate)}&toDate=${encodeURIComponent(toDate)}`,
    ),
  usOrderFills: () => getJson<UsReadOnlyTrSummary>("/api/us/account/order-fills"),
  usRanking: (type: "realtime" | "change-rate" | "volume" | "price-spike") =>
    getJson<MarketRankingResponse>(`/api/market/rankings/us/${type}`),
  usConditions: (seq?: string) => {
    const suffix = seq ? `?seq=${encodeURIComponent(seq)}` : "";
    return getJson<UsConditionSearchResponse>(`/api/market/us/conditions${suffix}`);
  },
  usRealtimeWindow: (symbols: string[], exchanges: Record<string, string> = {}) => {
    const search = new URLSearchParams();
    if (symbols.length) search.set("symbols", symbols.join(","));
    const exchangePairs = symbols
      .map((symbol) => `${symbol}:${exchanges[symbol] ?? ""}`)
      .filter((pair) => /:(ND|NY|NA)$/.test(pair));
    if (exchangePairs.length) search.set("exchanges", exchangePairs.join(","));
    const suffix = search.toString() ? `?${search.toString()}` : "";
    return getJson<UsRealtimeWindowResponse>(`/api/market/us/realtime-window${suffix}`);
  },
  usLiquidityAnalysis: (symbol: string, exchange = "ND", thresholdKrw = 10_000_000, fxKrwPerUsd?: number) => {
    const search = new URLSearchParams({ symbol, exchange, thresholdKrw: String(thresholdKrw) });
    if (fxKrwPerUsd !== undefined) search.set("fxKrwPerUsd", String(fxKrwPerUsd));
    return getJson<UsLiquidityAnalysisResponse>(`/api/market/us/liquidity-analysis?${search.toString()}`);
  },
  usQuote: (symbol: string, exchange: string) =>
    getJson<UsQuoteResponse>(`/api/market/us/quote?symbol=${encodeURIComponent(symbol)}&exchange=${encodeURIComponent(exchange)}`),
  usOrderStatus: () => getJson<UsOrderStatus>("/api/us/orders/status"),
  usAutoTradeStatus: () => getJson<UsAutoTradeRuntimeStatus>("/api/us/autotrade/status"),
  usAutoTradeStrategies: (refresh = false) =>
    getJson<UsAutoTradeStrategyStatus>(
      "/api/us/autotrade/strategies" + (refresh ? "?refresh=true" : ""),
    ),
  toggleUsAutoTradeStrategy: (strategy: string, enabled: boolean) =>
    postJson<UsAutoTradeStrategyStatus>(`/api/us/autotrade/strategies/${encodeURIComponent(strategy)}/toggle`, { enabled }),
  enableUsAutoTrade: () => postJson<UsAutoTradeRuntimeStatus>("/api/us/autotrade/enable", {}),
  disableUsAutoTrade: () => postJson<UsAutoTradeRuntimeStatus>("/api/us/autotrade/disable", {}),
  enableUsAutoTradeObservation: () => postJson<UsAutoTradeRuntimeStatus>("/api/us/autotrade/observe/enable", {}),
  disableUsAutoTradeObservation: () => postJson<UsAutoTradeRuntimeStatus>("/api/us/autotrade/observe/disable", {}),
};
