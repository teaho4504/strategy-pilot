import { cn } from "@/lib/utils";
import type { Top10Item } from "@/types/us";
import { useNow, useTop10 } from "./hooks";

const STATE_CHIP: Record<Top10Item["state"], { label: string; cls: string }> = {
  eligible: { label: "적격", cls: "border-primary/50 text-primary" },
  subscribed: { label: "구독", cls: "border-success/50 text-success" },
  pending: { label: "구독 대기", cls: "border-warning/50 text-warning" },
  excluded: { label: "제외", cls: "border-border text-muted-foreground" },
};

export function Top10Watch({ selected, onSelect }: { selected: string | null; onSelect: (i: Top10Item) => void }) {
  const q = useTop10();
  const now = useNow(5000);
  const expired = q.data ? new Date(q.data.validUntil).getTime() < now.getTime() : false;

  return (
    <section className="wts-panel" aria-label="TOP10 관찰 종목">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold">2팀 TOP10</h2>
        {q.data && <span className="text-[11px] text-muted-foreground">{expired ? "순위 만료" : "5초 갱신"}</span>}
      </div>
      {expired ? (
        <p className="py-6 text-center text-xs text-muted-foreground">유효기간이 지난 순위는 표시하지 않습니다.</p>
      ) : (
        <ul className="space-y-1">
          {q.data?.items.map((i) => (
            <li key={i.symbol}>
              <button
                type="button"
                onClick={() => onSelect(i)}
                aria-pressed={selected === i.symbol}
                className={cn(
                  "flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-muted",
                  selected === i.symbol && "bg-muted ring-1 ring-primary/50",
                )}
              >
                <span className="w-4 text-[11px] text-muted-foreground num">{i.rank}</span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[13px] font-semibold leading-tight">{i.symbol}</span>
                  <span className="block truncate text-[11px] text-muted-foreground">{i.excludeReason ?? i.name}</span>
                </span>
                <span className="text-right">
                  <span className="block text-[13px] num">${i.last.toFixed(i.last >= 1 ? 2 : 4)}</span>
                  <span className={cn("block text-[11px] num", i.changePct >= 0 ? "text-up" : "text-down")}>
                    {i.changePct >= 0 ? "+" : ""}{i.changePct.toFixed(1)}%
                  </span>
                </span>
                <span className={cn("chip shrink-0", STATE_CHIP[i.state].cls)}>{STATE_CHIP[i.state].label}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
