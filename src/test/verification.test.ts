import { describe, expect, it } from "vitest";
import { evaluateSpread, sessionHealth, summarizeGate, verifyLiveCycle } from "@/lib/verification";
import { mockControl, mockHealth, mockVerification } from "@/services/us/mock";
import { normalizeControl, normalizeHealth } from "@/services/us/client";

describe("summarizeGate", () => {
  it("인계서 잠금 설정은 locked (의도된 차단만)", () => {
    const g = summarizeGate(mockHealth(), mockControl());
    expect(g.mode).toBe("locked");
    expect(g.unexpected).toEqual([]);
    expect(g.intended).toContain("EMERGENCY_STOP_ON");
  });
  it("2팀 귀속 차단·구형 미확인 기록은 blocked", () => {
    const g = summarizeGate(mockHealth(), { ...mockControl(), team2Blockers: ["LEGACY_ORDER_OWNERSHIP"], legacyUnresolved: 2 });
    expect(g.mode).toBe("blocked");
    expect(g.unexpected).toContain("LEGACY_ORDER_OWNERSHIP");
  });
  it("차단 없음은 armed", () => {
    const h = { ...mockHealth(), readOnly: false, emergencyStop: false, orderEnabled: true };
    expect(summarizeGate(h, { ...mockControl(), blockers: [] }).mode).toBe("armed");
  });
  it("실서버 빈 응답은 안전측(잠금)으로 정규화", () => {
    const g = summarizeGate(normalizeHealth({}), normalizeControl({}));
    expect(g.mode).toBe("locked");
  });
  it("snake_case 응답도 정규화", () => {
    const h = normalizeHealth({ read_only: false, order_enabled: true, emergency_stop: false });
    expect(h.readOnly).toBe(false);
    expect(h.orderEnabled).toBe(true);
    const c = normalizeControl({ team2_blockers: ["X"], session_keeper: { expires_at: "2026-11-12T13:00:00Z" } });
    expect(c.team2Blockers).toEqual(["X"]);
    expect(c.sessionKeeper.expiresAt).toBe("2026-11-12T13:00:00Z");
  });
});

describe("sessionHealth", () => {
  const now = new Date("2026-11-12T12:00:00Z");
  it("만료 10분 전부터 갱신 구간", () => {
    expect(sessionHealth("2026-11-12T12:30:00Z", now).state).toBe("ok");
    expect(sessionHealth("2026-11-12T12:09:00Z", now).state).toBe("renew_window");
    expect(sessionHealth("2026-11-12T11:59:00Z", now).state).toBe("expired");
    expect(sessionHealth(null, now).state).toBe("none");
  });
  it("백오프 중 표시", () => {
    expect(sessionHealth("2026-11-12T12:05:00Z", now, "2026-11-12T12:00:20Z").state).toBe("backoff");
  });
});

describe("evaluateSpread", () => {
  it("$10 미만 1틱은 틱 기준으로 통과 (PLCE $1.02 사례)", () => {
    const r = evaluateSpread(1.01, 1.02);
    expect(r.rule).toBe("tick");
    expect(r.ticks).toBe(1);
    expect(r.ok).toBe(true);
    expect(r.spreadPct!).toBeGreaterThan(0.9); // 기존 0.1% 기준이면 탈락했던 값
  });
  it("$10 이상은 0.1% 기준", () => {
    expect(evaluateSpread(20.0, 20.01).ok).toBe(true);
    expect(evaluateSpread(12.0, 12.05).ok).toBe(false);
  });
  it("호가 역전은 데이터 오류로 탈락 (NXXT 사례)", () => {
    const r = evaluateSpread(1.97, 1.61);
    expect(r.rule).toBe("invalid");
    expect(r.ok).toBe(false);
  });
});

describe("verifyLiveCycle", () => {
  it("현재 상황은 미완료 (체결 없음, 미체결 조회 실패)", () => {
    const r = verifyLiveCycle(mockVerification("pending"));
    expect(r.verdict).toBe("incomplete");
    expect(r.checks.find((c) => c.key === "open_orders")!.state).toBe("pending");
  });
  it("정상 왕복은 검증 완료 + 실현손익", () => {
    const r = verifyLiveCycle(mockVerification("pass"));
    expect(r.verdict).toBe("verified");
    expect(r.realizedPnl).toBeCloseTo(0.03, 6);
  });
  it("무귀속·원장 단독 체결·열린 예약은 불일치", () => {
    const r = verifyLiveCycle(mockVerification("mismatch"));
    expect(r.verdict).toBe("mismatch");
    const failed = r.checks.filter((c) => c.state === "fail").map((c) => c.key);
    expect(failed).toEqual(expect.arrayContaining(["ledger_match", "account_scope", "balance"]));
  });
  it("잔고 불일치 감지", () => {
    const r = verifyLiveCycle({ ...mockVerification("pass"), brokerHoldingQty: 1 });
    expect(r.checks.find((c) => c.key === "balance")!.state).toBe("fail");
  });
  it("매도 수량이 매수보다 크면 실패", () => {
    const base = mockVerification("pass");
    const r = verifyLiveCycle({ ...base, fills: [...base.fills, { ...base.fills[1], orderNo: "***203" }] });
    expect(r.checks.find((c) => c.key === "sell_fill")!.state).toBe("fail");
  });
});
