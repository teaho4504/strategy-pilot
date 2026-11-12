import type {
  ControlStatus, HealthStatus, Position, Quote, Team2Plan, Top10Universe, VerificationInput,
} from "@/types/us";

/**
 * 인계서(2026-11-12 21:00 KST) 시점의 잠금 상태를 재현한 모의 데이터.
 * 종목·가격은 예시이며 실계좌 정보는 포함하지 않는다.
 */

const iso = (offsetSec = 0) => new Date(Date.now() + offsetSec * 1000).toISOString();

export const mockHealth = (): HealthStatus => ({
  ok: true,
  readOnly: true,
  orderEnabled: false,
  emergencyStop: true,
  adminEnabled: false,
  runnerEnabled: false,
  serverTime: iso(),
});

export const mockControl = (): ControlStatus => ({
  blockers: [
    "US_ORDER_DISABLED",
    "READ_ONLY_ENABLED",
    "SERVER_CONFIRM_NOT_CONFIGURED",
    "LIVE_ORDER_UNLOCK_REQUIRED",
    "LIVE_RUNNER_NOT_READY",
  ],
  team2Blockers: [],
  legacyUnresolved: 0,
  sessionKeeper: { expiresAt: iso(60 * 47), lastRenewedAt: iso(-60 * 13), lastError: null, backoffUntil: null },
});

export const mockTop10 = (): Top10Universe => ({
  asOf: iso(-20),
  validUntil: iso(280),
  items: [
    { rank: 1, symbol: "PLCE", exchange: "NASDAQ", name: "Children's Place", last: 1.02, changePct: 38.4, state: "subscribed" },
    { rank: 2, symbol: "NXXT", exchange: "NASDAQ", name: "NextNRG", last: 1.79, changePct: 27.1, state: "eligible" },
    { rank: 3, symbol: "SOUN", exchange: "NASDAQ", name: "SoundHound AI", last: 12.48, changePct: 14.2, state: "subscribed" },
    { rank: 4, symbol: "AIOK", exchange: "NASDAQ", name: "AIOK Holdings", last: 0.84, changePct: 12.9, state: "pending" },
    { rank: 5, symbol: "RGTI", exchange: "NASDAQ", name: "Rigetti Computing", last: 18.31, changePct: 11.6, state: "eligible" },
    { rank: 6, symbol: "QSI", exchange: "NASDAQ", name: "Quantum-Si", last: 2.14, changePct: 9.8, state: "excluded", excludeReason: "거래대금 미달" },
    { rank: 7, symbol: "BBAI", exchange: "NYSE", name: "BigBear.ai", last: 6.07, changePct: 8.7, state: "eligible" },
    { rank: 8, symbol: "OPEN", exchange: "NASDAQ", name: "Opendoor", last: 3.42, changePct: 7.3, state: "excluded", excludeReason: "스프레드 초과" },
    { rank: 9, symbol: "LCID", exchange: "NASDAQ", name: "Lucid Group", last: 21.66, changePct: 6.1, state: "eligible" },
    { rank: 10, symbol: "WULF", exchange: "NASDAQ", name: "TeraWulf", last: 11.9, changePct: 5.4, state: "pending" },
  ],
});

/** 결정적 의사난수 (종목별 고정 시계열) */
function seeded(symbol: string) {
  let h = 0;
  for (const c of symbol) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return () => ((h = (h * 1664525 + 1013904223) >>> 0) / 2 ** 32);
}

export const mockQuote = (symbol: string): Quote => {
  const item = mockTop10().items.find((i) => i.symbol === symbol) ?? mockTop10().items[0];
  const rnd = seeded(symbol);
  const tick = item.last >= 1 ? 0.01 : 0.0001;
  const ticks = Array.from({ length: 90 }, (_, i) => {
    const drift = (i / 90) * item.last * (item.changePct / 100) * 0.4;
    const p = item.last - item.last * (item.changePct / 100) * 0.4 + drift + (rnd() - 0.5) * item.last * 0.02;
    return { t: iso(-(90 - i) * 4), p: Math.max(tick, +p.toFixed(item.last >= 1 ? 2 : 4)) };
  });
  ticks[ticks.length - 1].p = item.last;
  // NXXT는 인계서 P1 관측(호가 역전)을 재현
  const inverted = symbol === "NXXT";
  const bid = inverted ? 1.97 : +(item.last - tick).toFixed(4);
  const ask = inverted ? 1.61 : +(item.last + (symbol === "OPEN" ? tick * 6 : 0)).toFixed(4);
  return {
    symbol: item.symbol, exchange: item.exchange, last: item.last, changePct: item.changePct,
    bid, ask, bidSize: Math.round(rnd() * 9000 + 500), askSize: Math.round(rnd() * 9000 + 500),
    strength: Math.round(80 + rnd() * 90), receivedAt: iso(-1), ticks,
  };
};

export const mockPlan = (symbol: string): Team2Plan => ({
  symbol,
  steps: [
    { label: "TOP10 편입", done: true },
    { label: "실시간 구독", done: symbol !== "AIOK" && symbol !== "WULF" },
    { label: "1분 스퀴즈 신호", done: false },
    { label: "자금 예약", done: false },
    { label: "주문 제출", done: false },
  ],
  criteria: [
    { key: "gain", label: "당일 상승률 ≥ 5%", pass: true, detail: "TOP10 기준 충족" },
    { key: "strength", label: "체결강도 ≥ 120", pass: null, detail: "실시간 수신 후 판정" },
    { key: "spread", label: "스프레드", pass: null, detail: "아래 스프레드 평가 참조" },
    { key: "cap", label: "1주 ≤ 30만원", pass: true, detail: "진입 한도 내" },
  ],
  blockers: ["US_ORDER_DISABLED", "READ_ONLY_ENABLED", "LIVE_RUNNER_NOT_READY"],
  nextAction: "잠금 상태 — 관찰만 수행. 실주문 해제는 사용자가 live_on.sh로 직접 진행",
});

export const mockPositions = (): Position[] => [];

/**
 * 검증 시나리오:
 *  - "pending" : 11/12 현재 실상황 (체결 없음, 잔고 0, 미체결 조회 502)
 *  - "pass"    : 1주 매수→매도 왕복이 원장·잔고와 일치하는 정상 사례
 *  - "mismatch": 원장 무귀속 + 잔고 불일치 사례 (2팀 차단 원인과 같은 유형)
 */
export type VerificationScenario = "pending" | "pass" | "mismatch";

export const mockVerification = (scenario: VerificationScenario): VerificationInput => {
  if (scenario === "pending") {
    return { symbol: "PLCE", fills: [], ledger: [], reservations: [], brokerHoldingQty: 0, openOrders: null };
  }
  const fills = [
    { orderNo: "***201", side: "buy" as const, symbol: "PLCE", qty: 1, price: 1.02, filledAt: iso(-600) },
    { orderNo: "***202", side: "sell" as const, symbol: "PLCE", qty: 1, price: 1.05, filledAt: iso(-120) },
  ];
  if (scenario === "pass") {
    return {
      symbol: "PLCE",
      fills,
      ledger: [
        { id: 21, orderNo: "***201", side: "buy", symbol: "PLCE", qty: 1, status: "filled", filledQty: 1, accountScope: "team2" },
        { id: 22, orderNo: "***202", side: "sell", symbol: "PLCE", qty: 1, status: "filled", filledQty: 1, accountScope: "team2" },
      ],
      reservations: [{ id: 9, symbol: "PLCE", status: "closed" }],
      brokerHoldingQty: 0,
      openOrders: [],
    };
  }
  return {
    symbol: "PLCE",
    fills: fills.slice(0, 1),
    ledger: [
      { id: 21, orderNo: "***201", side: "buy", symbol: "PLCE", qty: 1, status: "filled", filledQty: 1, accountScope: null },
      { id: 22, orderNo: "***202", side: "sell", symbol: "PLCE", qty: 1, status: "filled", filledQty: 1, accountScope: "team2" },
    ],
    reservations: [{ id: 9, symbol: "PLCE", status: "filled" }],
    brokerHoldingQty: 0,
    openOrders: [],
  };
};
