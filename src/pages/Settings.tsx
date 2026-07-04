import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { TopBar } from "@/components/layout/TopBar";
import { Card, SectionTitle } from "@/components/common/Card";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { portfolioAdapter, queryKeys, riskAdapter } from "@/services/adapters";
import { getErrorMessage } from "@/services/apiClient";
import { won } from "@/lib/format";
import { Link2, ShieldCheck, ServerCog, Lock, Info } from "lucide-react";
import { toast } from "sonner";
import type { RiskSettings } from "@/types";

const emptyRisk: RiskSettings = {
  dailyLossLimit: 0,
  perStrategyMaxInvest: 0,
  perTickerMaxWeightPct: 0,
  maxConcurrentTickers: 0,
  maxOrdersPerDay: 0,
  notify: { strategyError: false, orderFailure: false, dailyLossHit: false, bigPnl: false },
};

export default function Settings() {
  const queryClient = useQueryClient();
  const { data: risk } = useQuery({ queryKey: queryKeys.risk, queryFn: riskAdapter.get });
  const { data: health, isError: healthError, error: healthQueryError } = useQuery({
    queryKey: queryKeys.health,
    queryFn: portfolioAdapter.getHealth,
    refetchInterval: 15_000,
    retry: 1,
  });
  const [r, setR] = useState<RiskSettings>(emptyRisk);
  const saveMutation = useMutation({
    mutationFn: riskAdapter.update,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.risk }),
  });

  useEffect(() => {
    if (risk) setR(risk);
  }, [risk]);

  const save = () => {
    saveMutation.mutate(r);
    toast.success("설정 저장됨 (데모)");
  };

  return (
    <>
      <TopBar />
      <main className="space-y-3 p-4 animate-fade-in">
        <h1 className="text-xl font-semibold">리스크 · 설정</h1>

        <Card className="space-y-4">
          <SectionTitle title="리스크 한도" sub="자동매매가 절대 넘지 않는 안전 한도" />
          <Field label="일일 손실 한도" suffix="원" value={r.dailyLossLimit}
            onChange={(v) => setR({ ...r, dailyLossLimit: v })} hint="이 금액 도달 시 모든 전략 자동 정지" />
          <Field label="전략별 최대 투자금" suffix="원" value={r.perStrategyMaxInvest}
            onChange={(v) => setR({ ...r, perStrategyMaxInvest: v })} />
          <Field label="종목당 최대 비중" suffix="%" value={r.perTickerMaxWeightPct}
            onChange={(v) => setR({ ...r, perTickerMaxWeightPct: v })} />
          <Field label="동시 보유 종목 수" suffix="개" value={r.maxConcurrentTickers}
            onChange={(v) => setR({ ...r, maxConcurrentTickers: v })} />
          <Field label="일일 주문 횟수 제한" suffix="건" value={r.maxOrdersPerDay}
            onChange={(v) => setR({ ...r, maxOrdersPerDay: v })} />
          <div className="rounded-xl border border-success/30 bg-success/10 p-3 text-[12px] text-success flex gap-2">
            <ShieldCheck className="h-4 w-4 shrink-0" />
            현재 한도 요약 · 일일 손실 {won(r.dailyLossLimit)} · 종목당 {r.perTickerMaxWeightPct}% 이하
          </div>
        </Card>

        <Card className="space-y-3">
          <SectionTitle title="알림" />
          <Toggle label="전략 오류" checked={r.notify.strategyError}
            onChange={(v) => setR({ ...r, notify: { ...r.notify, strategyError: v } })} />
          <Toggle label="주문 실패" checked={r.notify.orderFailure}
            onChange={(v) => setR({ ...r, notify: { ...r.notify, orderFailure: v } })} />
          <Toggle label="일일 손실 한도 도달" checked={r.notify.dailyLossHit}
            onChange={(v) => setR({ ...r, notify: { ...r.notify, dailyLossHit: v } })} />
          <Toggle label="큰 수익/손실 발생" checked={r.notify.bigPnl}
            onChange={(v) => setR({ ...r, notify: { ...r.notify, bigPnl: v } })} />
        </Card>

        <Card className="space-y-3">
          <SectionTitle title="증권사 연동" sub="안전한 서버 측 연동만 지원합니다" />
          <div className="rounded-xl border border-border bg-surface-3/40 p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="grid h-9 w-9 place-items-center rounded-lg bg-primary/15 text-primary">
                  <Link2 className="h-4 w-4" />
                </span>
                <div>
                  <div className="text-sm font-semibold">키움증권</div>
                  <div className="text-[11px] text-muted-foreground">
                    {health?.mode === "live" ? "REST API · 계좌 조회 모드" : "REST API · mock 모드"}
                  </div>
                </div>
              </div>
              <span className={health?.kiwoom.configured ? "chip border-success/40 bg-success/10 text-success" : "chip border-warning/40 bg-warning-soft text-warning"}>
                {health?.kiwoom.configured ? "설정 확인" : "설정 필요"}
              </span>
            </div>
            <div className="mt-3 rounded-lg border border-border bg-muted/30 p-3 text-[11px] text-muted-foreground">
              App Key {health?.kiwoom.appKey ?? "미설정"} · 계좌 {health?.kiwoom.accountNo ?? "미설정"}
            </div>
          </div>
          <div className="flex items-start gap-2 rounded-xl border border-border bg-muted/40 p-3 text-[12px] text-muted-foreground">
            <Lock className="mt-0.5 h-4 w-4 shrink-0" />
            API 키와 시크릿은 프론트엔드에 저장되지 않습니다. 실제 주문 실행은 서버 측 자동매매 엔진에서만 처리됩니다.
          </div>
        </Card>

        <Card className="space-y-3">
          <SectionTitle title="서버 상태" sub={healthError ? `API 오류 · ${getErrorMessage(healthQueryError)}` : undefined} />
          <Row icon={<ServerCog className="h-4 w-4" />} label="백엔드" value={health?.status ?? "연결 대기"} tone={health?.status === "ok" ? "ok" : undefined} />
          <Row icon={<ServerCog className="h-4 w-4" />} label="키움 모드" value={health?.mode ?? "unknown"} tone={health?.mode === "mock" || health?.mode === "live" ? "ok" : undefined} />
          <Row icon={<ServerCog className="h-4 w-4" />} label="마지막 정상 조회" value={health?.lastSuccessAt ? new Date(health.lastSuccessAt).toLocaleTimeString("ko-KR") : "없음"} />
          <Row icon={<Info className="h-4 w-4" />} label="앱 버전" value="prototype" />
        </Card>

        <Button className="w-full" onClick={save} disabled={saveMutation.isPending}>
          설정 저장
        </Button>

        <p className="pt-1 text-center text-[11px] text-muted-foreground">
          본 화면은 데모 프로토타입입니다. 실주문 · 실로그인은 포함되지 않습니다.
        </p>
      </main>
    </>
  );
}

function Field({ label, value, onChange, suffix, hint }: {
  label: string; value: number; onChange: (v: number) => void; suffix?: string; hint?: string;
}) {
  return (
    <div className="space-y-1.5">
      <Label className="text-[12.5px] text-muted-foreground">{label}</Label>
      <div className="relative">
        <Input
          inputMode="numeric"
          value={value.toLocaleString("ko-KR")}
          onChange={(e) => onChange(Number(e.target.value.replace(/[^\d]/g, "")) || 0)}
          className="h-11 pr-12 text-right num text-base"
        />
        {suffix && <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">{suffix}</span>}
      </div>
      {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  );
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="flex items-center justify-between rounded-xl border border-border bg-surface-3/40 px-3 py-2.5">
      <span className="text-sm">{label}</span>
      <Switch checked={checked} onCheckedChange={onChange} />
    </div>
  );
}

function Row({ icon, label, value, tone }: { icon: React.ReactNode; label: string; value: string; tone?: "ok" }) {
  return (
    <div className="flex items-center justify-between rounded-xl border border-border bg-surface-3/40 px-3 py-2.5">
      <div className="flex items-center gap-2 text-sm">
        <span className="text-muted-foreground">{icon}</span>
        {label}
      </div>
      <span className={tone === "ok" ? "text-[12px] font-medium text-success" : "text-[12px] text-muted-foreground"}>
        {value}
      </span>
    </div>
  );
}
