import { cn } from "@/lib/utils";
import { pct } from "@/lib/format";

export function DeltaPct({ value, className }: { value: number; className?: string }) {
  const tone = value > 0 ? "text-up" : value < 0 ? "text-down" : "text-flat";
  return (
    <span className={cn("num font-semibold", tone, className)}>
      {pct(value)}
    </span>
  );
}
