import { cn } from "@/lib/utils";
import { safeError } from "@/services/apiClient";

export function ApiModeBadge({ mode, readOnly }: { mode?: string; readOnly?: boolean }) {
  const isLive = mode === "live";
  const label = isLive && readOnly ? "LIVE READ-ONLY" : mode === "mock" ? "MOCK" : "BACKEND";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-wide",
        isLive ? "border-success/40 bg-success/10 text-success" : "border-warning/40 bg-warning-soft text-warning"
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", isLive ? "bg-success" : "bg-warning")} />
      {label}
    </span>
  );
}

export function ApiInlineState({ isLoading, error }: { isLoading?: boolean; error?: unknown }) {
  if (isLoading) return <p className="text-[11px] text-muted-foreground">LOADING · backend 데이터를 불러오는 중</p>;
  if (!error) return null;
  const safe = safeError(error);
  return (
    <p className="text-[11px] text-warning">
      {safe.type === "backend_offline" ? "BACKEND OFFLINE" : "KIWOOM CONNECTION ERROR"} · {safe.endpoint}
      {safe.status ? ` · HTTP ${safe.status}` : ""}
    </p>
  );
}

export function ApiErrorBox({ error }: { error: unknown }) {
  const safe = safeError(error);
  return (
    <div className="rounded-xl border border-warning/30 bg-warning-soft/40 px-3 py-2 text-[11px] text-warning">
      <div className="font-semibold">{safe.type === "backend_offline" ? "BACKEND OFFLINE" : "KIWOOM CONNECTION ERROR"}</div>
      <div className="mt-1 text-warning/80">
        endpoint={safe.endpoint}{safe.status ? ` · http=${safe.status}` : ""} · {safe.guidance}
      </div>
    </div>
  );
}
