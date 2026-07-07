import type { Account, Portfolio, WatchTicker } from "@/types";

export interface CashBalance {
  cash: number;
  withdrawableAmount: number;
  orderableAmount: number;
  source: string;
  updatedAt: string;
}

export interface Holding {
  code: string;
  name: string;
  quantity: number;
  averagePrice: number;
  currentPrice: number;
  valuationAmount: number;
  profitLoss: number;
  returnRate: number;
  weight: number;
  updatedAt: string;
}

export interface PerformanceSummary {
  accountId: string;
  totalPurchaseAmount: number;
  totalValuationAmount: number;
  totalProfitLoss: number;
  totalReturnRate: number;
  source: string;
  updatedAt: string;
}

export interface ApiClientErrorDetails {
  endpoint: string;
  status?: number;
  type: "missing_token" | "unauthorized" | "http_error" | "network_error" | "invalid_response";
}

export class ApiClientError extends Error {
  endpoint: string;
  status?: number;
  type: ApiClientErrorDetails["type"];

  constructor(message: string, details: ApiClientErrorDetails) {
    super(message);
    this.name = "ApiClientError";
    this.endpoint = details.endpoint;
    this.status = details.status;
    this.type = details.type;
  }
}

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";
export const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL).replace(/\/$/, "");

let accessTokenProvider: (() => string | null) | null = null;
let unauthorizedHandler: (() => void) | null = null;

export function setAccessTokenProvider(provider: (() => string | null) | null) {
  accessTokenProvider = provider;
}

export function setUnauthorizedHandler(handler: (() => void) | null) {
  unauthorizedHandler = handler;
}

async function requestJson<T>(endpoint: string): Promise<T> {
  const token = accessTokenProvider?.() ?? null;
  if (!token) {
    throw new ApiClientError("Missing API access token", { endpoint, type: "missing_token" });
  }

  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}${endpoint}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch (error) {
    throw new ApiClientError("Backend request failed", { endpoint, type: "network_error" });
  }

  if (response.status === 401) {
    unauthorizedHandler?.();
    throw new ApiClientError("Authentication expired", { endpoint, status: 401, type: "unauthorized" });
  }

  if (!response.ok) {
    throw new ApiClientError("Backend returned an error", { endpoint, status: response.status, type: "http_error" });
  }

  try {
    return await response.json() as T;
  } catch (error) {
    throw new ApiClientError("Backend response was not JSON", { endpoint, status: response.status, type: "invalid_response" });
  }
}

export const readonlyApiClient = {
  accounts: () => requestJson<Account[]>("/api/accounts"),
  portfolio: () => requestJson<Portfolio>("/api/account/portfolio"),
  cash: () => requestJson<CashBalance>("/api/account/cash"),
  holdings: () => requestJson<Holding[]>("/api/account/holdings"),
  performance: () => requestJson<PerformanceSummary>("/api/account/performance"),
  watchlist: () => requestJson<WatchTicker[]>("/api/market/watchlist"),
};

export function safeApiError(error: unknown): ApiClientErrorDetails | null {
  if (error instanceof ApiClientError) {
    return { endpoint: error.endpoint, status: error.status, type: error.type };
  }
  return null;
}
