import { Bell, LogOut } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useAuth } from "@/auth/AuthProvider";
import { readonlyApiClient } from "@/services/apiClient";
import { Button } from "@/components/ui/button";
import { Sheet, SheetClose, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { extractHoldingExitAlerts } from "@/lib/exit-alerts";
import { cn } from "@/lib/utils";
import { ConnectionBadge } from "@/components/layout/ConnectionBadge";

export function TopBar() {
  const { email, session, signOut } = useAuth();
  const orderStatus = useQuery({
    queryKey: ["topbar-us-order-status", session?.accessToken],
    queryFn: () => readonlyApiClient.usOrderStatus(),
    enabled: Boolean(session?.accessToken),
    refetchInterval: 30_000,
    retry: false,
  });
  const holdings = useQuery({
    queryKey: ["portfolio-card", "us-holdings"],
    queryFn: readonlyApiClient.usHoldings,
    enabled: Boolean(session?.accessToken),
    refetchInterval: 5_000,
    retry: false,
  });
  const alerts = extractHoldingExitAlerts(holdings.data);
  const liveSession = session?.mode === "live";
  const accountPolicy = session?.orderEnabled ? "실전계좌 · 자동주문" : "실전계좌 · 주문잠금";

  return (
    <header className="sticky top-0 z-30 border-b border-border bg-surface-1/85 backdrop-blur">
      <div className="flex items-center justify-between gap-3 px-4 py-3" style={{ paddingTop: "calc(env(safe-area-inset-top) + 12px)" }}>
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <span className={`shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${liveSession ? "border-primary/30 bg-primary/10 text-primary" : "border-warning/30 bg-warning/10 text-warning"}`}>
            실매매
          </span>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-foreground">키움증권 · {session?.accountLabel ?? "세션 확인"}</div>
            <div className="truncate text-[10.5px] text-muted-foreground">{accountPolicy}</div>
          </div>
          <span
            className={`hidden shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold sm:inline-flex ${
              liveSession
                ? "border-primary/30 bg-primary/10 text-primary"
                : "border-warning/30 bg-warning/10 text-warning"
            }`}
          >
            LIVE
          </span>
          <SessionPolicyChip
            loading={orderStatus.isLoading}
            sessionPresent={Boolean(orderStatus.data?.sessionPresent)}
            orderOpen={Boolean(orderStatus.data && (orderStatus.data.blockedReasons?.length ?? 0) === 0)}
            runtimeLocked={Boolean(orderStatus.data?.runtimeOrderLocked)}
            enabled={Boolean(session?.accessToken)}
          />
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <ConnectionBadge />
          <span className="hidden max-w-[150px] truncate text-[11px] text-muted-foreground sm:block">
            {email ?? "키움 인증"}
          </span>
          <Sheet>
            <SheetTrigger asChild>
              <button aria-label={`알림${alerts.length ? ` ${alerts.length}건` : ""}`} className="relative grid h-9 w-9 place-items-center rounded-full text-foreground/80 hover:bg-muted">
                <Bell className="h-[18px] w-[18px]" />
                {alerts.length ? (
                  <span className="absolute right-0.5 top-0.5 grid min-h-4 min-w-4 place-items-center rounded-full bg-warning px-1 text-[9px] font-bold text-background">
                    {alerts.length > 9 ? "9+" : alerts.length}
                  </span>
                ) : null}
              </button>
            </SheetTrigger>
            <SheetContent className="w-[min(92vw,380px)] border-border bg-surface-1 p-5">
              <SheetHeader className="pr-7 text-left">
                <SheetTitle>매도 검토 알림</SheetTitle>
                <SheetDescription>실계좌 수익률 ±2% 도달 종목 · 주문 전송 없음</SheetDescription>
              </SheetHeader>
              <div className="mt-5 space-y-2">
                {alerts.length ? alerts.map((alert) => (
                  <SheetClose asChild key={`${alert.exchange}-${alert.symbol}`}>
                    <Link
                      to={`/quotes?symbol=${encodeURIComponent(alert.symbol)}&exchange=${encodeURIComponent(alert.exchange)}`}
                      className="flex items-center justify-between gap-3 rounded-xl border border-border bg-background/45 p-3 hover:bg-muted"
                    >
                      <div className="min-w-0">
                        <div className="truncate text-sm font-semibold">{alert.name}</div>
                        <div className="mt-0.5 text-[11px] text-muted-foreground">{alert.symbol} · {alert.exchange}</div>
                      </div>
                      <div className={cn("num shrink-0 text-right text-sm font-bold", alert.reason === "take_profit" ? "text-up" : "text-down")}>
                        {alert.returnRate > 0 ? "+" : ""}{alert.returnRate.toFixed(2)}%
                        <div className="mt-0.5 text-[10px] font-medium">{alert.reason === "take_profit" ? "익절 검토" : "손절 검토"}</div>
                      </div>
                    </Link>
                  </SheetClose>
                )) : (
                  <div className="rounded-xl border border-border bg-background/45 px-3 py-8 text-center text-xs text-muted-foreground">
                    현재 ±2% 기준에 도달한 보유종목이 없습니다.
                  </div>
                )}
              </div>
              <p className="mt-4 text-[10.5px] leading-4 text-muted-foreground">보유종목은 5초마다 갱신됩니다. 실제 매도는 키움 앱에서 직접 진행하세요.</p>
            </SheetContent>
          </Sheet>
          <Button aria-label="로그아웃" variant="ghost" size="icon" onClick={() => void signOut()}>
            <LogOut className="h-[18px] w-[18px]" />
          </Button>
        </div>
      </div>
    </header>
  );
}

function SessionPolicyChip({
  loading,
  sessionPresent,
  orderOpen,
  runtimeLocked,
  enabled,
}: {
  loading: boolean;
  sessionPresent: boolean;
  orderOpen: boolean;
  runtimeLocked: boolean;
  enabled: boolean;
}) {
  if (!enabled) return null;
  const label = loading
    ? "정책 확인"
    : !sessionPresent
      ? "세션 없음"
      : orderOpen
        ? "주문 OPEN"
        : runtimeLocked
          ? "주문 LOCK"
          : "주문 BLOCK";
  const tone = orderOpen
    ? "border-primary/30 bg-primary/10 text-primary"
    : "border-warning/35 bg-warning/10 text-warning";
  return (
    <span className={`hidden shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold md:inline-flex ${tone}`}>
      {label}
    </span>
  );
}
