import { useEffect, useMemo, useState } from "react";
import { Activity, Bot, BrainCircuit, Check, CirclePause, Clock3, DatabaseZap, GitBranch, Play, Radio, RefreshCw, Send, ShieldCheck, Sparkles } from "lucide-react";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type AgentStatus = "queued" | "working" | "done";
type StageTone = "cyan" | "blue" | "violet" | "amber" | "green";

export const AGENT_STAGES = [
  { id: "condition_intake", label: "조건검색 인테이크", role: "후보 검증 · 정규화", phase: 0, lane: "serial", tone: "cyan" as StageTone, icon: DatabaseZap, detail: "이벤트 순서, 조건식 등록, 심볼·거래소 매핑을 검증합니다." },
  { id: "realtime_market_analyst", label: "실시간 시장 분석", role: "REST 캔들 · FE/FT", phase: 1, lane: "parallel", tone: "blue" as StageTone, icon: Radio, detail: "5분봉 추세, VWAP, ATR, 호가 스프레드와 데이터 신선도를 확인합니다." },
  { id: "pullback_pattern_learner", label: "눌림 패턴 평가", role: "승인 버전 · 워크포워드", phase: 1, lane: "parallel", tone: "violet" as StageTone, icon: BrainCircuit, detail: "승인된 패턴 버전만 적용하고 미래 데이터 누수를 차단합니다." },
  { id: "risk_signal_gate", label: "독립 리스크 게이트", role: "Fail closed", phase: 2, lane: "serial", tone: "amber" as StageTone, icon: ShieldCheck, detail: "불일치·지연·미확인 상태가 하나라도 있으면 신호를 거절합니다." },
  { id: "signal_publisher", label: "신호 퍼블리셔", role: "Dashboard · Paper", phase: 3, lane: "serial", tone: "green" as StageTone, icon: Send, detail: "승인된 advisory 신호에 만료와 멱등 키를 붙여 발행합니다." },
] as const;

export const SAMPLE_SIGNAL = {
  signalId: "SIG-NVDA-0829-001", symbol: "NVDA", exchange: "NASDAQ", signal: "BUY_SIGNAL",
  confidence: 0.82, referencePrice: 179.42, invalidationPrice: 177.98,
  destination: "dashboard", executionAuthorized: false,
} as const;

const PHASE_COUNT = 4;

export default function AgentOperations() {
  const [phase, setPhase] = useState(0);
  const [playing, setPlaying] = useState(true);

  useEffect(() => {
    if (!playing) return;
    if (phase >= PHASE_COUNT) { setPlaying(false); return; }
    const timer = window.setTimeout(() => setPhase((value) => value + 1), phase === 1 ? 1500 : 1100);
    return () => window.clearTimeout(timer);
  }, [phase, playing]);

  const statuses = useMemo(() => new Map(AGENT_STAGES.map((stage) => [
    stage.id, stage.phase < phase ? "done" : stage.phase === phase ? "working" : "queued",
  ] as const)), [phase]);
  const completed = AGENT_STAGES.filter((stage) => statuses.get(stage.id) === "done").length;
  const active = AGENT_STAGES.filter((stage) => statuses.get(stage.id) === "working").length;
  const finished = phase >= PHASE_COUNT;

  const restart = () => { setPhase(0); setPlaying(true); };

  return (
    <>
      <TopBar />
      <main className="space-y-5 p-4 animate-fade-in md:p-6 lg:p-8">
        <header className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <div className="mb-2 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-primary"><span className="h-px w-6 bg-primary/60" />Codex Multi-Agent Observatory</div>
            <h1 className="text-2xl font-bold tracking-[-0.03em] md:text-3xl">에이전트 운영 대시보드</h1>
            <p className="mt-1.5 max-w-2xl text-xs leading-5 text-muted-foreground">조건검색 후보가 병렬 분석과 독립 리스크 검증을 거쳐 advisory 신호가 되는 과정을 관찰합니다.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <SafetyPill />
            <Button variant="outline" size="sm" onClick={() => setPlaying((value) => !value)} disabled={finished}>
              {playing ? <CirclePause className="mr-1.5 h-4 w-4" /> : <Play className="mr-1.5 h-4 w-4" />}{playing ? "일시정지" : finished ? "완료됨" : "계속"}
            </Button>
            <Button size="sm" onClick={restart}><RefreshCw className="mr-1.5 h-4 w-4" />다시 재생</Button>
          </div>
        </header>

        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="오케스트레이션 요약">
          <Metric label="실행 모드" value="SIGNAL ONLY" hint="브로커 주문 차단" icon={ShieldCheck} color="text-primary" />
          <Metric label="활성 에이전트" value={String(active)} hint={phase === 1 ? "병렬 분석 중" : playing ? "단계 처리 중" : "대기 없음"} icon={Bot} color="text-accent" />
          <Metric label="완료된 작업" value={`${completed}/${AGENT_STAGES.length}`} hint="동일 스냅숏 기준" icon={Check} color="text-success" />
          <Metric label="스냅숏" value="12:41:08" hint="SAMPLE · 1.8초 전" icon={Clock3} color="text-warning" />
        </section>

        <section className="grid items-start gap-4 2xl:grid-cols-[minmax(0,1.55fr)_minmax(360px,0.75fr)]">
          <div className="card-base overflow-hidden p-0">
            <div className="flex flex-col gap-3 border-b border-border px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
              <div><div className="flex items-center gap-2"><GitBranch className="h-4 w-4 text-primary" /><h2 className="text-sm font-semibold">실시간 오케스트레이션 흐름</h2></div><p className="mt-1 text-[11px] text-muted-foreground">EVENT-20260830-0042 · NVDA · NASDAQ</p></div>
              <div className="flex gap-2 text-[10px]"><span className="rounded-full border border-border px-2 py-1 text-muted-foreground">strategy v2.4.1</span><span className="rounded-full border border-primary/30 bg-primary/10 px-2 py-1 text-primary">snapshot locked</span></div>
            </div>
            <div className="p-4 md:p-6">
              <FlowConnector active={phase === 0} label="조건식 진입 이벤트" />
              <AgentNode stage={AGENT_STAGES[0]} status={statuses.get(AGENT_STAGES[0].id)!} />
              <div className="mx-auto flex w-[88%] items-center py-3" aria-hidden="true"><div className="h-px flex-1 bg-border" /><div className="mx-3 flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-muted-foreground"><GitBranch className="h-3.5 w-3.5" />parallel fan-out</div><div className="h-px flex-1 bg-border" /></div>
              <div className="grid gap-3 md:grid-cols-2"><AgentNode stage={AGENT_STAGES[1]} status={statuses.get(AGENT_STAGES[1].id)!} /><AgentNode stage={AGENT_STAGES[2]} status={statuses.get(AGENT_STAGES[2].id)!} /></div>
              <FlowConnector active={phase === 2} label="증거 수렴 · 스키마 일치" />
              <AgentNode stage={AGENT_STAGES[3]} status={statuses.get(AGENT_STAGES[3].id)!} />
              <FlowConnector active={phase === 3} label="APPROVE_SIGNAL 전용" />
              <AgentNode stage={AGENT_STAGES[4]} status={statuses.get(AGENT_STAGES[4].id)!} />
            </div>
          </div>
          <div className="space-y-4"><SignalCard visible={finished} /><AuditLog phase={phase} /></div>
        </section>
      </main>
    </>
  );
}

function AgentNode({ stage, status }: { stage: (typeof AGENT_STAGES)[number]; status: AgentStatus }) {
  const Icon = stage.icon;
  return (
    <article className={cn("relative overflow-hidden rounded-2xl border p-4 transition-all", status === "working" ? toneClass(stage.tone) : "border-border bg-surface-3/35", status === "queued" && "opacity-55")}>
      {status === "working" && <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary to-transparent" />}
      <div className="flex items-start gap-3">
        <div className={cn("grid h-10 w-10 shrink-0 place-items-center rounded-xl border", iconTone(stage.tone, status))}><Icon className={cn("h-5 w-5", status === "working" && "animate-pulse")} /></div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-sm font-semibold">{stage.label}</h3><StatusBadge status={status} /></div>
          <div className="mt-0.5 font-mono text-[10px] text-primary/80">{stage.id}</div>
          <p className="mt-2 text-[11px] leading-5 text-muted-foreground">{stage.detail}</p>
          <div className="mt-3 flex justify-between border-t border-border/70 pt-2 text-[10px] text-muted-foreground"><span>{stage.role}</span><span>{stage.lane === "parallel" ? "PARALLEL" : "SERIAL"}</span></div>
        </div>
      </div>
    </article>
  );
}

function StatusBadge({ status }: { status: AgentStatus }) {
  const label = status === "done" ? "완료" : status === "working" ? "작업 중" : "대기";
  return <span className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold", status === "done" ? "border-success/30 bg-success/10 text-success" : status === "working" ? "border-primary/30 bg-primary/10 text-primary" : "border-border text-muted-foreground")}><span className={cn("h-1.5 w-1.5 rounded-full", status === "done" ? "bg-success" : status === "working" ? "animate-pulse bg-primary" : "bg-muted-foreground/50")} />{label}</span>;
}

function FlowConnector({ active, label }: { active: boolean; label: string }) {
  return <div className="flex h-12 items-center justify-center gap-3 text-[10px] text-muted-foreground" aria-hidden="true"><span className={cn("h-8 w-px", active ? "bg-primary shadow-[0_0_10px_hsl(var(--primary))]" : "bg-border")} /><span className={cn(active && "text-primary")}>{label}</span></div>;
}

function SignalCard({ visible }: { visible: boolean }) {
  return (
    <section className="card-base">
      <div className="flex items-center justify-between"><div className="flex items-center gap-2"><Sparkles className="h-4 w-4 text-primary" /><h2 className="text-sm font-semibold">최종 신호 미리보기</h2></div><span className="rounded-full border border-warning/30 bg-warning-soft px-2 py-1 text-[9px] font-bold text-warning">SIMULATION</span></div>
      <div className={cn("mt-4 transition-opacity", visible ? "opacity-100" : "opacity-35")}>
        <div className="flex items-end justify-between"><div><div className="text-[10px] text-muted-foreground">ADVISORY SIGNAL</div><div className="mt-1 text-2xl font-bold text-primary">{visible ? SAMPLE_SIGNAL.signal : "PENDING"}</div></div><div className="text-right"><div className="text-[10px] text-muted-foreground">CONFIDENCE</div><div className="mt-1 text-xl font-semibold num">{visible ? `${Math.round(SAMPLE_SIGNAL.confidence * 100)}%` : "--"}</div></div></div>
        <div className="mt-4 grid grid-cols-2 gap-2 text-[11px]"><SignalValue label="기준가" value={visible ? `$${SAMPLE_SIGNAL.referencePrice}` : "-"} /><SignalValue label="무효화" value={visible ? `$${SAMPLE_SIGNAL.invalidationPrice}` : "-"} /><SignalValue label="목적지" value={SAMPLE_SIGNAL.destination} /><SignalValue label="실행 권한" value="FALSE" danger /></div>
      </div>
      <p className="mt-3 rounded-xl border border-danger/20 bg-danger-soft/40 p-3 text-[10px] leading-4 text-danger">execution_authorized=false · 주문 제출, 정정, 취소 기능은 연결되어 있지 않습니다.</p>
    </section>
  );
}

function AuditLog({ phase }: { phase: number }) {
  const logs = [["12:41:08.104", "condition_intake", "후보 이벤트 검증 시작"], ["12:41:09.211", "orchestrator", "동일 스냅숏으로 병렬 분석 위임"], ["12:41:10.734", "risk_signal_gate", "필수 기준 12/12 확인"], ["12:41:11.829", "signal_publisher", "advisory 이벤트 생성"]];
  return <section className="card-base"><div className="flex items-center gap-2"><Activity className="h-4 w-4 text-accent" /><h2 className="text-sm font-semibold">감사 이벤트</h2></div><div className="mt-3 space-y-1.5">{logs.map(([time, agent, message], index) => <div key={time} className={cn("grid grid-cols-[68px_1fr] gap-2 rounded-xl border border-border/70 px-2.5 py-2 text-[10px]", index > phase && "opacity-30")}><span className="font-mono text-muted-foreground">{index <= phase ? time : "--:--:--"}</span><div><div className="truncate font-mono text-primary/80">{agent}</div><div className="mt-0.5 text-muted-foreground">{index <= phase ? message : "대기 중"}</div></div></div>)}</div></section>;
}

function Metric({ label, value, hint, icon: Icon, color }: { label: string; value: string; hint: string; icon: typeof Bot; color: string }) {
  return <section className="card-base flex items-center gap-3"><div className={cn("grid h-10 w-10 place-items-center rounded-xl border border-border bg-surface-3/60", color)}><Icon className="h-5 w-5" /></div><div><div className="text-[10px] text-muted-foreground">{label}</div><div className="mt-0.5 text-lg font-semibold num">{value}</div><div className="text-[10px] text-muted-foreground">{hint}</div></div></section>;
}

function SignalValue({ label, value, danger = false }: { label: string; value: string; danger?: boolean }) {
  return <div className="rounded-xl border border-border bg-surface-3/40 p-2.5"><div className="text-[9px] text-muted-foreground">{label}</div><div className={cn("mt-1 font-mono font-semibold", danger ? "text-danger" : "text-foreground")}>{value}</div></div>;
}

function SafetyPill() {
  return <div className="inline-flex items-center gap-2 rounded-full border border-success/25 bg-success/5 px-3 py-1.5 text-[10px] font-semibold text-success"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-success shadow-[0_0_8px_hsl(var(--success))]" />READ-ONLY · ORDER BLOCKED</div>;
}

function toneClass(tone: StageTone) {
  return { cyan: "border-accent/35 bg-accent/5", blue: "border-down/35 bg-down-soft/25", violet: "border-purple-400/35 bg-purple-500/5", amber: "border-warning/35 bg-warning-soft/25", green: "border-success/35 bg-success/5" }[tone];
}
function iconTone(tone: StageTone, status: AgentStatus) {
  if (status === "queued") return "border-border bg-muted text-muted-foreground";
  return { cyan: "border-accent/30 bg-accent/10 text-accent", blue: "border-down/30 bg-down-soft text-down", violet: "border-purple-400/30 bg-purple-500/10 text-purple-300", amber: "border-warning/30 bg-warning-soft text-warning", green: "border-success/30 bg-success/10 text-success" }[tone];
}

