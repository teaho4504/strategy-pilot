/**
 * Service adapters for AutoTrader KR prototype.
 *
 * IMPORTANT (handoff notes for backend integration):
 * - This file is the ONLY place the UI talks to "data". Swap mock returns for
 *   real HTTP/WS clients without touching components.
 * - Real order execution MUST live on a server-side worker (not the browser).
 *   The dashboard should call a thin internal API; brokerage secrets stay on
 *   the server. NEVER place API keys / secrets in frontend code or .env files
 *   that ship to the client.
 * - Suggested split when going live:
 *     ├─ apps/dashboard       (this app, calls /api/* only)
 *     ├─ apps/order-worker    (long-running process, holds broker credentials)
 *     └─ packages/shared      (types in `src/types` move here)
 */

import {
  accounts, portfolio, marketIndices, watchlist, strategies,
  orders, timeline, analytics, riskSettings,
} from "./mock/data";
import { readonlyApiClient } from "./apiClient";
import type { Strategy, Order } from "@/types";

const wait = <T,>(v: T, ms = 120) => new Promise<T>((r) => setTimeout(() => r(v), ms));

export const portfolioAdapter = {
  getHealth: readonlyApiClient.health,
  getKiwoomStatus: readonlyApiClient.kiwoomStatus,
  getAccounts: readonlyApiClient.accounts,
  getCash: readonlyApiClient.cash,
  getPortfolio: (_accountId?: string) => readonlyApiClient.portfolio(),
  getHoldings: readonlyApiClient.holdings,
  getPerformance: readonlyApiClient.performance,
  getMarketIndices: () => wait(marketIndices),
  getWatchlist: readonlyApiClient.watchlist,
  getMockAccounts: () => wait(accounts),
  getMockPortfolio: () => wait(portfolio),
  getMockWatchlist: () => wait(watchlist),
};

export const strategyAdapter = {
  list: () => wait(strategies),
  toggle: (id: string, next: Strategy["status"]) => {
    const s = strategies.find((x) => x.id === id);
    if (s) s.status = next;
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
  summary: (_range: "today" | "7d" | "30d" | "custom" = "7d") => wait(analytics),
};

export const riskAdapter = {
  get: () => wait(riskSettings),
  update: (patch: Partial<typeof riskSettings>) => {
    Object.assign(riskSettings, patch);
    return wait({ ok: true });
  },
};
