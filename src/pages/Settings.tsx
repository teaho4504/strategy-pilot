import { useQuery } from "@tanstack/react-query";
import { TopBar } from "@/components/layout/TopBar";
import { Card, SectionTitle } from "@/components/common/Card";
import { readonlyApiClient } from "@/services/apiClient";
import { ShieldCheck, ServerCog } from "lucide-react";

export default function Settings() {
  const orderStatus = useQuery({
    queryKey: ["settings", "us-order-status"],
    queryFn: readonlyApiClient.usOrderStatus,
    refetchInterval: 15_000,
    retry: false,
  });
  const autoTrade = useQuery({
    queryKey: ["settings", "us-autotrade-status"],
    queryFn: readonlyApiClient.usAutoTradeStatus,
    refetchInterval: 15_000,
    retry: false,
  });

  return (
    <>
      <TopBar />
      <main className="space-y-3 p-4 animate-fade-in">
        <h1 className="text-xl font-semibold">운영 설정</h1>

        <Card className="space-y-3">
          <SectionTitle title="실계좌 서버 상태" sub="가짜 데이터 없이 백엔드가 보고한 현재 상태만 표시합니다" />
          <StatusRow label="백엔드 연결" value={orderStatus.isError ? "연결 오류" : orderStatus.isLoading ? "확인 중" : "연결됨"} ok={orderStatus.isSuccess} />
          <StatusRow label="실주문 정책" value={orderStatus.data?.orderEnabled ? "활성" : "비활성"} ok={Boolean(orderStatus.data?.orderEnabled)} />
          <StatusRow label="자동매매" value={autoTrade.data?.enabled ? "활성" : "비활성"} ok={Boolean(autoTrade.data?.enabled)} />
          <StatusRow label="상주 실행기" value={autoTrade.data?.runnerRunning ? "실행 중" : "정지"} ok={Boolean(autoTrade.data?.runnerRunning)} />
        </Card>

        <Card className="space-y-3">
          <SectionTitle title="보안 경계" />
          <div className="flex items-start gap-2 rounded-lg border border-success/30 bg-success/10 p-3 text-xs leading-5 text-success">
            <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
            App Key, Secret Key, 접근 토큰과 계좌번호는 브라우저에 저장하지 않습니다. 이 화면은 서버 상태만 조회합니다.
          </div>
          {(orderStatus.data?.blockedReasons ?? []).length > 0 ? (
            <div className="rounded-lg border border-warning/30 bg-warning-soft p-3 text-xs text-warning">
              차단 사유: {orderStatus.data?.blockedReasons.join(" · ")}
            </div>
          ) : null}
        </Card>
      </main>
    </>
  );
}

function StatusRow({ label, value, ok }: { label: string; value: string; ok: boolean }) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-border bg-surface-3/40 px-3 py-3 text-sm">
      <span className="flex items-center gap-2 text-muted-foreground"><ServerCog className="h-4 w-4" />{label}</span>
      <span className={ok ? "text-success" : "text-warning"}>{value}</span>
    </div>
  );
}
