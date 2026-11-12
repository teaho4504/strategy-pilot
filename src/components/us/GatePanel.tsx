import { cn } from "@/lib/utils";
import { GATE_LABELS, sessionHealth, summarizeGate, type SessionHealth } from "@/lib/verification";
import { useControl, useHealth, useNow } from "./hooks";

const fmtLeft = (s: number) => (s < 0 ? `${Math.floor(-s / 60)}분 경과` : `${Math.floor(s / 60)}분 ${s % 60}초`);

const SESSION_LABEL: Record<SessionHealth, string> = {
  ok: "정상",
  renew_window: "갱신 구간",
  backoff: "재시도 대기",
  expired: "만료 — 재로그인 필요",
  none: "세션 없음",
};

export function GatePanel() {
  const health = useHealth();
  const control = useControl();
  const now = useNow();
  if (!health.data || !control.data) return <section className="wts-panel text-xs text-muted-foreground">서버 상태 조회 중…</section>;
  const h = health.data.data;
  const c = control.data.data;
  const gate = summarizeGate(h, c);
  const sk = c.sessionKeeper;
  const sess = sessionHealth(sk.expiresAt, now, sk.backoffUntil);
  const err = health.data.error ?? control.data.error;

  return (
    <section className="wts-panel space-y-3" aria-label="주문 게이트">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">주문 게이트</h2>
        <span className="text-[10.5px] text-muted-foreground">출처 {health.data.source}</span>
      </div>
      {err && <p className="rounded-lg border border-danger/40 px-3 py-2 text-xs text-danger">실서버 조회 실패: {err}</p>}

      <div className="grid grid-cols-3 gap-1.5 text-center text-[11px]">
        <Flag label="주문" on={h.orderEnabled} />
        <Flag label="비상 차단" on={h.emergencyStop} invert />
        <Flag label="관리자" on={h.adminEnabled} />
        <Flag label="러너" on={h.runnerEnabled} />
        <Flag label="읽기 전용" on={h.readOnly} invert />
        <div className={cn("rounded-md border px-1.5 py-1", c.team2Blockers.length || c.legacyUnresolved ? "border-danger/50 text-danger" : "border-border text-muted-foreground")}>
          2팀 귀속 {c.team2Blockers.length || c.legacyUnresolved ? "차단" : "정상"}
        </div>
      </div>

      <div>
        <div className="mb-1 text-[11px] text-muted-foreground">조치 필요 ({gate.unexpected.length})</div>
        {gate.unexpected.length ? (
          <div className="flex flex-wrap gap-1.5">{gate.unexpected.map((g) => <span key={g} className="chip border-danger/50 text-danger">{GATE_LABELS[g] ?? g}</span>)}</div>
        ) : <p className="text-xs text-success">없음 — 2팀 차단 해제 상태</p>}
      </div>
      <div>
        <div className="mb-1 text-[11px] text-muted-foreground">의도된 잠금 ({gate.intended.length})</div>
        <div className="flex flex-wrap gap-1.5">{gate.intended.map((g) => <span key={g} className="chip">{GATE_LABELS[g] ?? g}</span>)}</div>
      </div>

      <div className="rounded-lg bg-surface-1 px-3 py-2 text-xs" data-testid="session-keeper">
        <div className="flex justify-between">
          <span>세션 키퍼</span>
          <span className={cn(
            sess.state === "ok" && "text-success",
            (sess.state === "renew_window" || sess.state === "backoff") && "text-warning",
            (sess.state === "expired" || sess.state === "none") && "text-danger",
          )}>
            {SESSION_LABEL[sess.state]}
          </span>
        </div>
        {sess.secondsLeft !== null && <div className="mt-0.5 text-muted-foreground num">만료까지 {fmtLeft(sess.secondsLeft)}</div>}
        {sk.lastError && <div className="mt-0.5 text-danger">{sk.lastError}</div>}
      </div>
      <p className="text-[10.5px] leading-relaxed text-muted-foreground">
        이 화면에는 주문·관리자 ON 버튼이 없습니다. 실주문 해제는 Mac에서 live_on.sh 실행 후 로컬 대시보드에서 사용자가 직접 수행합니다.
      </p>
    </section>
  );
}

function Flag({ label, on, invert }: { label: string; on: boolean; invert?: boolean }) {
  const safe = invert ? on : !on; // 잠금 쪽이 safe
  return (
    <div className={cn("rounded-md border px-1.5 py-1", safe ? "border-border text-muted-foreground" : "border-up/50 text-up")}>
      {label} {on ? "ON" : "OFF"}
    </div>
  );
}
