import { Bell, LogOut } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthProvider";
import { useApp } from "@/store/app";
import { DemoBadge } from "@/components/common/DemoBadge";
import { Button } from "@/components/ui/button";
import { portfolioAdapter } from "@/services/adapters";

export function TopBar() {
  const { selectedAccountId } = useApp();
  const { email, signOut } = useAuth();
  const accountsQuery = useQuery({ queryKey: ["accounts"], queryFn: portfolioAdapter.getAccounts });
  const acc = accountsQuery.data?.find((a) => a.id === selectedAccountId) ?? accountsQuery.data?.[0];

  return (
    <header className="sticky top-0 z-30 border-b border-border bg-surface-1/85 backdrop-blur">
      <div className="flex items-center justify-between gap-3 px-4 py-3" style={{ paddingTop: "calc(env(safe-area-inset-top) + 12px)" }}>
        <div className="flex min-w-0 items-center gap-2">
          <DemoBadge />
          <div className="min-w-0">
            <div className="truncate text-sm font-medium text-foreground">
              {acc ? `${acc.broker} · ${acc.label}` : "backend 계좌 확인 중"}
            </div>
            <div className="truncate text-[11px] text-muted-foreground">{email ?? "Supabase 인증"}</div>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            aria-label="알림"
            className="relative grid h-9 w-9 place-items-center rounded-full text-foreground/80 hover:bg-muted"
          >
            <Bell className="h-[18px] w-[18px]" />
            <span className="absolute right-2 top-2 h-1.5 w-1.5 rounded-full bg-up" />
          </button>
          <Button aria-label="로그아웃" variant="ghost" size="icon" onClick={() => void signOut()}>
            <LogOut className="h-[18px] w-[18px]" />
          </Button>
        </div>
      </div>
    </header>
  );
}
