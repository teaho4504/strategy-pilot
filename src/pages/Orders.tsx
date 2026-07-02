import { useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { TopBar } from "@/components/layout/TopBar";
import { Card } from "@/components/common/Card";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { orderAdapter, queryKeys, useOrdersQuery } from "@/services/adapters";
import type { Order, OrderStatus } from "@/types";
import { timeKR, won } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ShieldAlert } from "lucide-react";
import { toast } from "sonner";

type Tab = "pending" | "filled" | "rejected";

const TABS: { key: Tab; label: string; match: OrderStatus[] }[] = [
  { key: "pending", label: "대기 주문", match: ["pending", "partial"] },
  { key: "filled", label: "체결", match: ["filled", "partial"] },
  { key: "rejected", label: "취소 · 실패", match: ["cancelled", "failed"] },
];

const STATUS_LABEL: Record<OrderStatus, string> = {
  pending: "대기", filled: "체결", partial: "부분체결", cancelled: "취소", failed: "실패",
};

export default function Orders() {
  const queryClient = useQueryClient();
  const { data: list = [], isLoading, isError } = useOrdersQuery();
  const [tab, setTab] = useState<Tab>("pending");
  const [sel, setSel] = useState<Order | null>(null);

  const tabSpec = TABS.find((t) => t.key === tab)!;
  const filtered = useMemo(
    () => list.filter((o) => tabSpec.match.includes(o.status)).sort((a, b) => +new Date(b.time) - +new Date(a.time)),
    [list, tabSpec]
  );

  const cancel = async (id: string) => {
    await orderAdapter.cancel(id);
    queryClient.invalidateQueries({ queryKey: queryKeys.orders });
    toast.success("주문 취소 (데모)");
    setSel(null);
  };

  return (
    <>
      <TopBar />
      <main className="space-y-3 p-4 animate-fade-in">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-semibold">주문 · 체결</h1>
          <span className="chip">모의투자 · 주문 가능</span>
        </div>

        <div className="rounded-xl border border-warning/30 bg-warning-soft/60 p-3 text-[12px] text-warning flex gap-2">
          <ShieldAlert className="h-4 w-4 shrink-0" />
          수동 주문은 안전을 위해 비활성화되어 있습니다. 모든 주문은 전략에서만 생성됩니다 (데모).
        </div>

        <div className="grid grid-cols-3 gap-1.5 rounded-xl border border-border bg-surface-2 p-1">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={cn(
                "rounded-lg py-2 text-[12.5px] font-medium transition-colors",
                tab === t.key ? "bg-surface-3 text-foreground shadow-sm" : "text-muted-foreground"
              )}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="space-y-2">
          {isLoading && <Card className="text-center text-sm text-muted-foreground">주문 데이터를 불러오는 중입니다.</Card>}
          {isError && <Card className="text-center text-sm text-danger">주문 데이터를 불러오지 못했습니다.</Card>}
          {!isLoading && !isError && filtered.length === 0 && (
            <Card className="text-center text-sm text-muted-foreground">표시할 주문이 없습니다.</Card>
          )}
          {filtered.map((o) => (
            <button key={o.id} onClick={() => setSel(o)} className="block w-full text-left">
              <Card className="space-y-2 hover:border-border-strong">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className={cn(
                      "rounded-md px-1.5 py-0.5 text-[11px] font-bold",
                      o.side === "BUY" ? "bg-up/15 text-up" : "bg-down/15 text-down"
                    )}>
                      {o.side === "BUY" ? "매수" : "매도"}
                    </span>
                    <span className="text-sm font-semibold">{o.name}</span>
                    <span className="text-[11px] text-muted-foreground num">{o.code}</span>
                  </div>
                  <StatusTag s={o.status} />
                </div>
                <div className="flex items-center justify-between text-[12px] text-muted-foreground">
                  <span className="num">{o.qty}주 · {won(o.price)}</span>
                  <span className="num">{timeKR(o.time)}</span>
                </div>
                <div className="truncate text-[11px] text-muted-foreground/80">
                  {o.strategyName}
                </div>
              </Card>
            </button>
          ))}
        </div>
      </main>

      <Sheet open={!!sel} onOpenChange={(o) => !o && setSel(null)}>
        <SheetContent side="bottom" className="rounded-t-2xl border-border bg-surface-2">
          {sel && (
            <>
              <SheetHeader className="text-left">
                <SheetTitle className="flex items-center gap-2">
                  <span className={cn(
                    "rounded-md px-1.5 py-0.5 text-[11px] font-bold",
                    sel.side === "BUY" ? "bg-up/15 text-up" : "bg-down/15 text-down"
                  )}>
                    {sel.side === "BUY" ? "매수" : "매도"}
                  </span>
                  {sel.name} <span className="text-xs font-normal text-muted-foreground num">{sel.code}</span>
                </SheetTitle>
                <SheetDescription>주문 ID · {sel.id}</SheetDescription>
              </SheetHeader>
              <div className="mt-4 space-y-3">
                <div className="grid grid-cols-3 divide-x divide-border rounded-xl border border-border bg-surface-3/40">
                  <KV label="수량" value={`${sel.qty}주`} />
                  <KV label="가격" value={won(sel.price)} />
                  <KV label="시각" value={timeKR(sel.time)} />
                </div>
                <div>
                  <div className="text-[11px] uppercase tracking-wide text-muted-foreground">주문 근거</div>
                  <div className="mt-1 rounded-xl border border-border bg-surface-3/40 p-3 text-sm">
                    {sel.reason}
                  </div>
                </div>
                <div>
                  <div className="text-[11px] uppercase tracking-wide text-muted-foreground">연결 전략</div>
                  <div className="mt-1 text-sm font-medium">{sel.strategyName}</div>
                </div>
                <div>
                  <div className="text-[11px] uppercase tracking-wide text-muted-foreground">체결 경과</div>
                  <ol className="mt-2 space-y-1.5 text-[12.5px]">
                    <li className="flex justify-between"><span>신호 발생</span><span className="num text-muted-foreground">{timeKR(sel.time)}</span></li>
                    <li className="flex justify-between"><span>주문 제출</span><span className="num text-muted-foreground">{timeKR(sel.time)}</span></li>
                    <li className="flex justify-between"><span>현재 상태</span><span><StatusTag s={sel.status} /></span></li>
                  </ol>
                </div>

                {sel.status === "pending" ? (
                  <Button variant="destructive" className="w-full" onClick={() => cancel(sel.id)}>
                    주문 취소 (데모)
                  </Button>
                ) : (
                  <Button variant="outline" className="w-full" disabled>
                    취소 불가 · 종결된 주문
                  </Button>
                )}
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </>
  );
}

function StatusTag({ s }: { s: OrderStatus }) {
  const tone: Record<OrderStatus, string> = {
    pending: "border-accent/40 bg-accent/10 text-accent",
    filled: "border-success/40 bg-success/10 text-success",
    partial: "border-warning/40 bg-warning-soft text-warning",
    cancelled: "border-border bg-muted text-muted-foreground",
    failed: "border-danger/40 bg-danger-soft text-danger",
  };
  return (
    <span className={cn("rounded-full border px-2 py-0.5 text-[11px] font-medium", tone[s])}>
      {STATUS_LABEL[s]}
    </span>
  );
}

function KV({ label, value }: { label: string; value: string }) {
  return (
    <div className="px-3 py-2">
      <div className="text-[10.5px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-sm font-semibold num">{value}</div>
    </div>
  );
}
