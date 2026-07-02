import { Card, SectionTitle } from "@/components/common/Card";
import { useMarketSummaryQuery } from "@/services/adapters";
import { errorMessage, formatQueryUpdatedAt } from "@/services/apiClient";
import { DeltaPct } from "@/components/common/DeltaPct";

export function MarketSummary() {
  const { data, dataUpdatedAt, isLoading, isError, error } = useMarketSummaryQuery();
  const marketIndices = data?.marketIndices ?? [];
  const watchlist = data?.watchlist ?? [];

  return (
    <Card>
      <SectionTitle title="시장 요약" sub={`지수 · 환율 · 관심종목 · 마지막 정상 갱신 ${formatQueryUpdatedAt(dataUpdatedAt)}`} />
      {isError && data && (
        <div className="mb-3 rounded-lg border border-warning/30 bg-warning-soft/50 px-3 py-2 text-[11px] text-warning">
          관심종목 최신 조회 실패 · 마지막 정상 데이터를 표시 중입니다. {errorMessage(error)}
        </div>
      )}
      {isLoading && !data ? (
        <div className="rounded-xl border border-border bg-surface-3/40 p-3 text-sm text-muted-foreground">시장 데이터 조회 중...</div>
      ) : isError && !data ? (
        <div className="rounded-xl border border-danger/30 bg-danger-soft/50 p-3 text-sm text-danger">
          시장 데이터를 불러오지 못했습니다. {errorMessage(error)}
        </div>
      ) : (
        <>
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
        </>
      )}
    </Card>
  );
}
