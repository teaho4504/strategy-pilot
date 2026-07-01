import { useQuery } from "@tanstack/react-query";
import { Card, SectionTitle } from "@/components/common/Card";
import { timeKR } from "@/lib/format";
import { CheckCircle2, Send, Zap, ShieldAlert } from "lucide-react";
import { cn } from "@/lib/utils";
import { queryKeys, timelineAdapter } from "@/services/adapters";

const META = {
  signal: { icon: Zap, tone: "text-accent", bg: "bg-accent/10", label: "신호" },
  order:  { icon: Send, tone: "text-foreground", bg: "bg-muted", label: "주문" },
  fill:   { icon: CheckCircle2, tone: "text-success", bg: "bg-success/10", label: "체결" },
  risk:   { icon: ShieldAlert, tone: "text-warning", bg: "bg-warning-soft", label: "리스크" },
} as const;

export function TimelineCard() {
  const { data: timeline = [], isLoading } = useQuery({
    queryKey: queryKeys.timeline,
    queryFn: timelineAdapter.recent,
  });

  return (
    <Card>
      <SectionTitle title="오늘의 타임라인" sub={isLoading ? "이벤트 조회 중" : "신호 → 주문 → 체결 → 리스크"} />
      <ol className="relative space-y-3 pl-1">
        {timeline.map((e, i) => {
          const m = META[e.kind];
          const Icon = m.icon;
          return (
            <li key={e.id} className="flex gap-3">
              <div className="flex flex-col items-center">
                <span className={cn("grid h-8 w-8 place-items-center rounded-full", m.bg, m.tone)}>
                  <Icon className="h-4 w-4" />
                </span>
                {i < timeline.length - 1 && <span className="mt-1 w-px flex-1 bg-border" />}
              </div>
              <div className="flex-1 pb-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium text-foreground">{e.title}</span>
                  <span className="text-[11px] text-muted-foreground num">{timeKR(e.time)}</span>
                </div>
                <div className="text-[12px] text-muted-foreground">
                  {e.detail}
                  {e.strategyName && <span className="ml-1 text-muted-foreground/70">· {e.strategyName}</span>}
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}
