/**
 * 미국 주식 운영 콘솔 데이터 클라이언트 — 조회(GET) 전용.
 *
 * - VITE_US_API_BASE 미설정 → 모든 데이터 mock (클라우드/Lovable 미리보기 기본)
 * - VITE_US_API_BASE 설정   → 인계서에 확인된 엔드포인트만 실서버 조회
 *     GET {base}/api/health
 *     GET {base}/api/us/orders/control/status
 *   나머지(TOP10·시세·판단표·검증)는 실서버 경로가 이 저장소에 없어 mock 유지.
 *   응답 출처는 항상 `source`로 표시한다.
 *
 * 이 파일에는 POST/PUT/DELETE를 추가하지 않는다. 주문·관리자 ON·자동매매 ON은
 * Mac 로컬 대시보드에서 사용자가 직접 수행한다 (AGENTS.md 실주문 게이트).
 */
import type { ControlStatus, HealthStatus } from "@/types/us";
import { mockControl, mockHealth } from "./mock";

export type Source = "live" | "mock" | "live-error";
export interface Sourced<T> { data: T; source: Source; error?: string }

const BASE = (import.meta.env.VITE_US_API_BASE as string | undefined)?.replace(/\/$/, "") || "";
export const liveConfigured = BASE.length > 0;

async function getJson(path: string): Promise<unknown> {
  const res = await fetch(`${BASE}${path}`, { method: "GET", credentials: "include", headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

type Obj = Record<string, unknown>;
const bool = (o: Obj, ...keys: string[]) => keys.map((k) => o[k]).find((v) => typeof v === "boolean") as boolean | undefined;
const arr = (v: unknown) => (Array.isArray(v) ? v.map(String) : []);

export function normalizeHealth(raw: unknown): HealthStatus {
  const o = (raw ?? {}) as Obj;
  return {
    ok: bool(o, "ok") ?? true,
    readOnly: bool(o, "readOnly", "read_only") ?? true,
    orderEnabled: bool(o, "orderEnabled", "order_enabled") ?? false,
    emergencyStop: bool(o, "emergencyStop", "emergency_stop", "killSwitch") ?? true,
    adminEnabled: bool(o, "adminEnabled", "admin_enabled") ?? false,
    runnerEnabled: bool(o, "runnerEnabled", "runner_enabled") ?? false,
    serverTime: String(o.serverTime ?? o.server_time ?? new Date().toISOString()),
  };
}

export function normalizeControl(raw: unknown): ControlStatus {
  const o = (raw ?? {}) as Obj;
  const sk = ((o.sessionKeeper ?? o.session_keeper ?? {}) as Obj);
  return {
    blockers: arr(o.blockers ?? o.orderBlockers),
    team2Blockers: arr(o.team2Blockers ?? o.team2_blockers),
    legacyUnresolved: Number(o.legacyUnresolved ?? o.legacy_unresolved ?? 0),
    sessionKeeper: {
      expiresAt: (sk.expiresAt ?? sk.expires_at ?? null) as string | null,
      lastRenewedAt: (sk.lastRenewedAt ?? sk.last_renewed_at ?? null) as string | null,
      lastError: (sk.lastError ?? sk.last_error ?? null) as string | null,
      backoffUntil: (sk.backoffUntil ?? sk.backoff_until ?? null) as string | null,
    },
  };
}

async function liveOrMock<T>(path: string, normalize: (r: unknown) => T, mock: () => T): Promise<Sourced<T>> {
  if (!liveConfigured) return { data: mock(), source: "mock" };
  try {
    return { data: normalize(await getJson(path)), source: "live" };
  } catch (e) {
    // 실서버 조회 실패 시 잠금 상태 mock으로 대체하지 않는다: 안전측(차단) 값으로 표시
    return { data: normalize({}), source: "live-error", error: (e as Error).message };
  }
}

export const usClient = {
  health: () => liveOrMock("/api/health", normalizeHealth, mockHealth),
  control: () => liveOrMock("/api/us/orders/control/status", normalizeControl, mockControl),
};
