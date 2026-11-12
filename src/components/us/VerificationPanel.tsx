import { Check, Circle, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { verifyLiveCycle } from "@/lib/verification";
import type { VerificationInput } from "@/types/us";

const VERDICT = {
  verified: { label: "검증 완료", cls: "border-success/50 text-success" },
  mismatch: { label: "불일치", cls: "border-danger/50 text-danger" },
  incomplete: { label: "미완료", cls: "border-warning/50 text-warning" },
} as const;

export function VerificationPanel({ input, compact }: { input: VerificationInput; compact?: boolean }) {
  const r = verifyLiveCycle(input);
  return (
    <section className="wts-panel space-y-2" aria-label="실매매 체결 검증">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">실매매 체결 검증 · {r.symbol}</h2>
        <span data-testid="verdict" className={cn("chip", VERDICT[r.verdict].cls)}>{VERDICT[r.verdict].label}</span>
      </div>
      <ul className="space-y-1">
        {r.checks.map((c) => (
          <li key={c.key} className="flex items-start gap-2 text-xs">
            {c.state === "pass" ? <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" /> : c.state === "fail" ? <X className="mt-0.5 h-3.5 w-3.5 shrink-0 text-danger" /> : <Circle className="mt-0.5 h-3 w-3 shrink-0 text-muted-foreground" />}
            <span className="w-28 shrink-0">{c.label}</span>
            {!compact && <span className="text-muted-foreground">{c.detail}</span>}
          </li>
        ))}
      </ul>
      {r.realizedPnl !== null && (
        <p className={cn("text-xs num", r.realizedPnl >= 0 ? "text-up" : "text-down")}>실현손익 ${r.realizedPnl.toFixed(4)} (수수료 제외)</p>
      )}
    </section>
  );
}
