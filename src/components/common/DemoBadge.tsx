import { cn } from "@/lib/utils";

export function DemoBadge({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border border-warning/40 bg-warning-soft px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-wide text-warning",
        className
      )}
      title="이 화면은 모의투자 데모 데이터입니다."
    >
      <span className="h-1.5 w-1.5 rounded-full bg-warning" />
      모의투자
    </span>
  );
}

export function StatusDot({ status }: { status: "running" | "idle" | "paused" | "error" }) {
  const map = {
    running: "bg-success animate-pulse",
    idle: "bg-flat",
    paused: "bg-warning",
    error: "bg-danger",
  } as const;
  return <span className={cn("inline-block h-2 w-2 rounded-full", map[status])} />;
}

export function StatusBadge({ status }: { status: "running" | "idle" | "paused" | "error" }) {
  const labels = { running: "실행 중", idle: "대기", paused: "일시정지", error: "오류" };
  const tone = {
    running: "border-success/40 bg-success/10 text-success",
    idle: "border-border bg-muted text-muted-foreground",
    paused: "border-warning/40 bg-warning-soft text-warning",
    error: "border-danger/40 bg-danger-soft text-danger",
  }[status];
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium", tone)}>
      <StatusDot status={status} />
      {labels[status]}
    </span>
  );
}
