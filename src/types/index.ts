// Domain types for AutoTrader KR dashboard.
// Brokerage credentials and tokens must stay on the FastAPI backend.

export type AutomationState = "idle" | "running" | "paused" | "error";

export interface Account {
  id: string;
  broker: string;        // e.g. "키움증권"
  label: string;         // e.g. "데모계좌"
  isDemo: boolean;
  maskedNumber: string;  // e.g. "****-**-1234"
}

export interface Portfolio {
  equity: number;            // 평가자산
  cash: number;              // 현금
  dayPnl: number;            // 당일 손익(원)
  dayPnlPct: number;         // 당일 수익률(%)
  cumulativePnl: number;     // 누적 손익
  cashRatio: number;         // 현금 비중(0-1)
  intradayCurve: { t: string; v: number }[]; // 시간별 평가곡선
  updatedAt?: string;
}

export interface CashBalance {
  deposit: number;
  orderableAmount: number;
  withdrawableAmount: number;
  updatedAt: string;
}

export interface Holding {
  code: string;
  name: string;
  quantity: number;
  avgPrice: number;
  currentPrice: number;
  marketValue: number;
  pnl: number;
  pnlPct: number;
  weightPct: number;
  updatedAt: string;
}

export interface PerformancePosition {
  code: string;
  name: string;
  currentPrice: number;
  avgPrice: number;
  quantity: number;
  purchaseAmount: number;
  daySellPnl: number;
  pnl: number;
  pnlPct: number;
}

export interface PerformanceSummary {
  totalPnl: number;
  totalPnlPct: number;
  positions: PerformancePosition[];
  updatedAt: string;
}

export interface ConnectionStatus {
  api: "connected" | "disconnected" | "error";
  websocket: "connected" | "connecting" | "reconnecting" | "disconnected";
  mode: "mock" | "live";
  lastUpdatedAt: string | null;
}

export interface BackendHealth {
  ok: boolean;
  mode: "mock" | "live";
  kiwoomConfigured: boolean;
  kiwoomMissing: string[];
  lastUpdatedAt: string | null;
  lastError: string | null;
  connection: ConnectionStatus;
}

export interface MarketIndex {
  code: "KOSPI" | "KOSDAQ" | "USDKRW";
  name: string;
  value: number;
  changePct: number;
}

export interface WatchTicker {
  code: string;     // "005930"
  name: string;     // "삼성전자"
  price: number;
  changePct: number;
  updatedAt?: string;
}

export type StrategyStatus = "running" | "idle" | "paused" | "error";

export interface Strategy {
  id: string;
  name: string;
  universe: string;          // 적용 종목군 요약
  timeframe: string;         // "1m" | "5분봉" | "일봉" ...
  status: StrategyStatus;
  dayReturnPct: number;
  maxLossLimit: number;      // 원 단위 최대 손실 한도
  lastSignalAt: string | null; // ISO
  signalsToday: number;
  fillsToday: number;
  description?: string;
}

export type OrderSide = "BUY" | "SELL";
export type OrderStatus = "pending" | "filled" | "partial" | "cancelled" | "failed";

export interface Order {
  id: string;
  time: string;          // ISO
  code: string;
  name: string;
  side: OrderSide;
  qty: number;
  price: number;
  status: OrderStatus;
  strategyId: string;
  strategyName: string;
  reason: string;        // 주문 근거(어떤 조건에서 발동)
}

export type TimelineKind = "signal" | "order" | "fill" | "risk";
export interface TimelineEvent {
  id: string;
  kind: TimelineKind;
  time: string; // ISO
  title: string;
  detail: string;
  strategyName?: string;
}

export interface AnalyticsSummary {
  range: "today" | "7d" | "30d" | "custom";
  realizedPnl: number;
  winRate: number;       // 0-1
  avgWin: number;
  avgLoss: number;
  mdd: number;           // 최대낙폭(원)
  avgHoldMin: number;    // 평균 보유시간(분)
  perStrategy: { name: string; pnl: number }[];
  byHour: { hour: number; fills: number }[];
  lossTags: { tag: string; count: number }[];
}

export interface RiskSettings {
  dailyLossLimit: number;            // 원
  perStrategyMaxInvest: number;      // 원
  perTickerMaxWeightPct: number;     // %
  maxConcurrentTickers: number;
  maxOrdersPerDay: number;
  notify: {
    strategyError: boolean;
    orderFailure: boolean;
    dailyLossHit: boolean;
    bigPnl: boolean;
  };
}
