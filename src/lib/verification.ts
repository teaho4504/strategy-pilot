import type {
  ControlStatus, GateCode, HealthStatus, VerificationCheck, VerificationInput, VerificationResult,
} from "@/types/us";

/* ------------------------------------------------------------------ */
/* 주문 게이트 요약                                                     */
/* ------------------------------------------------------------------ */

/** 잠금 설정에서 "의도된" 차단 사유. 이것만 남아 있으면 상태는 locked(정상 잠금). */
export const INTENDED_LOCK_CODES: GateCode[] = [
  "US_ORDER_DISABLED",
  "READ_ONLY_ENABLED",
  "SERVER_CONFIRM_NOT_CONFIGURED",
  "LIVE_ORDER_UNLOCK_REQUIRED",
  "LIVE_RUNNER_NOT_READY",
  "EMERGENCY_STOP_ON",
];

export const GATE_LABELS: Record<string, string> = {
  US_ORDER_DISABLED: "미국 주문 비활성",
  READ_ONLY_ENABLED: "읽기 전용",
  SERVER_CONFIRM_NOT_CONFIGURED: "서버 확인 미설정",
  LIVE_ORDER_UNLOCK_REQUIRED: "실주문 잠금 해제 필요",
  LIVE_RUNNER_NOT_READY: "러너 미준비",
  EMERGENCY_STOP_ON: "비상 차단 ON",
  EXIT_SINGLE_SHARE_EXCEEDS_CAP: "1주 > 한도 (청산 차단 위험)",
  LEGACY_ORDER_OWNERSHIP: "구형 주문 귀속 미확인",
  SESSION_EXPIRING: "세션 만료 임박",
};

export type GateMode = "locked" | "blocked" | "armed";

export interface GateSummary {
  mode: GateMode;
  intended: GateCode[];
  unexpected: GateCode[];
}

/**
 * locked  : 의도된 잠금 사유만 존재 (기본 운영 상태)
 * blocked : 의도되지 않은 차단 사유 존재 (2팀 귀속, 세션 등) → 조치 필요
 * armed   : 차단 사유 없음 → 실주문 가능 상태 (사용자가 직접 해제한 경우만)
 */
export function summarizeGate(health: HealthStatus, control: ControlStatus): GateSummary {
  const all = new Set<GateCode>([...control.blockers, ...control.team2Blockers]);
  if (health.emergencyStop) all.add("EMERGENCY_STOP_ON");
  if (health.readOnly) all.add("READ_ONLY_ENABLED");
  if (control.legacyUnresolved > 0) all.add("LEGACY_ORDER_OWNERSHIP");
  const list = [...all];
  const intended = list.filter((c) => INTENDED_LOCK_CODES.includes(c));
  const unexpected = list.filter((c) => !INTENDED_LOCK_CODES.includes(c));
  const mode: GateMode = unexpected.length ? "blocked" : intended.length ? "locked" : "armed";
  return { mode, intended, unexpected };
}

/* ------------------------------------------------------------------ */
/* 세션 키퍼 (P0-1/P0-3)                                                */
/* ------------------------------------------------------------------ */

export type SessionHealth = "none" | "ok" | "renew_window" | "expired" | "backoff";

export function sessionHealth(
  expiresAt: string | null,
  now: Date,
  backoffUntil: string | null = null,
  marginSeconds = 600,
): { state: SessionHealth; secondsLeft: number | null } {
  if (!expiresAt) return { state: "none", secondsLeft: null };
  const left = Math.floor((new Date(expiresAt).getTime() - now.getTime()) / 1000);
  if (left <= 0) return { state: "expired", secondsLeft: left };
  if (backoffUntil && new Date(backoffUntil).getTime() > now.getTime()) return { state: "backoff", secondsLeft: left };
  if (left <= marginSeconds) return { state: "renew_window", secondsLeft: left };
  return { state: "ok", secondsLeft: left };
}

/* ------------------------------------------------------------------ */
/* 스프레드 규칙 (P1: 0.1% 고정 기준 → 저가주 틱 기준)                   */
/* ------------------------------------------------------------------ */

/** 미국 주식 최소 호가 단위: $1 이상 0.01, 미만 0.0001 */
export const usTickSize = (price: number) => (price >= 1 ? 0.01 : 0.0001);

export interface SpreadEval {
  spreadPct: number | null;
  ticks: number | null;
  ok: boolean;
  rule: "pct" | "tick" | "invalid";
  reason: string;
}

/**
 * $10 이상은 기존 0.1% 기준, $10 미만은 maxTicks 틱 이내면 통과.
 * 호가 역전(bid > ask)·0 이하 값은 데이터 오류로 탈락 (P1 NXXT 사례).
 */
export function evaluateSpread(bid: number, ask: number, opts = { pctMax: 0.1, maxTicks: 2, tickRuleBelow: 10 }): SpreadEval {
  if (!(bid > 0) || !(ask > 0)) return { spreadPct: null, ticks: null, ok: false, rule: "invalid", reason: "호가 없음" };
  if (bid > ask) return { spreadPct: null, ticks: null, ok: false, rule: "invalid", reason: `호가 역전 (bid ${bid} > ask ${ask})` };
  const mid = (bid + ask) / 2;
  const spreadPct = ((ask - bid) / mid) * 100;
  const ticks = Math.round((ask - bid) / usTickSize(bid));
  if (mid >= opts.tickRuleBelow) {
    const ok = spreadPct <= opts.pctMax;
    return { spreadPct, ticks, ok, rule: "pct", reason: ok ? `${spreadPct.toFixed(3)}% ≤ ${opts.pctMax}%` : `${spreadPct.toFixed(3)}% > ${opts.pctMax}%` };
  }
  const ok = ticks <= opts.maxTicks;
  return { spreadPct, ticks, ok, rule: "tick", reason: ok ? `${ticks}틱 ≤ ${opts.maxTicks}틱` : `${ticks}틱 > ${opts.maxTicks}틱` };
}

/* ------------------------------------------------------------------ */
/* 실매매 체결 검증: 매수 → 매도 → 잔고 → 원장 일치                       */
/* ------------------------------------------------------------------ */

const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0);

export function verifyLiveCycle(input: VerificationInput): VerificationResult {
  const { symbol } = input;
  const fills = input.fills.filter((f) => f.symbol === symbol);
  const buys = fills.filter((f) => f.side === "buy");
  const sells = fills.filter((f) => f.side === "sell");
  const buyQty = sum(buys.map((f) => f.qty));
  const sellQty = sum(sells.map((f) => f.qty));
  const ledger = input.ledger.filter((l) => l.symbol === symbol);
  const checks: VerificationCheck[] = [];

  checks.push(
    buys.length
      ? { key: "buy_fill", label: "매수 체결", state: "pass", detail: `${buys.length}건 · ${buyQty}주` }
      : { key: "buy_fill", label: "매수 체결", state: "pending", detail: "브로커 매수 체결 없음" },
  );

  checks.push(
    !sells.length
      ? { key: "sell_fill", label: "매도 체결", state: "pending", detail: "브로커 매도 체결 없음" }
      : sellQty > buyQty
        ? { key: "sell_fill", label: "매도 체결", state: "fail", detail: `매도 ${sellQty}주 > 매수 ${buyQty}주` }
        : { key: "sell_fill", label: "매도 체결", state: sellQty === buyQty ? "pass" : "pending", detail: `${sells.length}건 · ${sellQty}/${buyQty}주` },
  );

  // 원장 ↔ 브로커 주문번호·수량 대조
  const mismatches: string[] = [];
  for (const f of fills) {
    const row = ledger.find((l) => l.orderNo === f.orderNo && l.side === f.side);
    if (!row) mismatches.push(`${f.orderNo} 원장 누락`);
    else if (row.filledQty !== f.qty) mismatches.push(`${f.orderNo} 수량 ${row.filledQty}≠${f.qty}`);
  }
  for (const l of ledger) {
    if (l.filledQty > 0 && !fills.some((f) => f.orderNo === l.orderNo && f.side === l.side)) {
      mismatches.push(`${l.orderNo} 브로커 체결 없음(원장 ${l.filledQty}주)`);
    }
  }
  checks.push(
    !fills.length && !ledger.length
      ? { key: "ledger_match", label: "원장 ↔ 체결 일치", state: "pending", detail: "대조할 체결 없음" }
      : mismatches.length
        ? { key: "ledger_match", label: "원장 ↔ 체결 일치", state: "fail", detail: mismatches.join(", ") }
        : { key: "ledger_match", label: "원장 ↔ 체결 일치", state: "pass", detail: `${fills.length}건 일치` },
  );

  const unscoped = ledger.filter((l) => l.side === "buy" && l.filledQty > 0 && !l.accountScope);
  checks.push(
    unscoped.length
      ? { key: "account_scope", label: "계좌 귀속", state: "fail", detail: `무귀속 매수 ${unscoped.map((l) => `#${l.id}`).join(", ")}` }
      : { key: "account_scope", label: "계좌 귀속", state: ledger.length ? "pass" : "pending", detail: ledger.length ? "모든 체결 귀속됨" : "원장 없음" },
  );

  const expectedHolding = buyQty - sellQty;
  checks.push(
    input.brokerHoldingQty === null
      ? { key: "balance", label: "잔고 일치", state: "pending", detail: "잔고 조회 실패" }
      : input.brokerHoldingQty === expectedHolding
        ? { key: "balance", label: "잔고 일치", state: buys.length ? "pass" : "pending", detail: `잔고 ${input.brokerHoldingQty}주 = 체결 순수량 ${expectedHolding}주` }
        : { key: "balance", label: "잔고 일치", state: "fail", detail: `잔고 ${input.brokerHoldingQty}주 ≠ 체결 순수량 ${expectedHolding}주` },
  );

  const open = input.openOrders?.filter((o) => o.symbol === symbol) ?? null;
  checks.push(
    open === null
      ? { key: "open_orders", label: "미체결 없음", state: "pending", detail: "미체결 조회 실패 (예: HTTP 502)" }
      : open.length
        ? { key: "open_orders", label: "미체결 없음", state: "fail", detail: `미체결 ${open.length}건` }
        : { key: "open_orders", label: "미체결 없음", state: "pass", detail: "미체결 0건" },
  );

  const res = input.reservations.filter((r) => r.symbol === symbol && ["reserved", "submitted", "filled"].includes(r.status));
  checks.push(
    res.length && expectedHolding === 0 && sells.length
      ? { key: "reservation", label: "자금 예약 종결", state: "fail", detail: `열린 예약 ${res.map((r) => `#${r.id}(${r.status})`).join(", ")}` }
      : { key: "reservation", label: "자금 예약 종결", state: sells.length ? "pass" : "pending", detail: res.length ? `열린 예약 ${res.length}건` : "열린 예약 없음" },
  );

  const realizedPnl = buys.length && sellQty === buyQty && sellQty > 0
    ? sum(sells.map((f) => f.qty * f.price)) - sum(buys.map((f) => f.qty * f.price))
    : null;

  const verdict: VerificationResult["verdict"] = checks.some((c) => c.state === "fail")
    ? "mismatch"
    : checks.every((c) => c.state === "pass")
      ? "verified"
      : "incomplete";

  return { symbol, verdict, checks, realizedPnl };
}
