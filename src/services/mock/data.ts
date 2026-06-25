// Mock data store for the prototype.
// NOTE: This module is the single source of demo data. When wiring real APIs,
// replace `services/adapters.ts` with HTTP/SSE adapters and keep types stable.

import type {
  Account, Portfolio, MarketIndex, WatchTicker,
  Strategy, Order, TimelineEvent, AnalyticsSummary, RiskSettings,
} from "@/types";

export const accounts: Account[] = [
  { id: "acc-demo-1", broker: "키움증권", label: "데모계좌", isDemo: true, maskedNumber: "****-**-1234" },
  { id: "acc-demo-2", broker: "키움증권", label: "테스트 서브계좌", isDemo: true, maskedNumber: "****-**-7788" },
];

const buildCurve = () => {
  const points: { t: string; v: number }[] = [];
  let v = 100;
  for (let i = 0; i < 38; i++) {
    v += (Math.sin(i / 3) + (Math.random() - 0.45)) * 0.4;
    const h = 9 + Math.floor(i / 6);
    const m = (i % 6) * 10;
    points.push({ t: `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`, v: +v.toFixed(2) });
  }
  return points;
};

export const portfolio: Portfolio = {
  equity: 52_184_300,
  cash: 18_420_000,
  dayPnl: 312_500,
  dayPnlPct: 0.61,
  cumulativePnl: 2_184_300,
  cashRatio: 0.353,
  intradayCurve: buildCurve(),
};

export const marketIndices: MarketIndex[] = [
  { code: "KOSPI", name: "KOSPI", value: 2_684.21, changePct: 0.42 },
  { code: "KOSDAQ", name: "KOSDAQ", value: 862.04, changePct: -0.31 },
  { code: "USDKRW", name: "USD/KRW", value: 1_372.5, changePct: 0.18 },
];

export const watchlist: WatchTicker[] = [
  { code: "005930", name: "삼성전자", price: 71_800, changePct: 0.84 },
  { code: "000660", name: "SK하이닉스", price: 198_500, changePct: 1.92 },
  { code: "035420", name: "NAVER", price: 184_200, changePct: -0.65 },
];

export const strategies: Strategy[] = [
  {
    id: "stg-1",
    name: "거래대금 돌파 스캘핑",
    universe: "코스피 200 · 거래대금 상위 30",
    timeframe: "1분봉",
    status: "running",
    dayReturnPct: 1.24,
    maxLossLimit: 500_000,
    lastSignalAt: new Date(Date.now() - 4 * 60_000).toISOString(),
    signalsToday: 14,
    fillsToday: 6,
    description: "거래대금 급증 + 호가 잔량 우위에서 진입, 짧은 추적손절.",
  },
  {
    id: "stg-2",
    name: "상승 추세 눌림목",
    universe: "코스피 · 시총 1조 이상",
    timeframe: "5분봉",
    status: "paused",
    dayReturnPct: -0.18,
    maxLossLimit: 800_000,
    lastSignalAt: new Date(Date.now() - 42 * 60_000).toISOString(),
    signalsToday: 3,
    fillsToday: 1,
    description: "20일선 위 종목의 5분봉 눌림목에서 분할 진입.",
  },
  {
    id: "stg-3",
    name: "변동성 돌파",
    universe: "코스닥 150",
    timeframe: "일봉",
    status: "idle",
    dayReturnPct: 0,
    maxLossLimit: 600_000,
    lastSignalAt: null,
    signalsToday: 0,
    fillsToday: 0,
    description: "전일 변동폭 × k 만큼 돌파 시 진입, 종가 청산.",
  },
  {
    id: "stg-4",
    name: "짝궁 후속주 추적",
    universe: "테마/섹터 연동주",
    timeframe: "3분봉",
    status: "error",
    dayReturnPct: -0.42,
    maxLossLimit: 400_000,
    lastSignalAt: new Date(Date.now() - 12 * 60_000).toISOString(),
    signalsToday: 5,
    fillsToday: 2,
    description: "선도주 급등 시 후속주 진입. (데모) 데이터 어댑터 오류 발생.",
  },
];

export const orders: Order[] = [
  {
    id: "ord-1001", time: new Date(Date.now() - 3 * 60_000).toISOString(),
    code: "005930", name: "삼성전자", side: "BUY", qty: 20, price: 71_800,
    status: "filled", strategyId: "stg-1", strategyName: "거래대금 돌파 스캘핑",
    reason: "거래대금 5분 평균 대비 +320%, 호가잔량비 1.8",
  },
  {
    id: "ord-1002", time: new Date(Date.now() - 8 * 60_000).toISOString(),
    code: "000660", name: "SK하이닉스", side: "BUY", qty: 4, price: 198_500,
    status: "pending", strategyId: "stg-1", strategyName: "거래대금 돌파 스캘핑",
    reason: "거래대금 돌파 신호, 지정가 198,500",
  },
  {
    id: "ord-1003", time: new Date(Date.now() - 25 * 60_000).toISOString(),
    code: "034020", name: "두산에너빌리티", side: "SELL", qty: 30, price: 21_350,
    status: "partial", strategyId: "stg-2", strategyName: "상승 추세 눌림목",
    reason: "보유 +1.2% 도달, 분할 청산 1차",
  },
  {
    id: "ord-1004", time: new Date(Date.now() - 55 * 60_000).toISOString(),
    code: "035420", name: "NAVER", side: "BUY", qty: 6, price: 184_200,
    status: "cancelled", strategyId: "stg-2", strategyName: "상승 추세 눌림목",
    reason: "조건 미달로 자동 취소 (5분 미체결)",
  },
  {
    id: "ord-1005", time: new Date(Date.now() - 95 * 60_000).toISOString(),
    code: "005930", name: "삼성전자", side: "SELL", qty: 20, price: 71_350,
    status: "failed", strategyId: "stg-4", strategyName: "짝궁 후속주 추적",
    reason: "(데모) 시세 어댑터 일시 단절로 실패",
  },
];

export const timeline: TimelineEvent[] = [
  { id: "t1", kind: "fill", time: new Date(Date.now() - 3 * 60_000).toISOString(),
    title: "삼성전자 매수 체결", detail: "20주 · 71,800원", strategyName: "거래대금 돌파 스캘핑" },
  { id: "t2", kind: "signal", time: new Date(Date.now() - 6 * 60_000).toISOString(),
    title: "SK하이닉스 진입 신호", detail: "거래대금 +320%", strategyName: "거래대금 돌파 스캘핑" },
  { id: "t3", kind: "order", time: new Date(Date.now() - 7 * 60_000).toISOString(),
    title: "SK하이닉스 매수 주문 제출", detail: "4주 · 198,500원 지정가", strategyName: "거래대금 돌파 스캘핑" },
  { id: "t4", kind: "risk", time: new Date(Date.now() - 14 * 60_000).toISOString(),
    title: "전략 오류 경고", detail: "짝궁 후속주 추적: 데이터 어댑터 재시도", strategyName: "짝궁 후속주 추적" },
  { id: "t5", kind: "fill", time: new Date(Date.now() - 25 * 60_000).toISOString(),
    title: "두산에너빌리티 분할 매도 일부 체결", detail: "15/30주 · 21,350원", strategyName: "상승 추세 눌림목" },
];

export const analytics: AnalyticsSummary = {
  range: "7d",
  realizedPnl: 842_500,
  winRate: 0.58,
  avgWin: 84_200,
  avgLoss: -52_800,
  mdd: -310_000,
  avgHoldMin: 23,
  perStrategy: [
    { name: "거래대금 돌파 스캘핑", pnl: 612_000 },
    { name: "상승 추세 눌림목", pnl: 285_000 },
    { name: "변동성 돌파", pnl: 0 },
    { name: "짝궁 후속주 추적", pnl: -54_500 },
  ],
  byHour: [
    { hour: 9, fills: 18 }, { hour: 10, fills: 12 }, { hour: 11, fills: 7 },
    { hour: 12, fills: 3 }, { hour: 13, fills: 6 }, { hour: 14, fills: 11 }, { hour: 15, fills: 9 },
  ],
  lossTags: [
    { tag: "급변 거래정지", count: 2 },
    { tag: "슬리피지 과다", count: 4 },
    { tag: "추격 후 되돌림", count: 6 },
    { tag: "시장 약세 필터 미흡", count: 3 },
  ],
};

export const riskSettings: RiskSettings = {
  dailyLossLimit: 800_000,
  perStrategyMaxInvest: 10_000_000,
  perTickerMaxWeightPct: 25,
  maxConcurrentTickers: 5,
  maxOrdersPerDay: 60,
  notify: { strategyError: true, orderFailure: true, dailyLossHit: true, bigPnl: false },
};
