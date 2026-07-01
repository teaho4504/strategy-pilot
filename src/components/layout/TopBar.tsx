import { Bell, ChevronDown } from "lucide-react";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useApp } from "@/store/app";
import { portfolioAdapter, queryKeys } from "@/services/adapters";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { DemoBadge } from "@/components/common/DemoBadge";

const fallbackAccount = { id: "pending", broker: "키움증권", label: "계좌 조회 대기", isDemo: true, maskedNumber: "****-**-****" };

export function TopBar() {
  const { selectedAccountId, setAccount } = useApp();
  const { data: accounts = [], isError } = useQuery({
    queryKey: queryKeys.accounts,
    queryFn: portfolioAdapter.getAccounts,
    retry: 1,
  });
  const acc = accounts.find((a) => a.id === selectedAccountId) ?? accounts[0] ?? fallbackAccount;
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-30 border-b border-border bg-surface-1/85 backdrop-blur">
      <div className="flex items-center justify-between gap-3 px-4 py-3" style={{ paddingTop: "calc(env(safe-area-inset-top) + 12px)" }}>
        <div className="flex min-w-0 items-center gap-2">
          <DemoBadge />
          <DropdownMenu open={open} onOpenChange={setOpen}>
            <DropdownMenuTrigger className="flex min-w-0 items-center gap-1 rounded-lg px-1.5 py-1 text-left text-sm font-medium text-foreground hover:bg-muted">
              <span className="truncate">{isError ? "계좌 API 오류" : `${acc.broker} · ${acc.label}`}</span>
              <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-[260px]">
              {accounts.length > 0 ? accounts.map((a) => (
                <DropdownMenuItem key={a.id} onSelect={() => setAccount(a.id)} className="flex flex-col items-start gap-0.5">
                  <span className="font-medium">{a.broker} · {a.label}</span>
                  <span className="text-xs text-muted-foreground">{a.maskedNumber} · {a.isDemo ? "데모" : "계좌 조회"}</span>
                </DropdownMenuItem>
              )) : (
                <DropdownMenuItem disabled className="text-xs text-muted-foreground">
                  계좌 데이터를 불러올 수 없습니다.
                </DropdownMenuItem>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        <button
          aria-label="알림"
          className="relative grid h-9 w-9 place-items-center rounded-full text-foreground/80 hover:bg-muted"
        >
          <Bell className="h-[18px] w-[18px]" />
          <span className="absolute right-2 top-2 h-1.5 w-1.5 rounded-full bg-up" />
        </button>
      </div>
    </header>
  );
}
