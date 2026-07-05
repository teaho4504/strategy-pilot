import { Card, SectionTitle } from "@/components/common/Card";
import { useQuery } from "@tanstack/react-query";
import { marketIndices } from "@/services/mock/data";
import { portfolioAdapter } from "@/services/adapters";
import { DeltaPct } from "@/components/common/DeltaPct";
import { ApiInlineState } from "@/components/common/ApiState";

export function MarketSummary() {
  const watchlistQuery = useQuery({ queryKey: ["readonly", "watchlist"], queryFn: portfolioAdapter.getWatchlist, staleTime: 15_000 });
  const watchlist = watchlistQuery.data ?? [];

  return (
    <Card>
      <SectionTitle title="시장 요약" sub="지수·환율은 데모 · 관심종목은 backend API" />
      <ApiInlineState isLoading={watchlistQuery.isLoading} error={watchlistQuery.error} />
      <div className="grid grid-cols-3 gap-2">
        {marketIndices.map((m) => (
          <div key={m.code} className="rounded-xl border border-border bg-surface-3/40 px-3 py-2.5">
            <div className="text-[10.5px] uppercase tracking-wide text-muted-foreground">{m.name}</div>
            <div className="mt-1 text-sm font-semibold num">{m.value.toLocaleString("ko-KR")}</div>
            <DeltaPct value={m.changePct} className="text-[11px]" />
          </div>
        ))}
      </div>
      <ul className="mt-3 divide-y divide-border rounded-xl border border-border bg-surface-3/40">
        {watchlist.length === 0 && (
          <li className="px-3 py-3 text-xs text-muted-foreground">
            관심종목 backend 데이터를 기다리는 중입니다.
          </li>
        )}
        {watchlist.map((t) => (
          <li key={t.code} className="flex items-center justify-between px-3 py-2.5">
            <div className="min-w-0">
              <div className="truncate text-sm font-medium">{t.name}</div>
              <div className="text-[11px] text-muted-foreground num">{t.code}</div>
            </div>
            <div className="text-right">
              <div className="text-sm font-semibold num">{t.price.toLocaleString("ko-KR")}</div>
              <DeltaPct value={t.changePct} className="text-[11px]" />
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}
