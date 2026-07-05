import { Area, AreaChart, ResponsiveContainer } from "recharts";
import { useQuery } from "@tanstack/react-query";
import { Card } from "@/components/common/Card";
import { DeltaPct } from "@/components/common/DeltaPct";
import { ApiErrorBox, ApiInlineState } from "@/components/common/ApiState";
import { won, wonCompact } from "@/lib/format";
import { portfolioAdapter } from "@/services/adapters";

export function PortfolioCard() {
  const portfolioQuery = useQuery({ queryKey: ["readonly", "portfolio"], queryFn: () => portfolioAdapter.getPortfolio(), staleTime: 10_000 });
  const cashQuery = useQuery({ queryKey: ["readonly", "cash"], queryFn: portfolioAdapter.getCash, staleTime: 10_000 });
  const holdingsQuery = useQuery({ queryKey: ["readonly", "holdings"], queryFn: portfolioAdapter.getHoldings, staleTime: 10_000 });
  const performanceQuery = useQuery({ queryKey: ["readonly", "performance"], queryFn: portfolioAdapter.getPerformance, staleTime: 10_000 });

  const p = portfolioQuery.data;
  const error = portfolioQuery.error || cashQuery.error || holdingsQuery.error || performanceQuery.error;
  const loading = portfolioQuery.isLoading || cashQuery.isLoading || holdingsQuery.isLoading || performanceQuery.isLoading;

  if (!p) {
    return (
      <Card className="space-y-3">
        <div>
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">평가자산</div>
          <div className="mt-1 text-xl font-semibold">backend 데이터 대기</div>
        </div>
        <ApiInlineState isLoading={loading} error={error} />
        {error && <ApiErrorBox error={error} />}
      </Card>
    );
  }

  const up = p.dayPnl >= 0;
  const cash = cashQuery.data;
  const holdings = holdingsQuery.data ?? [];
  const performance = performanceQuery.data;

  return (
    <Card className="overflow-hidden p-0">
      <div className="space-y-4 p-4">
        <ApiInlineState isLoading={loading} error={error} />
        <div className="flex items-start justify-between">
          <div>
            <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">평가자산</div>
            <div className="mt-1 text-[26px] font-bold leading-none num">
              {p.equity.toLocaleString("ko-KR")}
              <span className="ml-1 text-base font-medium text-muted-foreground">원</span>
            </div>
          </div>
          <div className="text-right">
            <DeltaPct value={p.dayPnlPct} className="text-base" />
            <div className={`text-xs num ${up ? "text-up" : "text-down"}`}>{won(p.dayPnl, { sign: true })}</div>
          </div>
        </div>

        <div className="grid grid-cols-3 divide-x divide-border rounded-xl border border-border bg-surface-3/40">
          <Stat label="누적 손익" value={won(p.cumulativePnl, { sign: true })} tone={p.cumulativePnl >= 0 ? "up" : "down"} />
          <Stat label="현금" value={wonCompact(p.cash)} />
          <Stat label="현금 비중" value={`${Math.round(p.cashRatio * 100)}%`} />
        </div>

        <div className="grid grid-cols-3 gap-2">
          <Mini label="주문가능" value={cash ? wonCompact(cash.orderableAmount) : "—"} />
          <Mini label="보유종목" value={`${holdings.length}개`} />
          <Mini label="계좌수익률" value={performance ? `${performance.totalReturnRate.toFixed(2)}%` : "—"} tone={(performance?.totalReturnRate ?? 0) >= 0 ? "up" : "down"} />
        </div>
        {error && <ApiErrorBox error={error} />}
      </div>

      <div className="h-[88px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={p.intradayCurve} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="curve" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={`hsl(var(--${up ? "up" : "down"}))`} stopOpacity={0.35} />
                <stop offset="100%" stopColor={`hsl(var(--${up ? "up" : "down"}))`} stopOpacity={0} />
              </linearGradient>
            </defs>
            <Area
              dataKey="v"
              stroke={`hsl(var(--${up ? "up" : "down"}))`}
              strokeWidth={1.75}
              fill="url(#curve)"
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}

function Mini({ label, value, tone }: { label: string; value: string; tone?: "up" | "down" }) {
  const c = tone === "up" ? "text-up" : tone === "down" ? "text-down" : "text-foreground";
  return (
    <div className="rounded-xl border border-border bg-surface-3/40 px-3 py-2">
      <div className="text-[10.5px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className={`mt-0.5 text-sm font-semibold num ${c}`}>{value}</div>
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: "up" | "down" }) {
  const c = tone === "up" ? "text-up" : tone === "down" ? "text-down" : "text-foreground";
  return (
    <div className="px-3 py-2.5">
      <div className="text-[10.5px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className={`mt-1 text-sm font-semibold num ${c}`}>{value}</div>
    </div>
  );
}
