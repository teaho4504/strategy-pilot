import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { TopBar } from "@/components/layout/TopBar";
import { Card, SectionTitle } from "@/components/common/Card";
import { analyticsAdapter, queryKeys } from "@/services/adapters";
import { won } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  Bar, BarChart, ResponsiveContainer, XAxis, YAxis, Tooltip, Cell,
} from "recharts";

const RANGES = [
  { k: "today", label: "오늘" },
  { k: "7d", label: "7일" },
  { k: "30d", label: "30일" },
  { k: "custom", label: "사용자 지정" },
] as const;

export default function Analytics() {
  const [range, setRange] = useState<(typeof RANGES)[number]["k"]>("7d");
  const { data: a, isLoading } = useQuery({ queryKey: queryKeys.analytics(range), queryFn: () => analyticsAdapter.summary(range) });

  if (!a) {
    return (
      <>
        <TopBar />
        <main className="space-y-3 p-4 animate-fade-in">
          <h1 className="text-xl font-semibold">분석</h1>
          <Card className="text-center text-sm text-muted-foreground">{isLoading ? "분석 데이터 조회 중입니다." : "분석 데이터가 없습니다."}</Card>
        </main>
      </>
    );
  }

  return (
    <>
      <TopBar />
      <main className="space-y-3 p-4 animate-fade-in">
        <h1 className="text-xl font-semibold">분석</h1>

        <div className="grid grid-cols-4 gap-1.5 rounded-xl border border-border bg-surface-2 p-1">
          {RANGES.map((r) => (
            <button
              key={r.k}
              onClick={() => setRange(r.k)}
              className={cn(
                "rounded-lg py-2 text-[12px] font-medium",
                range === r.k ? "bg-surface-3 text-foreground" : "text-muted-foreground"
              )}
            >
              {r.label}
            </button>
          ))}
        </div>

        <Card>
          <SectionTitle title="실현 손익" sub={`기간 · ${RANGES.find((r) => r.k === range)?.label} (데모)`} />
          <div className={cn("text-3xl font-bold num", a.realizedPnl >= 0 ? "text-up" : "text-down")}>
            {won(a.realizedPnl, { sign: true })}
          </div>
          <div className="mt-3 grid grid-cols-3 gap-2">
            <Kpi label="승률" value={`${Math.round(a.winRate * 100)}%`} />
            <Kpi label="평균 익절" value={won(a.avgWin)} tone="up" />
            <Kpi label="평균 손절" value={won(a.avgLoss)} tone="down" />
            <Kpi label="MDD" value={won(a.mdd)} tone="down" />
            <Kpi label="평균 보유" value={`${a.avgHoldMin}분`} />
            <Kpi label="체결 수" value={`${a.byHour.reduce((x, y) => x + y.fills, 0)}건`} />
          </div>
        </Card>

        <Card>
          <SectionTitle title="전략별 기여도" />
          <div className="h-[180px] w-full">
            <ResponsiveContainer>
              <BarChart data={a.perStrategy} layout="vertical" margin={{ left: 8, right: 8, top: 4, bottom: 4 }}>
                <XAxis type="number" hide />
                <YAxis dataKey="name" type="category" width={120}
                  tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }}
                  axisLine={false} tickLine={false}
                />
                <Tooltip
                  cursor={{ fill: "hsl(var(--muted) / 0.4)" }}
                  contentStyle={{ background: "hsl(var(--popover))", border: "1px solid hsl(var(--border))", borderRadius: 12, fontSize: 12 }}
                  formatter={(v: number) => won(v, { sign: true })}
                />
                <Bar dataKey="pnl" radius={[6, 6, 6, 6]} barSize={14}>
                  {a.perStrategy.map((d, i) => (
                    <Cell key={i} fill={`hsl(var(--${d.pnl >= 0 ? "up" : "down"}))`} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card>
          <SectionTitle title="시간대별 체결 분포" />
          <div className="h-[160px] w-full">
            <ResponsiveContainer>
              <BarChart data={a.byHour} margin={{ left: 0, right: 0, top: 8, bottom: 0 }}>
                <XAxis dataKey="hour" tickFormatter={(v) => `${v}시`}
                  tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }}
                  axisLine={false} tickLine={false}
                />
                <YAxis hide />
                <Tooltip
                  cursor={{ fill: "hsl(var(--muted) / 0.4)" }}
                  contentStyle={{ background: "hsl(var(--popover))", border: "1px solid hsl(var(--border))", borderRadius: 12, fontSize: 12 }}
                />
                <Bar dataKey="fills" fill="hsl(var(--primary))" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card>
          <SectionTitle title="손실 원인 태그" sub="가장 자주 등장한 사유" />
          <ul className="space-y-2">
            {a.lossTags.map((t) => {
              const max = Math.max(...a.lossTags.map((x) => x.count));
              const w = (t.count / max) * 100;
              return (
                <li key={t.tag}>
                  <div className="flex items-center justify-between text-[12.5px]">
                    <span>{t.tag}</span>
                    <span className="num text-muted-foreground">{t.count}건</span>
                  </div>
                  <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-muted">
                    <div className="h-full rounded-full bg-danger/70" style={{ width: `${w}%` }} />
                  </div>
                </li>
              );
            })}
          </ul>
        </Card>

        {range === "custom" && (
          <Card className="text-center text-sm text-muted-foreground">
            사용자 지정 기간 선택 UI는 다음 단계에서 연결됩니다 (데모).
          </Card>
        )}
      </main>
    </>
  );
}

function Kpi({ label, value, tone }: { label: string; value: string; tone?: "up" | "down" }) {
  return (
    <div className="rounded-xl border border-border bg-surface-3/40 px-3 py-2.5">
      <div className="text-[10.5px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className={cn("mt-0.5 text-sm font-semibold num",
        tone === "up" ? "text-up" : tone === "down" ? "text-down" : "text-foreground")}>
        {value}
      </div>
    </div>
  );
}
