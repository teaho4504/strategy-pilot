/**
 * 미국 주식(키움 해외 TR) 운영 콘솔 타입.
 * 실서버(Mac 로컬 FastAPI) 응답 모양을 인계서(2026-11-12 2차) 기준으로 축약했다.
 * 필드가 실서버와 다르면 src/services/us/client.ts 의 normalize* 함수만 고친다.
 */

export type GateCode =
  | "US_ORDER_DISABLED"
  | "READ_ONLY_ENABLED"
  | "SERVER_CONFIRM_NOT_CONFIGURED"
  | "LIVE_ORDER_UNLOCK_REQUIRED"
  | "LIVE_RUNNER_NOT_READY"
  | "EMERGENCY_STOP_ON"
  | "EXIT_SINGLE_SHARE_EXCEEDS_CAP"
  | (string & {});

export interface HealthStatus {
  ok: boolean;
  readOnly: boolean;
  orderEnabled: boolean;
  emergencyStop: boolean;
  adminEnabled: boolean;
  runnerEnabled: boolean;
  serverTime: string; // ISO
}

export interface SessionKeeperStatus {
  /** 세션 토큰 만료 시각 (ISO). null이면 세션 없음 */
  expiresAt: string | null;
  lastRenewedAt: string | null;
  lastError: string | null;
  backoffUntil: string | null;
}

export interface ControlStatus {
  blockers: GateCode[];
  team2Blockers: GateCode[];
  legacyUnresolved: number;
  sessionKeeper: SessionKeeperStatus;
}

export type EligibilityState = "eligible" | "subscribed" | "pending" | "excluded";

export interface Top10Item {
  rank: number;
  symbol: string;
  exchange: "NASDAQ" | "NYSE" | "AMEX" | (string & {});
  name: string;
  last: number;
  changePct: number;
  state: EligibilityState;
  excludeReason?: string;
}

export interface Top10Universe {
  asOf: string;
  validUntil: string;
  items: Top10Item[];
}

export interface Quote {
  symbol: string;
  exchange: string;
  last: number;
  changePct: number;
  bid: number;
  ask: number;
  bidSize: number;
  askSize: number;
  /** 체결강도 (매수체결/매도체결 ×100) */
  strength: number;
  receivedAt: string;
  /** 화면에서 수신한 체결가 (분봉 아님) */
  ticks: { t: string; p: number }[];
}

export interface Team2Criterion {
  key: string;
  label: string;
  pass: boolean | null;
  detail: string;
}

export interface Team2Plan {
  symbol: string;
  steps: { label: string; done: boolean }[];
  criteria: Team2Criterion[];
  blockers: GateCode[];
  nextAction: string;
}

export interface Position {
  symbol: string;
  exchange: string;
  qty: number;
  avgPrice: number;
  last: number;
}

/* ---------- 실매매 체결 검증 (매수→매도→잔고·원장 일치) ---------- */

export type Side = "buy" | "sell";

export interface BrokerFill {
  orderNo: string; // 마스킹된 주문번호 (***101)
  side: Side;
  symbol: string;
  qty: number;
  price: number;
  filledAt: string;
}

export interface LedgerOrderAttempt {
  id: number;
  orderNo: string;
  side: Side;
  symbol: string;
  qty: number;
  status: "submitted" | "filled" | "partially_filled" | "cancelled" | "rejected";
  filledQty: number;
  accountScope: string | null;
}

export interface LedgerReservation {
  id: number;
  symbol: string;
  status: "reserved" | "submitted" | "filled" | "closed" | "released";
}

export interface VerificationInput {
  symbol: string;
  fills: BrokerFill[];
  ledger: LedgerOrderAttempt[];
  reservations: LedgerReservation[];
  /** 브로커 잔고 조회 결과 (검증 대상 종목 보유 수량) */
  brokerHoldingQty: number | null;
  /** 미체결 조회 결과. null이면 조회 실패(예: HTTP 502) */
  openOrders: { orderNo: string; symbol: string }[] | null;
}

export type CheckState = "pass" | "fail" | "pending";

export interface VerificationCheck {
  key: string;
  label: string;
  state: CheckState;
  detail: string;
}

export interface VerificationResult {
  symbol: string;
  verdict: "verified" | "mismatch" | "incomplete";
  checks: VerificationCheck[];
  realizedPnl: number | null;
}
