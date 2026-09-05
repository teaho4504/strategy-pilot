import type { UsRealtimeWindowItem } from "@/types";

export const REALTIME_FRESHNESS_THRESHOLD_MS = 10_000;
export const REALTIME_DELAY_THRESHOLD_MS = 2_000;

export type RealtimeFreshness = {
  state: "fresh" | "stale" | "missing";
  ageMs: number | null;
  receiveDelayMs: number | null;
  delayed: boolean;
};

export function getRealtimeFreshness(
  item?: Pick<UsRealtimeWindowItem, "lastEventAt" | "receiveDelayMs">,
  nowMs = Date.now(),
  thresholdMs = REALTIME_FRESHNESS_THRESHOLD_MS,
): RealtimeFreshness {
  const receiveDelayMs = item?.receiveDelayMs == null
    ? null
    : Math.max(0, Math.round(item.receiveDelayMs));
  const delayed = receiveDelayMs !== null && receiveDelayMs > REALTIME_DELAY_THRESHOLD_MS;
  if (!item?.lastEventAt) return { state: "missing", ageMs: null, receiveDelayMs, delayed };

  const eventMs = Date.parse(item.lastEventAt);
  if (!Number.isFinite(eventMs)) return { state: "missing", ageMs: null, receiveDelayMs, delayed };

  const rawAgeMs = nowMs - eventMs;
  return {
    state: rawAgeMs >= 0 && rawAgeMs <= thresholdMs ? "fresh" : "stale",
    ageMs: Math.max(0, rawAgeMs),
    receiveDelayMs,
    delayed,
  };
}

export function formatDataAge(ageMs: number | null): string {
  if (ageMs === null) return "수신 기록 없음";
  if (ageMs < 1_000) return "방금 전";
  const seconds = Math.floor(ageMs / 1_000);
  if (seconds < 60) return `${seconds}초 전`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}분 전`;
  return `${Math.floor(minutes / 60)}시간 전`;
}
