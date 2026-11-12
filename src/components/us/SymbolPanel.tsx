import { Line, LineChart, ResponsiveContainer, YAxis } from "recharts";
import { Check, Circle, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { evaluateSpread, GATE_LABELS } from "@/lib/verification";
import { useNow, usePlan, useQuote } from "./hooks";

const px = (p: number) => `$${p.toFixed(p >= 1 ? 2 : 4)}`;

export function SymbolPanel({ symbol }: { symbol: string | null }) {
  const quote = useQuote(symbol);
  const plan = usePlan(symbol);
  const now = useNow();
  if (!symbol) return <section className="wts-panel text-sm text-muted-foreground">종목을 선택하세요.</section>;
  const q = quote.data;
  const spread = q ? evaluateSpread(q.bid, q.ask) : null;
  const lagSec = q ? Math.max(0, Math.round((now.getTime() - new Date(q.receivedAt).getTime()) / 1000)) : null;

  return (
    <section className="wts-panel space-y-3" aria-label={`${symbol} 상세`}>
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <div className="text-[11px] text-muted-foreground">{q?.exchange} · 조회 전용</div>
          <h2 className="text-xl font-semibold tracking-tight">{symbol}</h2>
        </div>
        {q && (
          <div className="text-right">
            <div className="text-2xl font-semibold num">{px(q.last)}</div>
            <div className={cn("text-sm num", q.changePct >= 0 ? "text-up" : "text-down")}>
              {q.changePct >= 0 ? "+" : ""}{q.changePct.toFixed(2)}%
            </div>
          </div>
        )}
      </div>

      {q && (
        <>
          <div className="h-40 rounded-lg bg-surface-1 p-2" aria-label="수신 체결가 선 (분봉 아님)">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={q.ticks}>
                <YAxis hide domain={["dataMin", "dataMax"]} />
                <Line type="monotone" dataKey="p" dot={false} strokeWidth={1.6} stroke={q.changePct >= 0 ? "hsl(var(--up))" : "hsl(var(--down))"} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="-mt-2 text-[10.5px] text-muted-foreground">화면에서 수신한 체결가 선입니다. 분봉 OHLC 아님.</p>

          <dl className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
            <Stat k="매수호가" v={`${px(q.bid)} × ${q.bidSize.toLocaleString()}`} />
            <Stat k="매도호가" v={`${px(q.ask)} × ${q.askSize.toLocaleString()}`} />
            <Stat k="체결강도" v={String(q.strength)} />
            <Stat k="수신 지연" v={`${lagSec}s`} warn={(lagSec ?? 0) > 5} />
          </dl>

          {spread && (
            <div data-testid="spread-eval" className={cn("rounded-lg border px-3 py-2 text-xs", spread.ok ? "border-success/40 text-success" : "border-danger/40 text-danger")}>
              스프레드 {spread.spreadPct === null ? "—" : `${spread.spreadPct.toFixed(3)}%`} · {spread.rule === "tick" ? "틱 기준" : spread.rule === "pct" ? "0.1% 기준" : "데이터 오류"} · {spread.reason}
            </div>
          )}
        </>
      )}

      {plan.data && (
        <div className="space-y-2">
          <h3 className="text-xs font-semibold text-muted-foreground">2팀 판단표</h3>
          <ol className="flex flex-wrap gap-1.5">
            {plan.data.steps.map((s) => (
              <li key={s.label} className={cn("chip", s.done && "border-success/50 text-success")}>{s.done ? "✓" : "·"} {s.label}</li>
            ))}
          </ol>
          <ul className="divide-y divide-border rounded-lg border border-border">
            {plan.data.criteria.map((c) => {
              const pass = c.key === "spread" && spread ? spread.ok : c.pass;
              return (
                <li key={c.key} className="flex items-center gap-2 px-3 py-1.5 text-xs">
                  {pass === true ? <Check className="h-3.5 w-3.5 text-success" /> : pass === false ? <X className="h-3.5 w-3.5 text-danger" /> : <Circle className="h-3 w-3 text-muted-foreground" />}
                  <span className="flex-1">{c.label}</span>
                  <span className="text-right text-muted-foreground">{c.key === "spread" && spread ? spread.reason : c.detail}</span>
                </li>
              );
            })}
          </ul>
          <div className="flex flex-wrap gap-1.5">
            {plan.data.blockers.map((b) => <span key={b} className="chip border-warning/40 text-warning">{GATE_LABELS[b] ?? b}</span>)}
          </div>
          <p className="text-xs text-muted-foreground">다음 단계: {plan.data.nextAction}</p>
        </div>
      )}
    </section>
  );
}

function Stat({ k, v, warn }: { k: string; v: string; warn?: boolean }) {
  return (
    <div className="rounded-lg bg-surface-1 px-2.5 py-2">
      <dt className="text-[10.5px] text-muted-foreground">{k}</dt>
      <dd className={cn("mt-0.5 num", warn && "text-warning")}>{v}</dd>
    </div>
  );
}
