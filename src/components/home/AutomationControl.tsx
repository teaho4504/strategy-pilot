import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ArrowRight, CheckCircle2 } from "lucide-react";
import { Card } from "@/components/common/Card";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/auth/AuthProvider";
import { readonlyApiClient } from "@/services/apiClient";

export function AutomationControl() {
  const { session } = useAuth();
  const sessionToken = session?.accessToken ?? "";
  const strategies = useQuery({
    queryKey: ["home", "us-autotrade-strategies", sessionToken],
    queryFn: readonlyApiClient.usAutoTradeStrategies,
    enabled: Boolean(sessionToken),
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
    retry: false,
  });
  const enabledStrategies = (strategies.data?.strategies ?? []).filter((item) => item.enabled);

  return (
    <Card className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">자동매매 상태</div>
          <div className="mt-1 text-lg font-semibold">활성 전략 {enabledStrategies.length}개</div>
        </div>
        <Button asChild size="sm" variant="secondary" className="shrink-0 rounded-full">
          <Link to="/strategies">전략 관리<ArrowRight className="ml-1 h-4 w-4" /></Link>
        </Button>
      </div>

      {strategies.isError ? (
        <div className="rounded-xl border border-danger/40 bg-danger-soft/50 px-3 py-3 text-xs font-medium text-danger">
          활성 전략을 불러오지 못했습니다. 로그인 세션과 백엔드 연결을 확인하세요.
        </div>
      ) : enabledStrategies.length ? (
        <div className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-background/45">
          {enabledStrategies.map((strategy) => (
            <div key={strategy.strategy} className="flex items-center justify-between gap-3 px-3 py-3">
              <span className="truncate text-sm font-semibold">{strategy.strategyName}</span>
              <span className="flex shrink-0 items-center gap-1 text-xs font-semibold text-success">
                <CheckCircle2 className="h-3.5 w-3.5" />활성
              </span>
            </div>
          ))}
        </div>
      ) : (
        <div className="rounded-xl border border-border bg-background/45 px-3 py-4 text-center text-xs text-muted-foreground">
          현재 활성화된 전략이 없습니다.
        </div>
      )}
    </Card>
  );
}
