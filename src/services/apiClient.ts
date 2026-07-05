import type {
  Account,
  BackendHealth,
  CashBalance,
  Holding,
  KiwoomStatus,
  PerformanceSummary,
  Portfolio,
  WatchTicker,
} from "@/types";

export type ApiErrorType = "backend_offline" | "http_error" | "invalid_response";

export class ApiClientError extends Error {
  endpoint: string;
  status?: number;
  type: ApiErrorType;

  constructor(endpoint: string, type: ApiErrorType, message: string, status?: number) {
    super(message);
    this.name = "ApiClientError";
    this.endpoint = endpoint;
    this.status = status;
    this.type = type;
  }
}

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";

export const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL).replace(/\/$/, "");

async function requestJson<T>(endpoint: string): Promise<T> {
  try {
    const response = await fetch(`${apiBaseUrl}${endpoint}`, {
      headers: { Accept: "application/json" },
    });

    if (!response.ok) {
      throw new ApiClientError(endpoint, "http_error", `HTTP ${response.status}`, response.status);
    }

    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiClientError) throw error;
    throw new ApiClientError(endpoint, "backend_offline", "Backend offline or unreachable");
  }
}

export const readonlyApiClient = {
  health: () => requestJson<BackendHealth>("/api/health"),
  kiwoomStatus: () => requestJson<KiwoomStatus>("/api/kiwoom/status"),
  accounts: () => requestJson<Account[]>("/api/accounts"),
  cash: () => requestJson<CashBalance>("/api/account/cash"),
  portfolio: () => requestJson<Portfolio>("/api/account/portfolio"),
  holdings: () => requestJson<Holding[]>("/api/account/holdings"),
  performance: () => requestJson<PerformanceSummary>("/api/account/performance"),
  watchlist: () => requestJson<WatchTicker[]>("/api/market/watchlist"),
};

export function safeError(error: unknown) {
  if (error instanceof ApiClientError) {
    return {
      endpoint: error.endpoint,
      status: error.status,
      type: error.type,
      guidance: error.type === "backend_offline" ? "FastAPI backend 실행 상태를 확인하세요." : "backend 로그와 endpoint 상태를 확인하세요.",
    };
  }
  return {
    endpoint: "unknown",
    status: undefined,
    type: "invalid_response" as ApiErrorType,
    guidance: "응답 형식 또는 네트워크 상태를 확인하세요.",
  };
}
