import { Lock, ShieldAlert, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";
import { liveConfigured } from "@/services/us/client";
import { summarizeGate } from "@/lib/verification";
import { useControl, useHealth, useNow } from "./hooks";

const etFmt = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
});

export function ConsoleTopBar() {
  const now = useNow();
  const health = useHealth();
  const control = useControl();
  const gate = health.data && control.data ? summarizeGate(health.data.data, control.data.data) : null;
  const sourceError = health.data?.source === "live-error" || control.data?.source === "live-error";

  return (
    <header className="sticky top-0 z-30 border-b border-border bg-surface-1/90 backdrop-blur">
      <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5" style={{ paddingTop: "calc(env(safe-area-inset-top) + 10px)" }}>
        <div className="flex items-center gap-2">
          <span className="text-[15px] font-semibold tracking-tight">Strategy Pilot</span>
          <span className="wts-pill">{liveConfigured ? "실서버 조회" : "모의 데이터"}</span>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="wts-pill num" data-testid="et-clock">ET {etFmt.format(now)}</span>
          {health.data?.data.readOnly && (
            <span className="wts-pill"><Lock className="h-3 w-3" />읽기 전용</span>
          )}
          {sourceError ? (
            <span className="wts-pill border-danger/50 text-danger"><ShieldAlert className="h-3 w-3" />서버 응답 없음</span>
          ) : gate && (
            <span
              data-testid="gate-pill"
              className={cn(
                "wts-pill",
                gate.mode === "locked" && "border-warning/50 text-warning",
                gate.mode === "blocked" && "border-danger/50 text-danger",
                gate.mode === "armed" && "border-up/60 text-up",
              )}
            >
              {gate.mode === "armed" ? <ShieldCheck className="h-3 w-3" /> : <ShieldAlert className="h-3 w-3" />}
              {gate.mode === "locked" ? "주문 잠금" : gate.mode === "blocked" ? "주문 차단 · 조치 필요" : "실주문 가능"}
            </span>
          )}
        </div>
      </div>
    </header>
  );
}
