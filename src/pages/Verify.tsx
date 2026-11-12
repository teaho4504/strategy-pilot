import { useState } from "react";
import { ConsoleTopBar } from "@/components/us/ConsoleTopBar";
import { VerificationPanel } from "@/components/us/VerificationPanel";
import { mockVerification, type VerificationScenario } from "@/services/us/mock";
import { cn } from "@/lib/utils";

const SCENARIOS: { key: VerificationScenario; label: string; desc: string }[] = [
  { key: "pending", label: "현재 (11/12)", desc: "체결 없음 · 잔고 0 · 미체결 조회 502 — 실매매 검증 미완료 상태" },
  { key: "pass", label: "정상 왕복", desc: "1주 매수→매도, 원장·잔고·예약 모두 일치" },
  { key: "mismatch", label: "불일치 예시", desc: "무귀속 매수 · 브로커에 없는 매도 원장 · 열린 예약" },
];

const RUNBOOK = [
  "Mac: live_off.sh 로 재시작해 세션 키퍼 코드 로드 → /api/health readOnly=true 확인",
  "P0-2·P0-4 수정·테스트 통과 확인 (시세·체결 감시 토큰 일관성, 청산 precheck 분리)",
  "사용자가 직접 live_on.sh 실행 ('실매매 진행' 입력) → UI에서 PIN·관리자 ON·2팀·자동매매 ON",
  "$10 미만·1주·한도 내 종목 1건만 체결 → 즉시 매도(또는 손절 경로) 확인",
  "브로커 체결내역·잔고·미체결 조회 결과를 이 화면의 7개 항목과 대조",
  "live_off.sh 로 즉시 잠금 복귀 → 검증 결과를 인계서에 기록",
];

export default function Verify() {
  const [s, setS] = useState<VerificationScenario>("pending");
  return (
    <>
      <ConsoleTopBar />
      <main className="mx-auto max-w-3xl space-y-3 p-3">
        <div className="flex flex-wrap gap-1.5" role="tablist">
          {SCENARIOS.map((x) => (
            <button
              key={x.key}
              role="tab"
              aria-selected={s === x.key}
              onClick={() => setS(x.key)}
              className={cn("wts-pill", s === x.key && "border-primary text-primary")}
            >
              {x.label}
            </button>
          ))}
        </div>
        <p className="text-xs text-muted-foreground">{SCENARIOS.find((x) => x.key === s)?.desc}</p>
        <VerificationPanel input={mockVerification(s)} />
        <section className="wts-panel">
          <h2 className="mb-2 text-sm font-semibold">실매매 1회 검증 절차 (사용자 수행)</h2>
          <ol className="list-decimal space-y-1 pl-5 text-xs text-muted-foreground">
            {RUNBOOK.map((r) => <li key={r}>{r}</li>)}
          </ol>
          <p className="mt-2 text-[10.5px] text-warning">이 클라우드 대시보드는 조회 전용이며 주문을 보내지 않습니다.</p>
        </section>
      </main>
    </>
  );
}
