import type { UsReadOnlyTrSummary } from "@/types";

export const EXIT_ALERT_THRESHOLD_PCT = 2;

export type HoldingExitAlert = {
  symbol: string;
  name: string;
  exchange: string;
  returnRate: number;
  reason: "take_profit" | "stop_loss";
};

export type HoldingWatchItem = Omit<HoldingExitAlert, "reason"> & {
  reason: HoldingExitAlert["reason"] | "waiting";
  price?: number;
};

export function extractHoldingWatchItems(summary?: UsReadOnlyTrSummary): HoldingWatchItem[] {
  const raw = summary?.data?.result_list ?? summary?.data?.result_lsit;
  if (!Array.isArray(raw)) return [];

  return raw.flatMap((value) => {
    if (!value || typeof value !== "object" || Array.isArray(value)) return [];
    const row = value as Record<string, unknown>;
    const symbol = firstText(row, ["stk_cd", "stk_code", "symbol", "jmcode"]);
    const returnRate = firstNumber(row, ["prft_rt", "evltv_prft_rt", "lspft_rt", "return_rt"]);
    if (!symbol || returnRate === null) return [];
    const price = firstNumber(row, ["cur_prc", "curr_pric", "last_prc", "close_pric"]);
    return [{
      symbol,
      name: firstText(row, ["stk_nm", "frgn_stk_nm", "name", "isu_nm"]) || symbol,
      exchange: normalizeExchange(firstText(row, ["stex_tp", "stex_nm", "ovrs_excg_cd", "excg_cd", "exchange"])),
      returnRate,
      ...(price === null ? {} : { price: Math.abs(price) }),
      reason: returnRate >= EXIT_ALERT_THRESHOLD_PCT
        ? "take_profit" as const
        : returnRate <= -EXIT_ALERT_THRESHOLD_PCT
          ? "stop_loss" as const
          : "waiting" as const,
    }];
  });
}

export function extractHoldingExitAlerts(summary?: UsReadOnlyTrSummary): HoldingExitAlert[] {
  return extractHoldingWatchItems(summary).filter(
    (item): item is HoldingExitAlert => item.reason !== "waiting",
  );
}

function firstText(row: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = row[key];
    if (typeof value !== "string" && typeof value !== "number") continue;
    const text = String(value).trim();
    if (text) return text;
  }
  return "";
}

function firstNumber(row: Record<string, unknown>, keys: string[]): number | null {
  for (const key of keys) {
    const text = String(row[key] ?? "").replace(/,/g, "").replace(/%/g, "").replace("+", "").trim();
    if (!text) continue;
    const value = Number(text);
    if (Number.isFinite(value)) return value;
  }
  return null;
}

function normalizeExchange(value: string): string {
  const normalized = value.toUpperCase().replace(/[\s_-]/g, "");
  if (normalized.includes("NASDAQ") || normalized.includes("나스닥") || normalized === "ND") return "ND";
  if (normalized.includes("NYSE") || normalized.includes("뉴욕") || normalized === "NY") return "NY";
  if (normalized.includes("AMEX") || normalized.includes("아멕스") || normalized === "NA") return "NA";
  return "ND";
}
