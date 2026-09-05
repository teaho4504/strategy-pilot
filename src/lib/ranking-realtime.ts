import type { MarketRankItem } from "@/types";

export interface RankingRealtimeItem {
  symbol: string;
  latestPrice: number | null;
  latestChangeRate: number | null;
  latestVolume: number | null;
  lastEventAt: string | null;
}

export function mergeRankingRealtime(
  rows: MarketRankItem[],
  realtime: ReadonlyMap<string, RankingRealtimeItem>,
  rankingType: "change-rate" | "volume",
) {
  return rows
    .map((row) => {
      const live = realtime.get(row.code.toUpperCase());
      return {
        ...row,
        price: live?.latestPrice ?? row.price,
        changeRate: live?.latestChangeRate ?? row.changeRate,
        volume: live?.latestVolume ?? row.volume,
      };
    })
    .sort((left, right) => rankingType === "volume"
      ? (right.volume ?? -1) - (left.volume ?? -1)
      : right.changeRate - left.changeRate)
    .map((row, index) => ({ ...row, rank: index + 1 }));
}
