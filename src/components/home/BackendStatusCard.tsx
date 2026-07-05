import { useQuery } from "@tanstack/react-query";
import { Card } from "@/components/common/Card";
import { ApiInlineState, ApiModeBadge } from "@/components/common/ApiState";
import { portfolioAdapter } from "@/services/adapters";

export function BackendStatusCard() {
  const healthQuery = useQuery({ queryKey: ["readonly", "health"], queryFn: portfolioAdapter.getHealth, staleTime: 15_000 });
  const statusQuery = useQuery({ queryKey: ["readonly", "kiwoom-status"], queryFn: portfolioAdapter.getKiwoomStatus, staleTime: 15_000 });
  const health = healthQuery.data;
  const status = statusQuery.data;
  const error = healthQuery.error || statusQuery.error;
  const loading = healthQuery.isLoading || statusQuery.isLoading;

  return (
    <Card className="flex items-center justify-between gap-3 py-3">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <ApiModeBadge mode={status?.mode ?? health?.mode} readOnly={status?.readOnly ?? health?.kiwoom?.readOnly} />
          <span className="truncate text-xs font-medium text-muted-foreground">
            {error ? "BACKEND OFFLINE" : loading ? "LOADING" : status?.configured ? "Kiwoom 연결 설정됨" : "Kiwoom mock/read-only"}
          </span>
        </div>
        <ApiInlineState isLoading={loading} error={error} />
      </div>
      <div className="shrink-0 text-right text-[10.5px] text-muted-foreground">
        <div>orders disabled</div>
        <div className="num">{status?.orderEnabled ? "ORDER ON" : "ORDER OFF"}</div>
      </div>
    </Card>
  );
}
