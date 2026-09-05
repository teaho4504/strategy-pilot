import { describe, expect, it } from "vitest";
import { extractHoldingExitAlerts, extractHoldingWatchItems } from "@/lib/exit-alerts";
import type { UsReadOnlyTrSummary } from "@/types";

function summary(resultList: Record<string, unknown>[]): UsReadOnlyTrSummary {
  return { trId: "ust21070", returnCode: "0", returnMessage: "", schemaKeys: [], data: { result_list: resultList }, source: "test", updatedAt: "2026-08-12T00:00:00Z" };
}

describe("extractHoldingExitAlerts", () => {
  it("returns only holdings at or beyond the ±2% threshold", () => {
    const alerts = extractHoldingExitAlerts(summary([
      { stk_cd: "AAA", stk_nm: "Alpha", stex_tp: "ND", prft_rt: "2.10" },
      { stk_cd: "BBB", stk_nm: "Beta", stex_tp: "NY", prft_rt: "-2.00" },
      { stk_cd: "CCC", stk_nm: "Gamma", stex_tp: "NA", prft_rt: "1.99" },
    ]));

    expect(alerts).toEqual([
      { symbol: "AAA", name: "Alpha", exchange: "ND", returnRate: 2.1, reason: "take_profit" },
      { symbol: "BBB", name: "Beta", exchange: "NY", returnRate: -2, reason: "stop_loss" },
    ]);
  });

  it("keeps sub-threshold holdings in the watch list as waiting", () => {
    expect(extractHoldingWatchItems(summary([{ stk_cd: "CCC", prft_rt: "1.99", cur_prc: "-42.50" }]))[0]).toMatchObject({
      symbol: "CCC",
      returnRate: 1.99,
      price: 42.5,
      reason: "waiting",
    });
  });
});
