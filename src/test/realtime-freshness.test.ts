import { describe, expect, it } from "vitest";
import { formatDataAge, getRealtimeFreshness } from "@/lib/realtime-freshness";
import type { UsRealtimeWindowItem } from "@/types";

function item(overrides: Partial<UsRealtimeWindowItem> = {}): UsRealtimeWindowItem {
  return {
    symbol: "NVDA",
    tickCount: 1,
    orderbookCount: 1,
    latestPrice: 100,
    latestVolume: 10,
    volume10sDelta: null,
    volume10sIncreasing: null,
    tradeStrength: null,
    tradeStrengthIncreasing: null,
    bid: 99.9,
    ask: 100.1,
    spreadPct: 0.2,
    spreadWithin01Pct: false,
    lastEventAt: "2026-08-12T00:00:00Z",
    sourceEventTime: null,
    receiveDelayMs: 150,
    persistedEventCount: 0,
    dbEvents10s: 0,
    dbEvents1m: 0,
    dbEvents5m: 0,
    dbVolume10sDelta: null,
    dbVolume1mDelta: null,
    dbVolume5mDelta: null,
    dbTradeStrength1mChange: null,
    dbSpreadPct: null,
    ...overrides,
  };
}

describe("getRealtimeFreshness", () => {
  it("separates fresh, stale, and delayed realtime data", () => {
    const now = Date.parse("2026-08-12T00:00:08Z");
    expect(getRealtimeFreshness(item(), now)).toMatchObject({ state: "fresh", ageMs: 8_000, delayed: false });
    expect(getRealtimeFreshness(item({ lastEventAt: "2026-08-11T23:59:40Z", receiveDelayMs: 2_001 }), now)).toMatchObject({ state: "stale", ageMs: 28_000, delayed: true });
  });

  it("treats absent or invalid event timestamps as missing", () => {
    expect(getRealtimeFreshness(item({ lastEventAt: null })).state).toBe("missing");
    expect(getRealtimeFreshness(item({ lastEventAt: "invalid" })).state).toBe("missing");
  });
});

describe("formatDataAge", () => {
  it("formats compact Korean age labels", () => {
    expect(formatDataAge(null)).toBe("수신 기록 없음");
    expect(formatDataAge(8_500)).toBe("8초 전");
    expect(formatDataAge(125_000)).toBe("2분 전");
  });
});
