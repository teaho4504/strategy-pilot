import { useQuery } from "@tanstack/react-query";
import { apiGet } from "./apiClient";
import {
  marketIndices, strategies, orders, timeline, analytics, riskSettings,
} from "./mock/data";
import type {
  Account,
  AnalyticsSummary,
  BackendHealth,
  CashBalance,
  Holding,
  Order,
  PerformanceSummary,
  Portfolio,
  RiskSettings,
  Strategy,
  WatchTicker,
} from "@/types";

const wait = <T,>(v: T, ms = 120) => new Promise<T>((r) => setTimeout(() => r(v), ms));

export const queryKeys = {
  health: ["backend", "health"] as const,
  accounts: ["accounts"] as const,
  portfolio: (accountId: string) => ["account", accountId, "portfolio"] as const,
  cash: (accountId: string) => ["account", accountId, "cash"] as const,
  holdings: (accountId: string) => ["account", accountId, "holdings"] as const,
  performance: (accountId: string) => ["account", accountId, "performance"] as const,
  marketSummary: ["market", "summary"] as const,
  strategies: ["strategies"] as const,
  orders: ["orders"] as const,
  timeline: ["timeline"] as const,
  analytics: (range: AnalyticsSummary["range"]) => ["analytics", range] as const,
  risk: ["risk"] as const,
};

export const backendAdapter = {
  health: () => apiGet<BackendHealth>("/api/health"),
};

export const portfolioAdapter = {
  getAccounts: () => apiGet<Account[]>("/api/accounts"),
  getPortfolio: (_accountId: string) => apiGet<Portfolio>("/api/account/portfolio"),
  getCash: (_accountId: string) => apiGet<CashBalance>("/api/account/cash"),
  getHoldings: (_accountId: string) => apiGet<Holding[]>("/api/account/holdings"),
  getPerformance: (_accountId: string) => apiGet<PerformanceSummary>("/api/account/performance"),
  getMarketIndices: () => wait(marketIndices),
  getWatchlist: () => apiGet<WatchTicker[]>("/api/market/watchlist"),
};

export const strategyAdapter = {
  list: () => wait(strategies),
  toggle: (id: string, next: Strategy["status"]) => {
    const s = strategies.find((x) => x.id === id);
    if (s) s.status = next;
    return wait({ ok: true });
  },
  pauseAll: () => {
    strategies.forEach((s) => {
      if (s.status === "running") s.status = "paused";
    });
    return wait({ ok: true });
  },
};

export const orderAdapter = {
  list: () => wait(orders),
  cancel: (id: string) => {
    const o = orders.find((x) => x.id === id);
    if (o && o.status === "pending") o.status = "cancelled";
    return wait({ ok: true } as { ok: true; order?: Order });
  },
};

export const timelineAdapter = {
  recent: () => wait(timeline),
};

export const analyticsAdapter = {
  summary: (range: AnalyticsSummary["range"] = "7d") => wait({ ...analytics, range }),
};

export const riskAdapter = {
  get: () => wait(riskSettings),
  update: (patch: Partial<RiskSettings>) => {
    Object.assign(riskSettings, patch);
    return wait({ ok: true });
  },
};

export function useBackendHealthQuery() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: backendAdapter.health,
    refetchInterval: 10_000,
  });
}

export function useAccountsQuery() {
  return useQuery({
    queryKey: queryKeys.accounts,
    queryFn: portfolioAdapter.getAccounts,
    refetchInterval: 10_000,
  });
}

export function usePortfolioQuery(accountId: string) {
  return useQuery({
    queryKey: queryKeys.portfolio(accountId),
    queryFn: () => portfolioAdapter.getPortfolio(accountId),
    refetchInterval: 5_000,
  });
}

export function useCashQuery(accountId: string) {
  return useQuery({
    queryKey: queryKeys.cash(accountId),
    queryFn: () => portfolioAdapter.getCash(accountId),
    refetchInterval: 10_000,
  });
}

export function useHoldingsQuery(accountId: string) {
  return useQuery({
    queryKey: queryKeys.holdings(accountId),
    queryFn: () => portfolioAdapter.getHoldings(accountId),
    refetchInterval: 10_000,
  });
}

export function usePerformanceQuery(accountId: string) {
  return useQuery({
    queryKey: queryKeys.performance(accountId),
    queryFn: () => portfolioAdapter.getPerformance(accountId),
    refetchInterval: 10_000,
  });
}

export function useMarketSummaryQuery() {
  return useQuery({
    queryKey: queryKeys.marketSummary,
    queryFn: async () => ({
      marketIndices: await portfolioAdapter.getMarketIndices(),
      watchlist: await portfolioAdapter.getWatchlist(),
    }),
    refetchInterval: 5_000,
  });
}

export function useStrategiesQuery() {
  return useQuery({ queryKey: queryKeys.strategies, queryFn: strategyAdapter.list });
}

export function useOrdersQuery() {
  return useQuery({ queryKey: queryKeys.orders, queryFn: orderAdapter.list });
}

export function useTimelineQuery() {
  return useQuery({ queryKey: queryKeys.timeline, queryFn: timelineAdapter.recent });
}

export function useAnalyticsQuery(range: AnalyticsSummary["range"] = "7d") {
  return useQuery({ queryKey: queryKeys.analytics(range), queryFn: () => analyticsAdapter.summary(range) });
}

export function useRiskSettingsQuery() {
  return useQuery({ queryKey: queryKeys.risk, queryFn: riskAdapter.get });
}
