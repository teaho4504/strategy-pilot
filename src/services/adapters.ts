/**
 * Service adapters for AutoTrader KR prototype.
 *
 * UI components must import data through this file only. Account, portfolio,
 * holdings and market data are fetched from the FastAPI backend. Strategy,
 * order, timeline, analytics and risk settings still use local demo state until
 * their backend endpoints are introduced.
 */

import { apiClient } from "./apiClient";
import {
  strategies, orders, timeline, analytics, riskSettings,
} from "./mock/data";
import type {
  Account, AnalyticsSummary, MarketIndex, Order, Portfolio, RiskSettings,
  Strategy, WatchTicker,
} from "@/types";

export interface Holding {
  code: string;
  name: string;
  quantity: number;
  averagePrice: number;
  currentPrice: number;
  valuationAmount: number;
  pnl: number;
  returnPct: number;
  weightPct: number;
  updatedAt: string;
}

export interface AccountPerformance {
  totalEvaluationAmount: number;
  totalPurchaseAmount: number;
  totalPnl: number;
  totalReturnPct: number;
  dayPnl: number;
  dayPnlPct: number;
  holdings: Holding[];
  source: string;
  updatedAt: string;
}

export interface HealthStatus {
  status: string;
  mode: "mock" | "live" | string;
  kiwoom: {
    mode?: string;
    apiBaseUrl?: string;
    configured?: boolean;
    appKey?: string | null;
    accountNo?: string | null;
  };
  lastSuccessAt: string | null;
  error: string | null;
}

interface MarketWatchlistResponse {
  indices: MarketIndex[];
  watchlist: WatchTicker[];
  updatedAt: string;
}

const wait = <T,>(v: T, ms = 120) => new Promise<T>((r) => setTimeout(() => r(v), ms));

export const queryKeys = {
  health: ["health"] as const,
  accounts: ["accounts"] as const,
  portfolio: ["portfolio"] as const,
  performance: ["account-performance"] as const,
  holdings: ["holdings"] as const,
  marketWatchlist: ["market-watchlist"] as const,
  strategies: ["strategies"] as const,
  orders: ["orders"] as const,
  timeline: ["timeline"] as const,
  analytics: (range: AnalyticsSummary["range"]) => ["analytics", range] as const,
  risk: ["risk-settings"] as const,
};

export const portfolioAdapter = {
  getHealth: () => apiClient.get<HealthStatus>("/api/health"),
  getAccounts: () => apiClient.get<Account[]>("/api/accounts"),
  getPortfolio: (_accountId = "default") => apiClient.get<Portfolio & { updatedAt?: string }>("/api/account/portfolio"),
  getPerformance: () => apiClient.get<AccountPerformance>("/api/account/performance"),
  getHoldings: () => apiClient.get<Holding[]>("/api/account/holdings"),
  getMarketWatchlist: () => apiClient.get<MarketWatchlistResponse>("/api/market/watchlist"),
  getMarketIndices: async () => (await apiClient.get<MarketWatchlistResponse>("/api/market/watchlist")).indices,
  getWatchlist: async () => (await apiClient.get<MarketWatchlistResponse>("/api/market/watchlist")).watchlist,
};

export const strategyAdapter = {
  list: () => wait(strategies.map((strategy) => ({ ...strategy }))),
  toggle: (id: string, next: Strategy["status"]) => {
    const s = strategies.find((x) => x.id === id);
    if (s) s.status = next;
    return wait({ ok: true });
  },
};

export const orderAdapter = {
  list: () => wait(orders.map((order) => ({ ...order }))),
  cancel: (id: string) => {
    const o = orders.find((x) => x.id === id);
    if (o && o.status === "pending") o.status = "cancelled";
    return wait({ ok: true } as { ok: true; order?: Order });
  },
};

export const timelineAdapter = {
  recent: () => wait(timeline.map((event) => ({ ...event }))),
};

export const analyticsAdapter = {
  summary: (_range: "today" | "7d" | "30d" | "custom" = "7d") => wait({ ...analytics }),
};

export const riskAdapter = {
  get: () => wait({ ...riskSettings, notify: { ...riskSettings.notify } }),
  update: (patch: Partial<RiskSettings>) => {
    Object.assign(riskSettings, patch);
    return wait({ ok: true });
  },
};
