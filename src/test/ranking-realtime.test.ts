import { describe, expect, it } from "vitest";
import { mergeRankingRealtime, type RankingRealtimeItem } from "@/lib/ranking-realtime";
import type { MarketRankItem } from "@/types";

const rows: MarketRankItem[] = [
  { rank: 1, code: "AAA", name: "AAA", price: 10, changeRate: 2, volume: 100, tradingValue: 1_000, exchange: "ND", reason: "test" },
  { rank: 2, code: "BBB", name: "BBB", price: 20, changeRate: 1, volume: 200, tradingValue: 2_000, exchange: "NY", reason: "test" },
];

function live(symbol: string, price: number, changeRate: number, volume: number): RankingRealtimeItem {
  return { symbol, latestPrice: price, latestChangeRate: changeRate, latestVolume: volume, lastEventAt: "2026-08-13T00:00:00Z" };
}

describe("mergeRankingRealtime", () => {
  it("merges FE/FT values and reorders change-rate ranking", () => {
    const result = mergeRankingRealtime(rows, new Map([
      ["AAA", live("AAA", 11, 2.5, 300)],
      ["BBB", live("BBB", 22, 4.5, 250)],
    ]), "change-rate");

    expect(result.map((item) => item.code)).toEqual(["BBB", "AAA"]);
    expect(result[0]).toMatchObject({ rank: 1, price: 22, changeRate: 4.5, volume: 250 });
  });

  it("reorders volume ranking while keeping REST fallback values", () => {
    const result = mergeRankingRealtime(rows, new Map([
      ["AAA", live("AAA", 11, 2.5, 500)],
    ]), "volume");

    expect(result.map((item) => item.code)).toEqual(["AAA", "BBB"]);
    expect(result[1].price).toBe(20);
  });
});
