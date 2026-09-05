import { Activity, LockKeyhole, Radio, Server } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import { readonlyApiClient } from "@/services/apiClient";
import { cn } from "@/lib/utils";

export function DashboardStatusStrip() {
  const { session } = useAuth();
  const orderStatus = useQuery({
    queryKey: ["topbar-us-order-status", session?.accessToken],
    queryFn: readonlyApiClient.usOrderStatus,
    enabled: Boolean(session?.accessToken),
    refetchInterval: 30_000,
    retry: false,
  });

  const connected = Boolean(orderStatus.data?.sessionPresent) && !orderStatus.isError;
  const locked = Boolean(
    orderStatus.data?.readOnly ||
    orderStatus.data?.runtimeOrderLocked ||
    (orderStatus.data?.blockedReasons?.length ?? 0) > 0,
  );

  return (
    <section className="overflow-hidden rounded-2xl border border-border bg-surface-2/75 shadow-card">
      <div className="grid grid-cols-2 divide-x divide-y divide-border sm:grid-cols-4 sm:divide-y-0">
        <StatusItem icon={Activity} label="운영 모드" value={session?.mode === "live" ? "실계좌 조회" : "세션 확인"} tone="primary" />
        <StatusItem icon={Server} label="데이터 경로" value="백엔드 경유" tone="neutral" />
        <StatusItem icon={Radio} label="세션 상태" value={orderStatus.isLoading ? "확인 중" : connected ? "연결됨" : "확인 필요"} tone={connected ? "success" : "warning"} />
        <StatusItem icon={LockKeyhole} label="주문 안전" value={orderStatus.isLoading ? "정책 확인" : locked ? "잠금 유지" : "정책 활성"} tone={locked ? "success" : "warning"} />
      </div>
    </section>
  );
}

function StatusItem({
  icon: Icon,
  label,
  value,
  tone,
}: {
  icon: typeof Activity;
  label: string;
  value: string;
  tone: "primary" | "success" | "warning" | "neutral";
}) {
  return (
    <div className="flex min-w-0 items-center gap-3 px-3 py-3.5 sm:px-4">
      <span className={cn(
        "grid h-9 w-9 shrink-0 place-items-center rounded-xl border",
        tone === "primary" && "border-primary/25 bg-primary/10 text-primary",
        tone === "success" && "border-success/25 bg-success/10 text-success",
        tone === "warning" && "border-warning/25 bg-warning/10 text-warning",
        tone === "neutral" && "border-border bg-background/55 text-muted-foreground",
      )}>
        <Icon className="h-4 w-4" />
      </span>
      <div className="min-w-0">
        <div className="truncate text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">{label}</div>
        <div className="mt-0.5 truncate text-xs font-bold text-foreground">{value}</div>
      </div>
    </div>
  );
}
