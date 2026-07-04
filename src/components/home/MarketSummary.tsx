import { useQuery } from "@tanstack/react-query";
import { Card, SectionTitle } from "@/components/common/Card";
import { DeltaPct } from "@/components/common/DeltaPct";
import { getErrorMessage } from "@/services/apiClient";
import { portfolioAdapter, queryKeys } from "@/services/adapters";

export function MarketSummary() {
  const query = useQuery({
    queryKey: queryKeys.marketWatchlist,
    queryFn: () => portfolioAdapter.getMarketWatchlist(),
    refetchInterval: 15_000,
    retry: 1,
  });
  const marketIndices = query.data?.indices ?? [];
  const watchlist = query.data?.watchlist ?? [];

  return (
    <Card>
      <SectionTitle
        title="시장 요약"
        sub={query.isError ? `API 오류 · ${getErrorMessage(query.error)}` : query.data?.updatedAt ? `마지막 조회 · ${new Date(query.data.updatedAt).toLocaleTimeString("ko-KR")}` : "지수 · 환율 · 관심종목"}
      />
      <div className="grid grid-cols-3 gap-2">
        {marketIndices.map((m) => (
          <div key={m.code} className="rounded-xl border border-border bg-surface-3/40 px-3 py-2.5">
            <div className="text-[10.5px] uppercase tracking-wide text-muted-foreground">{m.name}</div>
            <div className="mt-1 text-sm font-semibold num">{m.value.toLocaleString("ko-KR")}</div>
            <DeltaPct value={m.changePct} className="text-[11px]" />
          </div>
        ))}
        {query.isLoading && <div className="col-span-3 rounded-xl border border-border bg-surface-3/40 p-3 text-center text-xs text-muted-foreground">시장 데이터 조회 중</div>}
      </div>
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
        {!query.isLoading && watchlist.length === 0 && (
          <li className="px-3 py-3 text-center text-xs text-muted-foreground">표시할 관심종목이 없습니다.</li>
        )}
      </ul>
    </Card>
  );
}
