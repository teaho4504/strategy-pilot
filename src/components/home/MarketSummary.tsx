import { useQuery } from "@tanstack/react-query";
import { Card, SectionTitle } from "@/components/common/Card";
import { marketIndices } from "@/services/mock/data";
import { DeltaPct } from "@/components/common/DeltaPct";
import { portfolioAdapter } from "@/services/adapters";
import { safeApiError } from "@/services/apiClient";

export function MarketSummary() {
  const watchlistQuery = useQuery({ queryKey: ["watchlist"], queryFn: portfolioAdapter.getWatchlist });
  const safe = safeApiError(watchlistQuery.error);
  const watchlist = watchlistQuery.data ?? [];

  return (
    <Card>
      <SectionTitle title="시장 요약" sub="지수·환율은 데모 · 관심종목은 인증 API" />
      <div className="grid grid-cols-3 gap-2">
        {marketIndices.map((m) => (
          <div key={m.code} className="rounded-xl border border-border bg-surface-3/40 px-3 py-2.5">
            <div className="text-[10.5px] uppercase tracking-wide text-muted-foreground">{m.name}</div>
            <div className="mt-1 text-sm font-semibold num">{m.value.toLocaleString("ko-KR")}</div>
            <DeltaPct value={m.changePct} className="text-[11px]" />
          </div>
        ))}
      </div>
      <div className="mt-3 text-xs font-medium text-muted-foreground">관심종목</div>
      {watchlistQuery.isLoading && <div className="mt-2 rounded-xl border border-border bg-surface-3/40 px-3 py-3 text-sm text-muted-foreground">backend 관심종목을 불러오는 중</div>}
      {watchlistQuery.isError && (
        <div className="mt-2 rounded-xl border border-danger/40 bg-danger-soft/40 px-3 py-3 text-xs text-danger">
          관심종목 API 오류 endpoint={safe?.endpoint ?? "/api/market/watchlist"} {safe?.status ? `http=${safe.status}` : safe?.type}
        </div>
      )}
      <ul className="mt-3 divide-y divide-border rounded-xl border border-border bg-surface-3/40">
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
