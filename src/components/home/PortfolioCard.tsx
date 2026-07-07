import { Area, AreaChart, ResponsiveContainer } from "recharts";
import { useQuery } from "@tanstack/react-query";
import { Card } from "@/components/common/Card";
import { DeltaPct } from "@/components/common/DeltaPct";
import { won, wonCompact } from "@/lib/format";
import { portfolioAdapter } from "@/services/adapters";
import { safeApiError } from "@/services/apiClient";

export function PortfolioCard() {
  const portfolioQuery = useQuery({ queryKey: ["portfolio"], queryFn: () => portfolioAdapter.getPortfolio("default") });
  const cashQuery = useQuery({ queryKey: ["cash"], queryFn: portfolioAdapter.getCash });
  const holdingsQuery = useQuery({ queryKey: ["holdings"], queryFn: portfolioAdapter.getHoldings });
  const performanceQuery = useQuery({ queryKey: ["performance"], queryFn: portfolioAdapter.getPerformance });
  const p = portfolioQuery.data;

  if (portfolioQuery.isLoading) {
    return <Card><div className="py-8 text-center text-sm text-muted-foreground">backend 계좌 데이터를 불러오는 중</div></Card>;
  }

  if (!p || portfolioQuery.isError) {
    const safe = safeApiError(portfolioQuery.error);
    return (
      <Card>
        <div className="text-sm font-semibold text-danger">KIWOOM CONNECTION ERROR</div>
        <div className="mt-1 text-xs text-muted-foreground">
          endpoint={safe?.endpoint ?? "/api/account/portfolio"} {safe?.status ? `http=${safe.status}` : safe?.type}
        </div>
      </Card>
    );
  }

  const up = p.dayPnl >= 0;
  return (
    <Card className="overflow-hidden p-0">
      <div className="space-y-4 p-4">
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
          <Stat label="현금" value={wonCompact(cashQuery.data?.cash ?? p.cash)} />
          <Stat label="현금 비중" value={`${Math.round(p.cashRatio * 100)}%`} />
        </div>
        <div className="grid grid-cols-2 gap-2 text-[11px] text-muted-foreground">
          <div>보유종목 {holdingsQuery.data?.length ?? "-"}개</div>
          <div className="text-right">수익률 {performanceQuery.data ? `${performanceQuery.data.totalReturnRate.toFixed(2)}%` : "-"}</div>
        </div>
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

function Stat({ label, value, tone }: { label: string; value: string; tone?: "up" | "down" }) {
  const c = tone === "up" ? "text-up" : tone === "down" ? "text-down" : "text-foreground";
  return (
    <div className="px-3 py-2.5">
      <div className="text-[10.5px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className={`mt-1 text-sm font-semibold num ${c}`}>{value}</div>
    </div>
  );
}
