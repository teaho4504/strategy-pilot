import { RefreshCw, Server, ServerOff } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import { readonlyApiClient } from "@/services/apiClient";
import { cn } from "@/lib/utils";

export function ConnectionBadge() {
  const { session } = useAuth();
  const status = useQuery({
    queryKey: ["topbar-us-order-status", session?.accessToken],
    queryFn: readonlyApiClient.usOrderStatus,
    enabled: Boolean(session?.accessToken),
    refetchInterval: 30_000,
    retry: false,
  });

  const checking = status.isLoading || status.isFetching;
  const connected = Boolean(status.data?.sessionPresent) && !status.isError;
  const Icon = checking ? RefreshCw : connected ? Server : ServerOff;
  const label = checking ? "동기화 중" : connected ? "서버 연결" : "연결 확인";

  return (
    <span
      className={cn(
        "hidden items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-semibold sm:inline-flex",
        checking && "border-warning/35 bg-warning/10 text-warning",
        connected && !checking && "border-success/35 bg-success/10 text-success",
        !connected && !checking && "border-danger/35 bg-danger-soft/70 text-danger",
      )}
      role="status"
      aria-live="polite"
      title="브라우저가 아닌 별도 백엔드 서버를 통한 연결 상태입니다."
    >
      <Icon className={cn("h-3 w-3", checking && "animate-spin")} />
      {label}
    </span>
  );
}
