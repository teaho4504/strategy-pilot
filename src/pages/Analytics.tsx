import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { TopBar } from "@/components/layout/TopBar";
import { Card, SectionTitle } from "@/components/common/Card";
import { Button } from "@/components/ui/button";
import { readonlyApiClient } from "@/services/apiClient";
import { cn } from "@/lib/utils";

type BrokerFill = {
  orderNo: string;
  symbol: string;
  side: "buy" | "sell" | "unknown";
  quantity: number;
  price: number;
};

const WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"];

export default function Analytics() {
  const [month, setMonth] = useState(() => startOfMonth(new Date()));
  const fromDate = compactDate(month);
  const toDate = compactDate(new Date(month.getFullYear(), month.getMonth() + 1, 0));

  const daily = useQuery({
    queryKey: ["analytics", "daily-returns", fromDate, toDate],
    queryFn: () => readonlyApiClient.usDailyReturns(fromDate, toDate),
    staleTime: 60_000,
    retry: false,
  });
  const realized = useQuery({
    queryKey: ["analytics", "realized-pnl"],
    queryFn: readonlyApiClient.usRealizedPnl,
    refetchInterval: 60_000,
    retry: false,
  });
  const fills = useQuery({
    queryKey: ["analytics", "order-fills"],
    queryFn: readonlyApiClient.usOrderFills,
    refetchInterval: 30_000,
    retry: false,
  });

  const dailyRows = useMemo(() => daily.data?.rows ?? [], [daily.data?.rows]);
  const dailyByDate = useMemo(
    () => new Map(dailyRows.filter((row) => row.baseDate).map((row) => [normalizeDate(row.baseDate!), row])),
    [dailyRows],
  );
  const brokerFills = useMemo(() => extractBrokerFills(fills.data?.data), [fills.data?.data]);
  const monthPnl = dailyRows.reduce((sum, row) => sum + numberValue(row.profitLossAmount), 0);
  const todayKey = compactDate(new Date());
  const todayPnl = numberValue(dailyByDate.get(todayKey)?.profitLossAmount);
  const filledQuantity = brokerFills.reduce((sum, row) => sum + row.quantity, 0);
  const failed = daily.isError || realized.isError || fills.isError;

  return (
    <>
      <TopBar />
      <main className="space-y-3 p-4 animate-fade-in">
        <div>
          <h1 className="text-xl font-semibold">매매 분석</h1>
          <p className="mt-1 text-xs text-muted-foreground">
            키움 실제 계좌 조회 TR의 주문·체결·일별 손익만 표시합니다.
          </p>
        </div>

        <Card>
          <SectionTitle title="실제 계좌 손익" sub="ust21630 · usa21670" />
          <div className="grid gap-2 sm:grid-cols-3">
            <Kpi label="오늘 손익" value={money(todayPnl)} tone={todayPnl} />
            <Kpi label="선택 월 손익" value={money(monthPnl)} tone={monthPnl} />
            <Kpi label="당일 체결 수량" value={`${filledQuantity.toLocaleString()}주`} />
          </div>
          <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
            <SourceBadge label="당일 실현손익" trId={realized.data?.trId ?? "ust21630"} ok={realized.isSuccess} />
            <SourceBadge label="일별 계좌손익" trId={daily.data?.trId ?? "usa21670"} ok={daily.isSuccess} />
            <SourceBadge label="주문·체결" trId={fills.data?.trId ?? "ust21510"} ok={fills.isSuccess} />
          </div>
          {failed ? <Note text="일부 키움 계좌 TR을 불러오지 못했습니다. 임의 데이터로 대체하지 않았습니다." warning /> : null}
        </Card>

        <Card>
          <div className="mb-3 flex items-center justify-between gap-3">
            <SectionTitle title="일별 손익 캘린더" sub="usa21670 일별계좌수익률현황" />
            <div className="flex items-center gap-1">
              <Button size="icon" variant="ghost" aria-label="이전 달" onClick={() => setMonth(addMonths(month, -1))}>
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <span className="min-w-24 text-center text-sm font-semibold">{month.getFullYear()}년 {month.getMonth() + 1}월</span>
              <Button size="icon" variant="ghost" aria-label="다음 달" onClick={() => setMonth(addMonths(month, 1))}>
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
          <div className="grid grid-cols-7 gap-1 text-center text-[10px] text-muted-foreground">
            {WEEKDAYS.map((day) => <div key={day} className="py-1">{day}</div>)}
          </div>
          <div className="grid grid-cols-7 gap-1">
            {calendarDays(month).map(({ date, inMonth }) => {
              const key = compactDate(date);
              const row = dailyByDate.get(key);
              const pnl = numberValue(row?.profitLossAmount);
              return (
                <div key={key} className={cn(
                  "min-h-20 rounded-lg border border-border p-2",
                  inMonth ? "bg-surface-3/40" : "bg-muted/20 text-muted-foreground/40",
                  key === todayKey && "ring-1 ring-primary",
                )}>
                  <div className="text-[11px]">{date.getDate()}</div>
                  {inMonth && row ? (
                    <div className="mt-2 space-y-0.5 text-right">
                      <div className={cn("text-xs font-semibold num", pnl >= 0 ? "text-up" : "text-down")}>{money(pnl)}</div>
                      <div className="text-[10px] text-muted-foreground">{rate(row.returnRate)}</div>
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
          {!daily.isLoading && !dailyRows.length ? <Note text="선택한 달의 키움 일별 손익 내역이 없습니다." /> : null}
        </Card>

        <Card>
          <SectionTitle title="당일 주문·체결 내역" sub="ust21510 실제 계좌 응답" />
          <div className="space-y-2">
            {brokerFills.map((fill, index) => (
              <div key={`${fill.orderNo}-${fill.symbol}-${index}`} className="grid grid-cols-[1fr_auto_auto] items-center gap-3 rounded-lg border border-border bg-surface-3/40 px-3 py-2 text-xs">
                <div>
                  <div className="font-semibold">{fill.symbol || "종목 미확인"}</div>
                  <div className="mt-0.5 text-[10px] text-muted-foreground">주문번호 {maskedOrderNo(fill.orderNo)}</div>
                </div>
                <span className={cn("font-semibold", fill.side === "buy" ? "text-up" : fill.side === "sell" ? "text-down" : "text-muted-foreground")}>{sideLabel(fill.side)}</span>
                <div className="text-right num">
                  <div>{fill.quantity.toLocaleString()}주</div>
                  <div className="text-[10px] text-muted-foreground">{fill.price ? `$${fill.price.toLocaleString()}` : "가격 대기"}</div>
                </div>
              </div>
            ))}
            {!fills.isLoading && !brokerFills.length ? <Note text="오늘 확인된 실제 주문·체결 내역이 없습니다." /> : null}
          </div>
        </Card>
      </main>
    </>
  );
}

function Kpi({ label, value, tone }: { label: string; value: string; tone?: number }) {
  return <div className="rounded-lg border border-border bg-surface-3/40 p-3"><div className="text-[10px] text-muted-foreground">{label}</div><div className={cn("mt-1 text-lg font-semibold num", tone == null ? "" : tone >= 0 ? "text-up" : "text-down")}>{value}</div></div>;
}

function SourceBadge({ label, trId, ok }: { label: string; trId: string; ok: boolean }) {
  return <span className={cn("rounded-full border px-2 py-1", ok ? "border-success/30 text-success" : "border-border")}>{label} · {trId}</span>;
}

function Note({ text, warning = false }: { text: string; warning?: boolean }) {
  return <div className={cn("mt-3 rounded-lg border p-3 text-xs", warning ? "border-warning/30 bg-warning-soft text-warning" : "border-border text-muted-foreground")}>{text}</div>;
}

function startOfMonth(date: Date) { return new Date(date.getFullYear(), date.getMonth(), 1); }
function addMonths(date: Date, amount: number) { return new Date(date.getFullYear(), date.getMonth() + amount, 1); }
function compactDate(date: Date) { return `${date.getFullYear()}${String(date.getMonth() + 1).padStart(2, "0")}${String(date.getDate()).padStart(2, "0")}`; }
function normalizeDate(value: string) { return value.replace(/[^0-9]/g, "").slice(0, 8); }
function numberValue(value: unknown) { const parsed = Number(String(value ?? "0").replace(/,/g, "")); return Number.isFinite(parsed) ? parsed : 0; }
function money(value: number) { return `${value > 0 ? "+" : ""}$${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`; }
function rate(value: string | null | undefined) { const parsed = numberValue(value); return value == null || value === "" ? "수익률 -" : `${parsed > 0 ? "+" : ""}${parsed.toFixed(2)}%`; }
function maskedOrderNo(value: string) { return value ? `••••${value.slice(-4)}` : "-"; }
function sideLabel(side: BrokerFill["side"]) { return side === "buy" ? "매수" : side === "sell" ? "매도" : "구분 없음"; }

function calendarDays(month: Date) {
  const first = startOfMonth(month);
  const gridStart = new Date(first.getFullYear(), first.getMonth(), 1 - first.getDay());
  return Array.from({ length: 42 }, (_, index) => {
    const date = new Date(gridStart.getFullYear(), gridStart.getMonth(), gridStart.getDate() + index);
    return { date, inMonth: date.getMonth() === month.getMonth() };
  });
}

function extractBrokerFills(data: Record<string, unknown> | undefined): BrokerFill[] {
  const raw = data?.result_list ?? data?.result_lsit;
  if (!Array.isArray(raw)) return [];
  return raw.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object").map((item) => ({
    orderNo: String(item.ord_no ?? item.odno ?? item.order_no ?? ""),
    symbol: String(item.stk_code ?? item.stk_cd ?? item.symbol ?? item.code ?? ""),
    side: fillSide(item),
    quantity: numberValue(item.cntr_qty ?? item.exec_qty ?? item.filled_qty ?? item.ord_qty),
    price: numberValue(item.cntr_uv ?? item.exec_price ?? item.filled_price ?? item.ord_uv),
  }));
}

function fillSide(item: Record<string, unknown>): BrokerFill["side"] {
  const code = String(item.slby_tp ?? item.side ?? "").trim();
  const label = String(item.slby_tp_nm ?? item.frgn_trde_nm ?? item.sideName ?? "").toLowerCase();
  if (code === "2" || label.includes("매수") || label.includes("buy")) return "buy";
  if (code === "1" || label.includes("매도") || label.includes("sell")) return "sell";
  return "unknown";
}
