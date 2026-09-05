import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { Card } from "@/components/common/Card";
import { readonlyApiClient } from "@/services/apiClient";
import type { UsReadOnlyTrSummary, UsRealtimeWindowItem } from "@/types";
import { cn } from "@/lib/utils";

type HoldingAllocation = {
  symbol: string;
  name: string;
  exchange: string;
  quantity: number | null;
  valuationAmount: number;
  profitLoss: number | null;
  returnRate: number | null;
  price: number | null;
};

export function PortfolioCard() {
  const cash = useQuery({
    queryKey: ["portfolio-card", "us-cash"],
    queryFn: readonlyApiClient.usCash,
    retry: false,
    refetchInterval: 5_000,
    refetchIntervalInBackground: false,
    staleTime: 3_000,
  });
  const valuation = useQuery({
    queryKey: ["portfolio-card", "us-valuation"],
    queryFn: readonlyApiClient.usValuation,
    retry: false,
    refetchInterval: 5_000,
    refetchIntervalInBackground: false,
    staleTime: 3_000,
  });
  const holdings = useQuery({
    queryKey: ["portfolio-card", "us-holdings"],
    queryFn: readonlyApiClient.usHoldings,
    retry: false,
    refetchInterval: 5_000,
    refetchIntervalInBackground: false,
    staleTime: 3_000,
  });
  const orderStatus = useQuery({
    queryKey: ["portfolio-card", "us-order-status"],
    queryFn: readonlyApiClient.usOrderStatus,
    retry: false,
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
    staleTime: 15_000,
  });
  const symbols = holdingSymbols(holdings.data);
  const exchanges = holdingExchangeMap(holdings.data);
  const realtime = useQuery({
    queryKey: ["portfolio-card", "us-holdings-realtime", symbols.join(",")],
    queryFn: () => readonlyApiClient.usRealtimeWindow(symbols, exchanges),
    enabled: symbols.length > 0,
    retry: false,
    refetchInterval: 5_000,
    refetchIntervalInBackground: false,
    staleTime: 3_000,
  });

  const loading = cash.isLoading || valuation.isLoading || holdings.isLoading;
  const error =
    (cash.error && !cash.data) ||
    (valuation.error && !valuation.data) ||
    (holdings.error && !holdings.data);
  const rows = buildHoldingAllocations(holdings.data, realtime.data?.items ?? []);
  const exitAlerts = rows.filter((row) => row.returnRate !== null && Math.abs(row.returnRate) >= 2);
  const summary = buildUsPortfolioSummary(cash.data, valuation.data, rows);
  const capitalUsagePct = orderStatus.data?.capitalUsagePct ?? 50;
  const managedCashUsd = summary.orderableCashUsd === null ? null : summary.orderableCashUsd * capitalUsagePct / 100;
  const reserveCashUsd = summary.orderableCashUsd === null ? null : summary.orderableCashUsd - (managedCashUsd ?? 0);
  const totalPnlUp = summary.totalProfitLoss === null ? null : summary.totalProfitLoss >= 0;

  return (
    <Card className="overflow-hidden p-0">
      <div className="border-b border-border bg-surface-2/80 px-4 py-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-xs font-semibold text-muted-foreground">평가자산</div>
            <div className="mt-1 text-[11px] text-muted-foreground">5초마다 최신 계좌 상태를 확인합니다.</div>
          </div>
          <div className="flex items-center gap-1 rounded-lg border border-border bg-background/50 px-2 py-1 text-[11px] text-muted-foreground">
            <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
            {loading ? "조회 중" : "갱신"}
          </div>
        </div>
      </div>

      <div className="space-y-3 p-4">
        {exitAlerts.length ? (
          <div className="rounded-xl border border-warning/45 bg-warning-soft/45 p-3" role="status" aria-live="polite">
            <div className="flex items-center gap-2 text-sm font-semibold text-warning">
              <AlertTriangle className="h-4 w-4" />
              매도 검토 알림 {exitAlerts.length}건
            </div>
            <div className="mt-2 space-y-1.5">
              {exitAlerts.map((row) => (
                <div key={`${row.exchange}-${row.symbol}-exit-alert`} className="flex items-center justify-between gap-3 rounded-lg bg-background/45 px-3 py-2 text-xs">
                  <span className="truncate font-semibold">{row.name || row.symbol} · {row.symbol}</span>
                  <span className={cn("num shrink-0 font-bold", (row.returnRate ?? 0) >= 2 ? "text-up" : "text-down")}>
                    {formatSignedPercent(row.returnRate)} · {(row.returnRate ?? 0) >= 2 ? "익절 검토" : "손절 검토"}
                  </span>
                </div>
              ))}
            </div>
            <p className="mt-2 text-[10.5px] leading-4 text-warning/90">5초마다 실계좌 잔고를 확인합니다. 알림만 제공하며 매도 주문은 전송하지 않습니다.</p>
          </div>
        ) : null}

        <div className="grid grid-cols-3 overflow-hidden rounded-xl border border-border bg-background/45">
          <MetricTab
            label="평가손익"
            value={formatSignedMoney(summary.totalProfitLoss, "원")}
            subValue={`${formatSignedUsd(summary.totalProfitLossUsd)} · ${formatSignedPercent(summary.totalReturnRate)}`}
            tone={totalPnlUp === null ? undefined : totalPnlUp ? "up" : "down"}
          />
          <MetricTab
            label="평가금"
            value={formatMoney(summary.valuationAmount, "원")}
            subValue={formatMoney(summary.valuationAmountUsd, "USD")}
          />
          <MetricTab
            label="주문가능"
            value={formatMoney(summary.orderableCashKrw, "원")}
            subValue={formatMoney(summary.orderableCashUsd, "USD")}
          />
        </div>

        <div className="grid grid-cols-2 overflow-hidden rounded-xl border border-primary/25 bg-primary/5">
          <MetricTab
            label={`운용 가능 · ${capitalUsagePct.toLocaleString("ko-KR", { maximumFractionDigits: 1 })}%`}
            value={formatMoney(managedCashUsd, "USD")}
            subValue="자동배분에 사용하는 최대 예수금"
          />
          <MetricTab
            label={`현금 유보 · ${(100 - capitalUsagePct).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}%`}
            value={formatMoney(reserveCashUsd, "USD")}
            subValue="신규 진입에 사용하지 않는 예수금"
          />
        </div>

        {error ? (
          <div className="rounded-xl border border-warning/40 bg-warning-soft/40 px-3 py-2 text-[11px] text-warning">
            일부 계좌 정보를 불러오지 못해 최신 잔고와 평가금액이 다를 수 있습니다.
          </div>
        ) : null}

        <div className="overflow-hidden rounded-xl border border-border bg-background/45">
          <div className="border-b border-border bg-surface-3/80 px-3 py-2">
            <div className="text-xs font-semibold">보유종목</div>
            <div className="mt-0.5 text-[10.5px] text-muted-foreground">종목별 수익률, 수익금, 보유수량만 간단히 표시</div>
          </div>
          <div className="overflow-x-auto">
            <div className="min-w-[480px]">
              <div className="grid grid-cols-[150px_90px_130px_90px] border-b border-border bg-surface-3/60 px-3 py-2 text-right text-[11px] font-semibold text-muted-foreground">
                <span className="text-left">종목</span>
                <span>수익률</span>
                <span>수익금</span>
                <span>보유수량</span>
              </div>

              {rows.length ? (
                rows.slice(0, 12).map((row) => <HoldingTableRow key={`${row.exchange}-${row.symbol}`} row={row} exchangeRate={summary.exchangeRate} />)
              ) : (
                <div className="px-3 py-6 text-center text-xs text-muted-foreground">
                  현재 표시 가능한 미국주식 보유종목이 없습니다.
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </Card>
  );
}

function MetricTab({ label, value, subValue, tone }: { label: string; value: string; subValue?: string; tone?: "up" | "down" }) {
  const toneClass = tone === "up" ? "text-up" : tone === "down" ? "text-down" : "text-foreground";
  return (
    <div className="border-r border-border px-3 py-3 last:border-r-0">
      <div className="text-[11px] font-semibold text-muted-foreground">{label}</div>
      <div className={cn("mt-1 truncate num text-sm font-bold", toneClass)}>{value}</div>
      {subValue ? <div className={cn("mt-0.5 truncate num text-[10.5px]", tone ? toneClass : "text-muted-foreground")}>{subValue}</div> : null}
    </div>
  );
}

function HoldingTableRow({ row, exchangeRate }: { row: HoldingAllocation; exchangeRate: number | null }) {
  const pnlUp = (row.profitLoss ?? 0) >= 0;
  const quotePath = `/quotes?symbol=${encodeURIComponent(row.symbol)}&exchange=${encodeURIComponent(normalizeQuoteExchange(row.exchange))}`;
  return (
    <Link to={quotePath} className="block border-b border-border px-3 py-3 last:border-b-0 hover:bg-primary/5 active:bg-primary/10">
      <div className="grid grid-cols-[150px_90px_130px_90px] items-center gap-0 text-right text-sm">
        <div className="min-w-0">
          <div className="truncate font-semibold text-foreground">{row.name || row.symbol}</div>
          <div className="mt-0.5 flex items-center gap-1 text-[11px] text-muted-foreground">
            <span>{row.symbol}</span>
            <span className="rounded bg-primary/10 px-1 py-0.5 text-[10px] font-semibold text-primary">{row.exchange}</span>
          </div>
        </div>
        <div className={cn("num font-bold", pnlUp ? "text-up" : "text-down")}>
          {row.returnRate === null ? "-" : formatSignedPercent(row.returnRate)}
        </div>
        <div className="num">
          <div className={cn("font-bold", pnlUp ? "text-up" : "text-down")}>{row.profitLoss === null ? "-" : formatSignedUsd(row.profitLoss)}</div>
          <div className={cn("text-[11px]", pnlUp ? "text-up" : "text-down")}>{row.profitLoss === null || exchangeRate === null ? "-" : formatSignedMoney(row.profitLoss * exchangeRate, "원")}</div>
        </div>
        <div className="num font-semibold">{formatQuantity(row.quantity)}</div>
      </div>
    </Link>
  );
}

function buildUsPortfolioSummary(
  cash?: UsReadOnlyTrSummary,
  valuation?: UsReadOnlyTrSummary,
  holdings: HoldingAllocation[] = [],
) {
  const cashRow = firstObject(cash?.data?.result_list);
  const valuationRow = firstObject(valuation?.data?.result_list);
  const exchangeRate = firstNumber(cashRow, ["exrt"]) ?? firstNumber(valuationRow, ["exrt"]);
  const valuationFromHoldings = holdings.reduce((sum, row) => sum + row.valuationAmount, 0);
  const pnlFromHoldings = holdings.reduce((sum, row) => sum + (row.profitLoss ?? 0), 0);
  const valuationAmountKrw =
    firstNumber(valuation?.normalized, ["valuationAmount", "depositAsset"]) ??
    firstNumber(valuation?.data, ["aset_evlt_amt", "tot_evlt_amt", "chg_evlt_amt"]) ??
    firstNumber(valuationRow, ["chg_evlt_amt"]) ??
    (valuationFromHoldings > 0 && exchangeRate !== null ? valuationFromHoldings * exchangeRate : null);
  const purchaseAmount =
    firstNumber(valuation?.normalized, ["purchaseAmount"]) ??
    firstNumber(valuation?.data, ["tot_pur_amt", "buy_amt"]) ??
    firstNumber(valuationRow, ["tot_pur_amt", "buy_amt"]);
  const totalProfitLossKrw =
    firstNumber(valuation?.normalized, ["profitLoss", "totalProfitLoss"]) ??
    firstNumber(valuation?.data, ["pl_amt", "lspft_amt", "evltv_prft"]) ??
    firstNumber(valuationRow, ["pl_amt", "lspft_amt", "evltv_prft"]) ??
    (holdings.length > 0 && exchangeRate !== null ? pnlFromHoldings * exchangeRate : null);
  const cashValue =
    firstNumber(cash?.normalized, ["cashAmount"]) ??
    firstNumber(cashRow, ["fc_entra"]) ??
    firstNumber(cash?.data, ["krw_entra", "cash"]);
  const orderableCash =
    firstNumber(cash?.normalized, ["orderableAmount"]) ??
    firstNumber(cashRow, ["fc_ord_alowa", "fc_pymn_alowa"]) ??
    firstNumber(cash?.data, ["ord_alow_amt", "ord_psbl_amt"]);
  const totalReturnRate =
    firstNumber(valuation?.normalized, ["returnRate", "totalReturnRate"]) ??
    firstNumber(valuation?.data, ["prft_rt", "lspft_rt"]) ??
    firstNumber(valuationRow, ["prft_rt", "lspft_rt"]) ??
    (purchaseAmount !== null && purchaseAmount > 0 && totalProfitLossKrw !== null ? (totalProfitLossKrw / purchaseAmount) * 100 : null);

  return {
    purchaseAmount,
    valuationAmount: valuationAmountKrw,
    valuationAmountUsd: valuationFromHoldings > 0 ? valuationFromHoldings : valuationAmountKrw !== null && exchangeRate ? valuationAmountKrw / exchangeRate : null,
    cash: cashValue,
    orderableCashUsd: orderableCash,
    orderableCashKrw: orderableCash !== null && exchangeRate !== null ? orderableCash * exchangeRate : null,
    totalProfitLoss: totalProfitLossKrw,
    totalProfitLossUsd: holdings.length > 0 ? pnlFromHoldings : totalProfitLossKrw !== null && exchangeRate ? totalProfitLossKrw / exchangeRate : null,
    totalReturnRate,
    exchangeRate,
    cashCurrency: stringValue(cash?.normalized?.currency) || stringValue(cashRow?.crnc_code) || stringValue(cashRow?.crnc_nm) || "USD",
  };
}

function buildHoldingAllocations(summary?: UsReadOnlyTrSummary, realtimeRows: UsRealtimeWindowItem[] = []): HoldingAllocation[] {
  const rows = resultRows(summary?.data);
  const realtimeBySymbol = new Map(realtimeRows.map((row) => [row.symbol.toUpperCase(), row]));
  const mapped = rows
    .map((row) => {
      const symbol = firstString(row, ["stk_cd", "symbol", "jmcode"]);
      if (!symbol) return null;
      const name = firstString(row, ["stk_nm", "frgn_stk_nm", "name", "isu_nm"]) ?? "";
      const exchange = normalizeExchange(firstString(row, ["stex_tp", "stex_nm", "ovrs_excg_cd", "excg_cd", "exchange"]));
      const quantity = firstNumber(row, ["hldg_qty", "cur_qty", "rmnd_qty", "jan_qty", "qty", "poss_qty"]);
      const balancePrice = firstNumber(row, ["now_pric", "cur_prc", "last", "evlt_pric", "avg_pric"]);
      const realtime = realtimeBySymbol.get(symbol.toUpperCase());
      const realtimePrice = validPositiveNumber(realtime?.latestPrice);
      const price = realtimePrice ?? balancePrice;
      const explicitValue = firstNumber(row, ["evlt_amt", "stk_evlta", "evltv", "evlt_amt_tot", "frgn_stk_evlta"]);
      const valuationAmount = realtimePrice !== null ? (quantity ?? 0) * realtimePrice : explicitValue ?? ((quantity ?? 0) * (price ?? 0));
      return {
        symbol,
        name,
        exchange,
        quantity,
        valuationAmount: Number.isFinite(valuationAmount) ? valuationAmount : 0,
        profitLoss: firstNumber(row, ["pl_amt", "evltv_prft", "lspft_amt", "prft_amt"]),
        returnRate: firstNumber(row, ["prft_rt", "evltv_prft_rt", "lspft_rt", "return_rt"]),
        price,
      };
    })
    .filter((row): row is HoldingAllocation => Boolean(row))
    .filter((row) => (row.quantity ?? 0) > 0 || row.valuationAmount > 0);

  return mapped.sort((a, b) => b.valuationAmount - a.valuationAmount);
}

function holdingSymbols(summary?: UsReadOnlyTrSummary): string[] {
  const symbols: string[] = [];
  for (const row of resultRows(summary?.data)) {
    const symbol = firstString(row, ["stk_cd", "symbol", "jmcode"])?.toUpperCase();
    if (symbol && !symbols.includes(symbol)) symbols.push(symbol);
    if (symbols.length >= 20) break;
  }
  return symbols;
}

function holdingExchangeMap(summary?: UsReadOnlyTrSummary): Record<string, string> {
  const exchanges: Record<string, string> = {};
  for (const row of resultRows(summary?.data)) {
    const symbol = firstString(row, ["stk_cd", "symbol", "jmcode"])?.toUpperCase();
    if (!symbol) continue;
    exchanges[symbol] = normalizeQuoteExchange(
      normalizeExchange(firstString(row, ["stex_tp", "stex_nm", "ovrs_excg_cd", "excg_cd", "exchange"])),
    );
  }
  return exchanges;
}

function resultRows(data: Record<string, unknown> | undefined): Record<string, unknown>[] {
  const raw = data?.result_list ?? data?.result_lsit;
  if (!Array.isArray(raw)) return [];
  return raw.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object" && !Array.isArray(item));
}

function firstObject(value: unknown): Record<string, unknown> | undefined {
  if (!Array.isArray(value)) return undefined;
  const first = value.find((item) => item && typeof item === "object" && !Array.isArray(item));
  return first as Record<string, unknown> | undefined;
}

function firstString(row: Record<string, unknown>, keys: string[]): string | null {
  for (const key of keys) {
    const value = row[key];
    if (typeof value !== "string" && typeof value !== "number") continue;
    const trimmed = String(value).trim();
    if (trimmed) return trimmed;
  }
  return null;
}

function firstNumber(data: Record<string, unknown> | null | undefined, keys: string[]): number | null {
  if (!data) return null;
  for (const key of keys) {
    const parsed = parseNumber(data[key]);
    if (parsed !== null) return parsed;
  }
  return null;
}

function parseNumber(value: unknown): number | null {
  if (value === null || value === undefined) return null;
  const normalized = String(value).replace(/,/g, "").replace(/%/g, "").replace("+", "").trim();
  if (!normalized) return null;
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

function validPositiveNumber(value: unknown): number | null {
  const parsed = parseNumber(value);
  return parsed !== null && parsed > 0 ? parsed : null;
}

function stringValue(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed || null;
}

function normalizeExchange(value: string | null): string {
  const normalized = String(value || "").trim().toUpperCase().replace(/[\s_-]/g, "");
  if (normalized.includes("NASDAQ") || normalized === "NASD" || normalized === "NAS" || normalized === "ND" || normalized.includes("나스닥")) return "ND";
  if (normalized.includes("NYSE") || normalized.includes("NEWYORK") || normalized === "NY" || normalized.includes("뉴욕")) return "NY";
  if (normalized.includes("AMEX") || normalized.includes("AMERICAN") || normalized === "NA" || normalized.includes("아멕스")) return "NA";
  return value?.trim() || "ND";
}

function normalizeQuoteExchange(value: string): string {
  return ["NA", "ND", "NY"].includes(value) ? value : "ND";
}

function formatMoney(value: number | null, currency = "") {
  if (value === null || !Number.isFinite(value)) return "-";
  const digits = currency === "원" || currency === "KRW" ? 0 : 2;
  const formatted = value.toLocaleString("ko-KR", { maximumFractionDigits: digits });
  return currency ? `${formatted}${currency === "원" ? "" : ` ${currency}`}` : formatted;
}

function formatSignedMoney(value: number | null, currency = "") {
  if (value === null || !Number.isFinite(value)) return "-";
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatMoney(value, currency)}`;
}

function formatSignedUsd(value: number | null) {
  if (value === null || !Number.isFinite(value)) return "-";
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatMoney(value, "USD")}`;
}

function formatSignedPercent(value: number | null) {
  if (value === null || !Number.isFinite(value)) return "-";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toLocaleString("ko-KR", { maximumFractionDigits: 2 })}%`;
}

function formatQuantity(value: number | null) {
  if (value === null || !Number.isFinite(value)) return "-";
  return value.toLocaleString("ko-KR", { maximumFractionDigits: 4 });
}
