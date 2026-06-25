import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronLeft, Info, Save } from "lucide-react";
import { Card } from "@/components/common/Card";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Slider } from "@/components/ui/slider";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

type Step = { key: string; title: string; sub: string };
const STEPS: Step[] = [
  { key: "universe", title: "대상 선택",   sub: "어떤 종목군을 거래할까요?" },
  { key: "entry",    title: "진입 조건",   sub: "언제 매수 신호가 발생하나요?" },
  { key: "filter",   title: "필터",       sub: "시장 상황에 따라 거래 제한" },
  { key: "order",    title: "주문 규칙",   sub: "어떻게 주문할까요?" },
  { key: "exit",     title: "청산 조건",   sub: "익절 · 손절 · 시간 종료" },
  { key: "risk",     title: "리스크 한도", sub: "전략별 한도 설정" },
  { key: "review",   title: "검토 · 저장", sub: "시뮬레이션 (향후 연동)" },
];

interface Block {
  id: string;
  step: string;
  label: string;
  desc: string;
  value: string;
  paramKey: "tradeValue" | "changePct" | "rsi" | "ma" | "prevHigh" | "askBidRatio" | "indexFilter" | "takeProfit" | "stopLoss" | "qty" | "maxLoss";
}

const INITIAL: Block[] = [
  { id: "u1", step: "universe", label: "코스피 200", desc: "구성 종목 한정", value: "200종목", paramKey: "tradeValue" },
  { id: "e1", step: "entry", label: "거래대금 급증", desc: "5분 평균 대비", value: "+200% 이상", paramKey: "tradeValue" },
  { id: "e2", step: "entry", label: "전일 고가 돌파", desc: "당일 1회 발생", value: "ON", paramKey: "prevHigh" },
  { id: "f1", step: "filter", label: "코스피 지수", desc: "시장 약세 회피", value: "-0.5% 이상", paramKey: "indexFilter" },
  { id: "f2", step: "filter", label: "RSI", desc: "과열 회피", value: "≤ 75", paramKey: "rsi" },
  { id: "o1", step: "order", label: "1회 주문 수량", desc: "균등 분할", value: "5주", paramKey: "qty" },
  { id: "x1", step: "exit", label: "익절", desc: "고정 비율", value: "+1.2%", paramKey: "takeProfit" },
  { id: "x2", step: "exit", label: "손절", desc: "추적 손절", value: "-0.8%", paramKey: "stopLoss" },
  { id: "r1", step: "risk", label: "일일 최대 손실", desc: "이 전략 한정", value: "500,000원", paramKey: "maxLoss" },
];

export default function StrategyBuilder() {
  const nav = useNavigate();
  const [stepIdx, setStepIdx] = useState(0);
  const [blocks, setBlocks] = useState(INITIAL);
  const [editing, setEditing] = useState<Block | null>(null);
  const [name, setName] = useState("나의 거래대금 돌파 전략");

  const step = STEPS[stepIdx];
  const stepBlocks = blocks.filter((b) => b.step === step.key);

  const updateBlock = (id: string, value: string) =>
    setBlocks((prev) => prev.map((b) => (b.id === id ? { ...b, value } : b)));

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-30 border-b border-border bg-surface-1/90 backdrop-blur"
        style={{ paddingTop: "env(safe-area-inset-top)" }}>
        <div className="mx-auto flex max-w-xl items-center justify-between gap-2 px-3 py-3">
          <button onClick={() => nav(-1)} className="grid h-9 w-9 place-items-center rounded-lg hover:bg-muted">
            <ChevronLeft className="h-5 w-5" />
          </button>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="h-9 flex-1 border-transparent bg-transparent text-center font-semibold focus-visible:border-border"
          />
          <Button size="sm" onClick={() => { toast.success("전략 저장됨 (데모)"); nav("/strategies"); }}>
            <Save className="mr-1 h-4 w-4" /> 저장
          </Button>
        </div>

        {/* Stepper */}
        <div className="no-scrollbar overflow-x-auto px-3 pb-3">
          <div className="flex gap-1.5">
            {STEPS.map((s, i) => (
              <button
                key={s.key}
                onClick={() => setStepIdx(i)}
                className={cn(
                  "shrink-0 rounded-full border px-3 py-1 text-[11px] font-medium",
                  i === stepIdx
                    ? "border-primary/40 bg-primary/15 text-primary"
                    : i < stepIdx
                      ? "border-border bg-surface-2 text-foreground"
                      : "border-border bg-surface-2 text-muted-foreground"
                )}
              >
                {i + 1}. {s.title}
              </button>
            ))}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-xl space-y-4 p-4 pb-40 animate-fade-in">
        <div>
          <h2 className="text-lg font-semibold">{step.title}</h2>
          <p className="text-sm text-muted-foreground">{step.sub}</p>
        </div>

        <div className="space-y-2">
          {stepBlocks.map((b) => (
            <button
              key={b.id}
              onClick={() => setEditing(b)}
              className="flex w-full items-center justify-between gap-3 rounded-2xl border border-border bg-card p-4 text-left transition-colors hover:border-border-strong"
            >
              <div>
                <div className="text-sm font-semibold">{b.label}</div>
                <div className="text-[12px] text-muted-foreground">{b.desc}</div>
              </div>
              <div className="text-right">
                <div className="text-sm font-semibold num text-primary">{b.value}</div>
                <div className="text-[11px] text-muted-foreground">탭하여 수정</div>
              </div>
            </button>
          ))}
          {stepBlocks.length === 0 && (
            <Card className="text-center text-sm text-muted-foreground">
              이 단계에는 아직 블록이 없습니다. 다른 단계 블록은 ‘전략 요약’에서 확인할 수 있어요.
            </Card>
          )}
          <Button variant="outline" className="w-full border-dashed">+ 조건 블록 추가 (데모)</Button>
        </div>

        {/* Summary */}
        <Card className="space-y-3">
          <div className="flex items-center gap-2">
            <Info className="h-4 w-4 text-accent" />
            <h3 className="text-sm font-semibold">전략 요약</h3>
          </div>
          <ul className="space-y-1.5 text-[12.5px]">
            {blocks.map((b) => (
              <li key={b.id} className="flex justify-between gap-3 text-muted-foreground">
                <span>{STEPS.find((s) => s.key === b.step)?.title} · {b.label}</span>
                <span className="num text-foreground">{b.value}</span>
              </li>
            ))}
          </ul>
          <div className="rounded-xl border border-warning/30 bg-warning-soft/60 p-3 text-[12px] text-warning">
            예상 리스크: 1회 주문 5주 × 평균가 ≈ 50만~100만원 노출. 일일 손실 한도 50만원에서 자동 정지.
          </div>
          <div className="rounded-xl border border-dashed border-border bg-surface-3/40 p-3 text-center text-[12px] text-muted-foreground">
            백테스트 · 실시간 시뮬레이션은 <span className="font-medium text-foreground">향후 연동 예정</span>입니다.
          </div>
        </Card>

        <div className="flex gap-2">
          <Button variant="outline" disabled={stepIdx === 0} onClick={() => setStepIdx((i) => i - 1)} className="flex-1">
            이전
          </Button>
          {stepIdx < STEPS.length - 1 ? (
            <Button onClick={() => setStepIdx((i) => i + 1)} className="flex-1">다음</Button>
          ) : (
            <Button onClick={() => { toast.success("전략 저장됨 (데모)"); nav("/strategies"); }} className="flex-1">
              <Save className="mr-1 h-4 w-4" /> 저장
            </Button>
          )}
        </div>
      </main>

      {/* Block editor bottom sheet */}
      <Sheet open={!!editing} onOpenChange={(o) => !o && setEditing(null)}>
        <SheetContent side="bottom" className="rounded-t-2xl border-border bg-surface-2 max-h-[80vh]">
          {editing && (
            <>
              <SheetHeader className="text-left">
                <SheetTitle>{editing.label}</SheetTitle>
                <SheetDescription>{editing.desc}</SheetDescription>
              </SheetHeader>
              <div className="mt-4 space-y-5">
                <div className="space-y-2">
                  <Label>현재 값</Label>
                  <Input
                    value={editing.value}
                    onChange={(e) => setEditing({ ...editing, value: e.target.value })}
                    className="text-base num"
                  />
                </div>
                <div className="space-y-2">
                  <Label>파라미터 (예시)</Label>
                  <Slider defaultValue={[60]} max={100} step={1} />
                  <p className="text-[11px] text-muted-foreground">실제 백테스트 연결 시 슬라이더가 정확한 단위로 매핑됩니다.</p>
                </div>
                <Button
                  className="w-full"
                  onClick={() => { updateBlock(editing.id, editing.value); toast.success("블록 업데이트 (데모)"); setEditing(null); }}
                >
                  적용
                </Button>
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
