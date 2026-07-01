import { useQuery } from "@tanstack/react-query";
import { Card, SectionTitle } from "@/components/common/Card";
import { StatusBadge } from "@/components/common/DemoBadge";
import { DeltaPct } from "@/components/common/DeltaPct";
import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { queryKeys, strategyAdapter } from "@/services/adapters";

export function ActiveStrategiesCard() {
  const { data: strategies = [], isLoading } = useQuery({
    queryKey: queryKeys.strategies,
    queryFn: strategyAdapter.list,
  });
  const running = strategies.filter((s) => s.status === "running").length;
  const totalSignals = strategies.reduce((a, b) => a + b.signalsToday, 0);
  const totalFills = strategies.reduce((a, b) => a + b.fillsToday, 0);

  return (
    <Card>
      <SectionTitle
        title="활성 전략"
        sub={isLoading ? "전략 데이터 조회 중" : undefined}
        action={
          <Link to="/strategies" className="flex items-center gap-0.5 text-xs font-medium text-muted-foreground hover:text-foreground">
            전체보기 <ChevronRight className="h-3.5 w-3.5" />
          </Link>
        }
      />
      <div className="mb-3 grid grid-cols-3 gap-2">
        <Mini label="실행 중" value={`${running}`} />
        <Mini label="오늘 신호" value={`${totalSignals}`} />
        <Mini label="오늘 체결" value={`${totalFills}`} />
      </div>
      <ul className="space-y-2">
        {strategies.slice(0, 3).map((s) => (
          <li key={s.id}>
            <Link
              to={`/strategies`}
              className="flex items-center justify-between gap-3 rounded-xl border border-border bg-surface-3/40 p-3 hover:border-border-strong"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <StatusBadge status={s.status} />
                  <span className="truncate text-sm font-semibold">{s.name}</span>
                </div>
                <div className="mt-1 truncate text-[11px] text-muted-foreground">{s.universe}</div>
              </div>
              <DeltaPct value={s.dayReturnPct} />
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border bg-surface-3/40 px-3 py-2.5">
      <div className="text-[10.5px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-lg font-semibold num">{value}</div>
    </div>
  );
}
