import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Plus, Pause, Play, ChevronRight } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { TopBar } from "@/components/layout/TopBar";
import { Card } from "@/components/common/Card";
import { StatusBadge } from "@/components/common/DemoBadge";
import { DeltaPct } from "@/components/common/DeltaPct";
import { queryKeys, strategyAdapter, useStrategiesQuery } from "@/services/adapters";
import { won, relTime } from "@/lib/format";
import type { StrategyStatus } from "@/types";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

const TABS: { key: "all" | StrategyStatus; label: string }[] = [
  { key: "all", label: "전체" },
  { key: "running", label: "실행 중" },
  { key: "idle", label: "대기" },
  { key: "paused", label: "일시정지" },
  { key: "error", label: "오류" },
];

export default function Strategies() {
  const queryClient = useQueryClient();
  const { data: list = [], isLoading, isError } = useStrategiesQuery();
  const [tab, setTab] = useState<(typeof TABS)[number]["key"]>("all");

  const filtered = useMemo(
    () => (tab === "all" ? list : list.filter((s) => s.status === tab)),
    [list, tab]
  );

  const toggle = async (id: string) => {
    const current = list.find((s) => s.id === id);
    if (!current) return;

    if (current.status === "error") {
      toast.error(`${current.name}: 오류 상태입니다. 설정에서 점검 필요`);
      return;
    }

    const next = current.status === "running" ? "paused" : "running";
    await strategyAdapter.toggle(id, next);
    queryClient.invalidateQueries({ queryKey: queryKeys.strategies });
    toast[next === "running" ? "success" : "message"](`${current.name} ${next === "running" ? "시작" : "일시정지"} (데모)`);
  };

  return (
    <>
      <TopBar />
      <main className="space-y-3 p-4 animate-fade-in">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-semibold">전략</h1>
          <Button asChild size="sm" className="rounded-full">
            <Link to="/strategies/builder">
              <Plus className="mr-1 h-4 w-4" /> 전략 생성
            </Link>
          </Button>
        </div>

        <div className="no-scrollbar -mx-4 overflow-x-auto px-4">
          <div className="flex w-max gap-2">
            {TABS.map((t) => {
              const active = tab === t.key;
              const count = t.key === "all" ? list.length : list.filter((s) => s.status === t.key).length;
              return (
                <button
                  key={t.key}
                  onClick={() => setTab(t.key)}
                  className={cn(
                    "rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
                    active
                      ? "border-primary/40 bg-primary/15 text-primary"
                      : "border-border bg-surface-2 text-muted-foreground hover:text-foreground"
                  )}
                >
                  {t.label} <span className="ml-1 text-[10.5px] opacity-70 num">{count}</span>
                </button>
              );
            })}
          </div>
        </div>

        <div className="space-y-3">
          {isLoading && (
            <Card className="text-center text-sm text-muted-foreground">전략 데이터를 불러오는 중입니다.</Card>
          )}
          {isError && (
            <Card className="text-center text-sm text-danger">전략 데이터를 불러오지 못했습니다.</Card>
          )}
          {!isLoading && !isError && filtered.length === 0 && (
            <Card className="text-center text-sm text-muted-foreground">조건에 해당하는 전략이 없습니다.</Card>
          )}
          {filtered.map((s) => (
            <Card key={s.id} className="space-y-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <StatusBadge status={s.status} />
                    <h3 className="truncate text-base font-semibold">{s.name}</h3>
                  </div>
                  <p className="mt-1 truncate text-[12px] text-muted-foreground">
                    {s.universe} · {s.timeframe}
                  </p>
                </div>
                <DeltaPct value={s.dayReturnPct} className="text-base shrink-0" />
              </div>

              <div className="grid grid-cols-3 gap-2 text-center">
                <Info label="신호" value={`${s.signalsToday}`} />
                <Info label="체결" value={`${s.fillsToday}`} />
                <Info label="마지막 신호" value={relTime(s.lastSignalAt)} />
              </div>

              <div className="flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
                <span>최대 손실 한도 · <span className="text-foreground num">{won(s.maxLossLimit)}</span></span>
                <Link to="/strategies/builder" className="inline-flex items-center text-foreground hover:text-primary">
                  상세 <ChevronRight className="h-3.5 w-3.5" />
                </Link>
              </div>

              <Button
                variant={s.status === "running" ? "secondary" : "default"}
                className="w-full"
                onClick={() => toggle(s.id)}
              >
                {s.status === "running" ? <><Pause className="mr-1.5 h-4 w-4" /> 일시정지</> : <><Play className="mr-1.5 h-4 w-4" /> 시작</>}
              </Button>
            </Card>
          ))}
        </div>
      </main>
    </>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-surface-3/40 px-2 py-2">
      <div className="text-[10.5px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-sm font-semibold num">{value}</div>
    </div>
  );
}
