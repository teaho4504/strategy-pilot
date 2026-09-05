import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BarChart3, ChevronDown, Radar, RefreshCw, ShieldAlert, Wifi } from "lucide-react";
import { TopBar } from "@/components/layout/TopBar";
import { Card } from "@/components/common/Card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/auth/AuthProvider";
import { readonlyApiClient, type UsAutoTradeStrategyStatusItem } from "@/services/apiClient";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { useConditionRealtime } from "@/hooks/use-condition-realtime";
import { useLiquidityRealtime } from "@/hooks/use-liquidity-realtime";
import type { UsLiquidityAnalysisResponse, UsLiquidityWall } from "@/types";

export default function Strategies() {
  const { session } = useAuth();
  const queryClient = useQueryClient();
  const sessionToken = session?.accessToken ?? "";
  const [expandedStrategy, setExpandedStrategy] = useState<string | null>(null);
  const [analysisSymbol, setAnalysisSymbol] = useState("NVDA");
  const [symbolDraft, setSymbolDraft] = useState("NVDA");

  const strategyStatus = useQuery({
    queryKey: ["strategies", "kiwoom-conditions", sessionToken],
    queryFn: readonlyApiClient.usAutoTradeStrategies,
    enabled: Boolean(sessionToken),
    refetchInterval: false,
    retry: false,
  });
  const runtimeStatus = useQuery({
    queryKey: ["strategies", "runtime-status", sessionToken],
    queryFn: readonlyApiClient.usAutoTradeStatus,
    enabled: Boolean(sessionToken),
    refetchInterval: 10_000,
    retry: false,
  });
  const liquidityRealtime = useLiquidityRealtime(
    sessionToken, analysisSymbol, "ND", Boolean(sessionToken && analysisSymbol),
  );

  const toggleStrategy = useMutation({
    mutationFn: ({ strategy, enabled }: { strategy: string; enabled: boolean }) =>
      readonlyApiClient.toggleUsAutoTradeStrategy(strategy, enabled),
    onSuccess: (next, variables) => {
      queryClient.setQueryData(["strategies", "kiwoom-conditions", sessionToken], next);
      toast.success(`키움 조건 감시를 ${variables.enabled ? "시작했습니다" : "해제했습니다"}.`);
    },
    onError: () => toast.error("키움 조건 감시 상태를 변경하지 못했습니다."),
  });
  const syncStrategies = useMutation({
    mutationFn: () => readonlyApiClient.usAutoTradeStrategies(true),
    onSuccess: (next) => {
      queryClient.setQueryData(["strategies", "kiwoom-conditions", sessionToken], next);
      toast.success("키움 HTS 조건식 목록을 다시 조회했습니다.");
    },
    onError: () => toast.error("키움 HTS 조건식 목록을 다시 조회하지 못했습니다."),
  });

  const baseRows = useMemo(
    () => strategyStatus.data?.strategies ?? [],
    [strategyStatus.data?.strategies],
  );
  const enabledSeqs = useMemo(
    () => baseRows
      .filter((item) => item.enabled && item.conditionSeq && !item.conditionError)
      .map((item) => item.conditionSeq as string),
    [baseRows],
  );
  const conditionRealtime = useConditionRealtime(
    sessionToken,
    enabledSeqs,
    Boolean(sessionToken && enabledSeqs.length),
  );
  const rows = useMemo(
    () => baseRows.map((status) => {
      const live = status.conditionSeq
        ? conditionRealtime.items.get(status.conditionSeq)
        : undefined;
      if (!live || !status.enabled) return status;
      return {
        ...status,
        conditionSeq: live.selectedSeq ?? status.conditionSeq,
        conditionName: live.selectedName ?? status.conditionName,
        conditionConnected: live.connected,
        conditionRegistered: live.registered,
        conditionMatchCount: live.matchCount,
        conditionMatches: live.matches,
        conditionError: live.error,
        conditionLastConnectedAt: live.lastConnectedAt,
        conditionLastReceivedAt: live.lastReceivedAt,
        conditionReconnectCount: live.reconnectCount,
        conditionNextRetrySeconds: live.nextRetrySeconds,
      };
    }),
    [baseRows, conditionRealtime.items],
  );
  const enabledCount = rows.filter((item) => item.enabled).length;
  const connectedCount = rows.filter((item) => item.enabled && item.conditionConnected).length;
  const runtimeBlockCount = runtimeStatus.data?.blockedReasons.length ?? null;

  return (
    <>
      <TopBar />
      <main className="mx-auto w-full max-w-5xl space-y-4 p-4 animate-fade-in">
        <header className="flex items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold">키움 조건검색식</h1>
            <p className="mt-1 text-xs text-muted-foreground">HTS 조건 감시 상태입니다. 감시 ON은 실주문 활성화와 별개입니다.</p>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="rounded-lg"
            disabled={strategyStatus.isFetching || syncStrategies.isPending}
            onClick={() => syncStrategies.mutate()}
          >
            <RefreshCw className={cn("mr-1.5 h-4 w-4", (strategyStatus.isFetching || syncStrategies.isPending) && "animate-spin")} />
            동기화
          </Button>
        </header>

        <Card className="grid overflow-hidden p-0 sm:grid-cols-2">
          <div className="flex items-center gap-3 border-b border-border px-4 py-3 sm:border-b-0 sm:border-r">
            <span className="rounded-lg bg-primary/10 p-2 text-primary">
              <Radar className="h-4 w-4" />
            </span>
            <div className="min-w-0">
              <p className="text-xs font-semibold">조건 감시</p>
              <p className="mt-0.5 truncate text-[11px] text-muted-foreground">
                {enabledCount}개 ON · {
                  enabledCount === 0
                    ? "WebSocket 감시 없음"
                    : conditionRealtime.state === "connected"
                      ? "키움 등록 " + connectedCount + "/" + enabledCount + " · 백엔드 연결"
                      : "WebSocket 재연결 중"
                }
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3 bg-danger-soft/10 px-4 py-3">
            <span className="rounded-lg bg-danger-soft/40 p-2 text-danger">
              <ShieldAlert className="h-4 w-4" />
            </span>
            <div className="min-w-0">
              <p className="text-xs font-semibold text-danger">실주문 차단</p>
              <p className="mt-0.5 truncate text-[11px] text-muted-foreground">
                {runtimeStatus.isLoading
                  ? "주문 안전장치 확인 중"
                  : runtimeBlockCount
                    ? `${runtimeBlockCount}개 안전장치 적용 중`
                    : "현재 버전은 주문을 전송하지 않습니다."}
              </p>
            </div>
          </div>
        </Card>

        <Card className="overflow-hidden p-0">
          <div className="flex items-center justify-between gap-3 border-b border-border bg-surface-3/50 px-4 py-4">
            <div>
              <h2 className="text-sm font-semibold">HTS 조건식 목록</h2>
              <p className="mt-1 text-xs text-muted-foreground">감시 ON 상태의 조건식만 실시간 편입·이탈을 수신합니다.</p>
            </div>
            <span className="shrink-0 text-xs font-semibold text-muted-foreground">
              {enabledCount}/{rows.length} 감시 ON
            </span>
          </div>

          <div className="space-y-3 p-3 sm:p-4">
            {strategyStatus.isLoading ? (
              <EmptyState>키움 조건식 목록을 불러오는 중입니다.</EmptyState>
            ) : strategyStatus.isError ? (
              <EmptyState danger>키움 세션 또는 조건식 목록 연결을 확인해 주세요.</EmptyState>
            ) : rows.length ? (
              rows.map((status) => {
                const expanded = expandedStrategy === status.strategy;
                return (
                  <ConditionStrategyRow
                    key={status.strategy}
                    status={status}
                    expanded={expanded}
                    toggling={toggleStrategy.isPending}
                    orderBlocked
                    updatedAt={conditionRealtime.updatedAt ?? strategyStatus.data?.updatedAt ?? null}
                    onToggle={(enabled) => toggleStrategy.mutate({ strategy: status.strategy, enabled })}
                    onExpand={() => setExpandedStrategy(expanded ? null : status.strategy)}
                  />
                );
              })
            ) : (
              <EmptyState>
                HTS에 저장된 키움 조건식이 없습니다. HTS에서 조건식을 저장한 뒤 동기화를 눌러 주세요.
              </EmptyState>
            )}
          </div>
        </Card>

        <LiquidityAnalysisPanel
          data={liquidityRealtime.data}
          loading={liquidityRealtime.state === "connecting" || liquidityRealtime.state === "reconnecting"}
          error={liquidityRealtime.state === "unavailable"}
          connectionState={liquidityRealtime.state}
          symbolDraft={symbolDraft}
          onSymbolDraftChange={setSymbolDraft}
          onAnalyze={() => {
            const clean = symbolDraft.toUpperCase().replace(/[^A-Z0-9.-]/g, "").slice(0, 12);
            if (clean) setAnalysisSymbol(clean);
          }}
        />

        <p className="px-1 text-[11px] leading-5 text-muted-foreground">
          조건식 작성과 수정은 키움 HTS에서 진행합니다. 대시보드의 감시 ON은 조건 편입·이탈 수신만 제어하며 실주문을 보내지 않습니다.
        </p>
      </main>
    </>
  );
}

function LiquidityAnalysisPanel({
  data,
  loading,
  error,
  connectionState,
  symbolDraft,
  onSymbolDraftChange,
  onAnalyze,
}: {
  data?: UsLiquidityAnalysisResponse;
  loading: boolean;
  error: boolean;
  connectionState: string;
  symbolDraft: string;
  onSymbolDraftChange: (value: string) => void;
  onAnalyze: () => void;
}) {
  const frames = data?.timeline.slice(-24) ?? [];
  return (
    <Card className="overflow-hidden p-0">
      <div className="flex flex-col gap-3 border-b border-border bg-surface-3/50 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <BarChart3 className="h-4 w-4 text-primary" />
            <h2 className="text-sm font-semibold">대형 호가 수급 · 다중 시간대 분석</h2>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">FE 체결과 FT 10단계 호가를 FastAPI 단일 스트림에서 분석합니다.</p>
        </div>
        <span className={cn(
          "w-fit rounded-full border px-2.5 py-1 text-[10px] font-semibold",
          connectionState === "connected" ? "border-success/30 bg-success/10 text-success" : "border-warning/30 bg-warning/10 text-warning",
        )}>
          {connectionState === "connected" ? "FastAPI WebSocket 연결" : "FastAPI WebSocket 연결 중"}
        </span>
        <form
          className="flex gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            onAnalyze();
          }}
        >
          <Input
            aria-label="분석 종목"
            value={symbolDraft}
            onChange={(event) => onSymbolDraftChange(event.target.value)}
            className="h-9 w-28 uppercase"
            maxLength={12}
          />
          <Button type="submit" size="sm" variant="outline" className="h-9">분석</Button>
        </form>
      </div>

      {error ? (
        <div className="m-4 rounded-lg border border-danger/30 bg-danger-soft/20 p-4 text-xs text-danger">
          분석 데이터를 불러오지 못했습니다. 키움 프로필과 백엔드 연결을 확인해 주세요.
        </div>
      ) : !data ? (
        <div className="p-8 text-center text-xs text-muted-foreground">{loading ? "호가 데이터를 분석 중입니다." : "분석할 종목을 입력해 주세요."}</div>
      ) : (
        <div className="space-y-4 p-4">
          <div className="grid gap-2 sm:grid-cols-3">
            {data.timeframes.map((item) => (
              <div key={item.timeframe} className="rounded-lg border border-foreground/15 bg-background/40 p-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold">{item.timeframe}</span>
                  <span className={cn(
                    "rounded-full px-2 py-0.5 text-[10px] font-semibold",
                    item.trend === "bullish" ? "bg-success/10 text-success" : item.trend === "bearish" ? "bg-danger-soft/30 text-danger" : "bg-muted text-muted-foreground",
                  )}>
                    {!item.dataSufficient ? "데이터 부족" : item.pullback ? "눌림 후보" : trendLabel(item.trend)}
                  </span>
                </div>
                <p className="mt-2 text-[11px] text-muted-foreground">
                  {item.latestClose == null ? "종가 없음" : `$${item.latestClose.toLocaleString()}`} · {item.candleCount}봉
                  {item.continuationComplete === false ? " · 추가 과거 데이터 있음" : ""}
                </p>
              </div>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground">
            <span className="rounded border border-foreground/15 px-2 py-1">
              차트: {data.chartContext.source === "kiwoom-usa06011" ? "키움 usa06011" : "FE 저장 데이터 대체"}
            </span>
            <span className="rounded border border-foreground/15 px-2 py-1">
              확보 시간대: {data.chartContext.availableTimeframes.length ? data.chartContext.availableTimeframes.join(" · ") : "없음"}
            </span>
            <span className={cn(
              "rounded border px-2 py-1 font-semibold",
              data.observationQuality.state === "ready"
                ? "border-success/30 bg-success/10 text-success"
                : data.observationQuality.state === "off_hours"
                  ? "border-foreground/15 bg-muted text-muted-foreground"
                  : "border-warning/30 bg-warning/10 text-warning",
            )}>
              키움 시세: {qualityLabel(data.observationQuality.state)}
            </span>
            {data.observationQuality.eventAgeSeconds != null ? (
              <span className="rounded border border-foreground/15 px-2 py-1">
                최근 이벤트 {Math.round(data.observationQuality.eventAgeSeconds).toLocaleString()}초 전
              </span>
            ) : null}
            {data.observationQuality.marketSession !== "closed" && data.observationQuality.staleTimeframes.length ? (
              <span className="rounded border border-warning/30 bg-warning/10 px-2 py-1 text-warning">
                지연 분봉: {data.observationQuality.staleTimeframes.join(" · ")}
              </span>
            ) : null}
            {data.fxStaleDays != null && data.fxStaleDays > 3 ? (
              <span className="rounded border border-warning/30 bg-warning/10 px-2 py-1 text-warning">환율 {data.fxStaleDays}일 경과</span>
            ) : null}
          </div>

          <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
            <div className="rounded-xl border border-foreground/15 bg-surface-3/40 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="text-xs font-semibold">{data.symbol} 호가벽 테트리스</p>
                  <p className="mt-0.5 text-[10px] text-muted-foreground">
                    기준 {formatKrw(data.thresholdKrw)} · USD/KRW {data.fxKrwPerUsd.toLocaleString()}
                    {data.fxAsOf ? ` (${data.fxAsOf} FRED)` : " (참고값)"}
                  </p>
                </div>
                <div className="flex gap-3 text-[10px] font-semibold">
                  <span className="text-danger">■ 매도벽</span>
                  <span className="text-success">■ 매수벽</span>
                  <span className="text-muted-foreground">□ 소멸</span>
                </div>
              </div>
              <div className="mt-3 overflow-x-auto rounded-lg border border-foreground/10 bg-background/50 p-2">
                {frames.length ? (
                  <div className="flex min-w-max items-stretch gap-1">
                    {frames.map((frame, index) => (
                      <div key={`${frame.timestamp}-${index}`} className="grid h-36 w-7 grid-rows-2 gap-1 border-r border-foreground/5 px-0.5" title={new Date(frame.timestamp).toLocaleString("ko-KR")}>
                        <WallStack walls={frame.walls.filter((wall) => wall.side === "ask")} threshold={data.thresholdKrw} reverse />
                        <WallStack walls={frame.walls.filter((wall) => wall.side === "bid")} threshold={data.thresholdKrw} />
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="flex h-36 items-center justify-center text-xs text-muted-foreground">저장된 FT 호가 스냅샷이 없습니다.</div>
                )}
              </div>
            </div>

            <div className="min-w-[210px] rounded-xl border border-foreground/15 bg-background/40 p-3 text-xs">
              <div className="flex items-center justify-between gap-4">
                <span className="text-muted-foreground">관찰 신호</span>
                <span className={cn("font-bold", data.signal.action === "BUY_WATCH" ? "text-success" : data.signal.action === "SELL_WATCH" ? "text-danger" : "text-warning")}>{signalLabel(data.signal.action)}</span>
              </div>
              <div className="mt-2 flex items-center justify-between gap-4">
                <span className="text-muted-foreground">호가 불균형</span>
                <span className="font-semibold">{data.latest.imbalancePct == null ? "-" : `${data.latest.imbalancePct.toFixed(1)}%`}</span>
              </div>
              <div className="mt-2 flex items-center justify-between gap-4">
                <span className="text-muted-foreground">매수벽</span>
                <span className="font-semibold text-success">{formatKrw(data.latest.bidWallKrw)}</span>
              </div>
              <div className="mt-2 flex items-center justify-between gap-4">
                <span className="text-muted-foreground">매도벽</span>
                <span className="font-semibold text-danger">{formatKrw(data.latest.askWallKrw)}</span>
              </div>
              <div className={cn(
                "mt-3 rounded-lg border px-2.5 py-2 text-[10px] font-semibold",
                data.observationQuality.signalEligible
                  ? "border-success/30 bg-success/10 text-success"
                  : "border-warning/30 bg-warning/10 text-warning",
              )}>
                {data.observationQuality.signalEligible
                  ? "데이터 품질 통과 · 관찰 신호 평가 가능"
                  : `신호 억제 · ${qualityLabel(data.observationQuality.state)}`}
              </div>
              <div className="mt-3 rounded-lg border border-danger/30 bg-danger-soft/20 px-2.5 py-2 text-[10px] font-semibold text-danger">
                실주문 차단 · execution_authorized=false
              </div>
            </div>
          </div>

          <p className="text-[10px] leading-4 text-muted-foreground">
            호가 소멸은 FE 체결과 대조해 체결·취소 가능성을 분류하며 동일 투자자의 이탈로 확정하지 않습니다. {loading ? "최신 데이터 동기화 중…" : `최근 ${data.orderbookSnapshotCount}개 호가 스냅샷 분석`}
          </p>
          <div className="rounded-lg border border-foreground/10 bg-background/30 px-3 py-2">
            <div className="flex items-center justify-between text-[11px]">
              <span className="font-semibold">관찰 신호 이력</span>
              <span className="text-muted-foreground">실주문 권한 없음</span>
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {data.signalHistory.slice(0, 6).map((item) => (
                <span key={`${item.createdAt}-${item.action}`} className="rounded border border-foreground/15 px-2 py-1 text-[10px] text-muted-foreground">
                  {signalLabel(item.action)} · {formatSyncTime(item.createdAt)}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}

function WallStack({ walls, threshold, reverse = false }: { walls: UsLiquidityWall[]; threshold: number; reverse?: boolean }) {
  const visible = walls.slice(0, 5);
  return (
    <div className={cn("flex min-h-0 flex-col items-stretch justify-end gap-0.5", reverse && "flex-col-reverse justify-start")}>
      {visible.map((wall, index) => {
        const vanished = wall.state === "disappeared";
        const height = vanished ? 4 : Math.min(20, Math.max(5, (wall.notionalKrw / threshold) * 5));
        return (
          <span
            key={`${wall.side}-${wall.price}-${index}`}
            title={`${wall.side === "bid" ? "매수" : "매도"} $${wall.price} · ${formatKrw(wall.notionalKrw)} · ${wall.state}${wall.exitInference ? ` · ${exitLabel(wall.exitInference)}` : ""}`}
            className={cn(
              "block rounded-[2px] border",
              vanished ? "border-dashed border-muted-foreground/50 bg-transparent" : wall.side === "bid" ? "border-success/40 bg-success/70" : "border-danger/40 bg-danger/70",
            )}
            style={{ height }}
          />
        );
      })}
    </div>
  );
}

function formatKrw(value: number): string {
  if (value >= 100_000_000) return `${(value / 100_000_000).toFixed(1)}억원`;
  if (value >= 10_000) return `${Math.round(value / 10_000).toLocaleString()}만원`;
  return `${Math.round(value).toLocaleString()}원`;
}

function trendLabel(value: string): string {
  if (value === "bullish") return "상승";
  if (value === "bearish") return "하락";
  if (value === "flat") return "중립";
  return "미확인";
}

function signalLabel(value: string): string {
  if (value === "BUY_WATCH") return "매수 관찰";
  if (value === "SELL_WATCH") return "매도 관찰";
  return "대기";
}

function qualityLabel(value: UsLiquidityAnalysisResponse["observationQuality"]["state"]): string {
  if (value === "ready") return "정상";
  if (value === "off_hours") return "장외 관찰";
  if (value === "reconnecting") return "재연결 대기";
  if (value === "stale") return "데이터 지연";
  if (value === "missing") return "수신 없음";
  return "일부 데이터 누락";
}

function exitLabel(value: string): string {
  if (value === "likely-execution") return "체결 추정";
  if (value === "possible-execution") return "체결 가능";
  if (value === "likely-cancel") return "취소 추정";
  return "판단 불가";
}

export function ConditionStrategyRow({
  status,
  expanded,
  toggling,
  orderBlocked = true,
  updatedAt = null,
  onToggle,
  onExpand,
}: {
  status: UsAutoTradeStrategyStatusItem;
  expanded: boolean;
  toggling: boolean;
  orderBlocked?: boolean;
  updatedAt?: string | null;
  onToggle: (enabled: boolean) => void;
  onExpand: () => void;
}) {
  const connectionLabel = !status.enabled
    ? "감시 OFF"
    : status.conditionConnected
      ? `${status.conditionMatchCount}종목 편입`
      : status.conditionError
        ? "연결 오류"
        : "연결 대기";

  return (
    <article className={cn(
      "rounded-xl border p-3 transition-colors sm:p-4",
      status.enabled ? "border-primary/35 bg-primary/[0.04]" : "border-foreground/20 bg-surface-3/30",
    )}>
      <div className="flex items-center gap-2 sm:gap-3">
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-sm font-semibold sm:text-base">
            {status.conditionName || status.strategyName}
          </h2>
          <p className="mt-1 text-[11px] text-muted-foreground">조건 번호 {status.conditionSeq ?? "-"}</p>
        </div>
        <button
          type="button"
          role="switch"
          aria-label={`${status.conditionName || status.strategyName} 감시`}
          aria-checked={status.enabled}
          disabled={toggling}
          onClick={() => onToggle(!status.enabled)}
          className={cn(
            "min-w-[76px] rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors",
            status.enabled
              ? "border-success/40 bg-success/10 text-success"
              : "border-border bg-background text-muted-foreground",
          )}
        >
          {status.enabled ? "감시 ON" : "감시 OFF"}
        </button>
        <button
          type="button"
          aria-label={`${status.conditionName || status.strategyName} 상세`}
          aria-expanded={expanded}
          onClick={onExpand}
          className="inline-flex items-center gap-1 rounded-full border border-foreground/25 bg-background px-3 py-1.5 text-xs font-semibold"
        >
          더보기
          <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", expanded && "rotate-180")} />
        </button>
      </div>

      <div className="mt-3 grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
        <div className="flex items-center justify-between gap-3 rounded-lg border border-foreground/30 bg-surface-3/70 px-3 py-3 text-xs shadow-[inset_0_0_0_1px_hsl(var(--foreground)/0.07)] sm:text-sm">
          <span className="truncate font-medium">키움 실시간 조건식 등록</span>
          <span className={cn(
            "shrink-0 font-semibold",
            status.conditionConnected ? "text-success" : status.conditionError ? "text-danger" : "text-muted-foreground",
          )}>
            {connectionLabel}
          </span>
        </div>
        <div className="flex items-center justify-between gap-3 rounded-lg border border-danger/35 bg-danger-soft/15 px-3 py-3 text-xs text-danger sm:min-w-[132px]">
          <span className="inline-flex items-center gap-1 font-medium">
            <ShieldAlert className="h-3.5 w-3.5" />
            주문
          </span>
          <span className="font-semibold">{orderBlocked ? "실주문 차단" : "정책 확인"}</span>
        </div>
      </div>

      {expanded ? (
        <div className="mt-3 space-y-2 border-t border-border pt-3">
          {status.conditionError ? (
            <div className="rounded-lg border border-danger/30 bg-danger-soft/20 px-3 py-2 text-xs text-danger">
              {status.conditionError}
            </div>
          ) : null}
          <div className="flex items-center justify-between gap-3 px-1">
            <span className="text-xs font-semibold">현재 편입 종목</span>
            <span className="text-[11px] text-muted-foreground">
              {status.conditionMatches.length}종목
            </span>
          </div>
          <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-2 rounded-lg border border-foreground/15 bg-background/30 px-3 py-2.5 text-[11px]">
            <span className="inline-flex items-center gap-1 text-muted-foreground">
              <Wifi className="h-3.5 w-3.5" /> 백엔드 WebSocket
            </span>
            <span className="text-right font-semibold">
              연결됨
            </span>
            <span className="text-muted-foreground">키움 조건식 등록</span>
            <span className="text-right font-semibold">
              {status.conditionRegistered ? "등록됨" : status.conditionError ? "오류" : "등록 대기"}
            </span>
            <span className="text-muted-foreground">키움 연결 시각</span>
            <span className="text-right font-semibold">{formatSyncTime(status.conditionLastConnectedAt)}</span>
            <span className="text-muted-foreground">최근 조건 데이터</span>
            <span className="text-right font-semibold">{formatSyncTime(status.conditionLastReceivedAt)}</span>
            <span className="text-muted-foreground">재연결 횟수</span>
            <span className="text-right font-semibold">
              {status.conditionReconnectCount}회{status.conditionNextRetrySeconds != null ? ` · ${status.conditionNextRetrySeconds}초 후` : ""}
            </span>
            <span className="text-muted-foreground">마지막 동기화</span>
            <span className="text-right font-semibold">{formatSyncTime(updatedAt)}</span>
          </div>
          {!status.enabled ? (
            <ConditionNotice>조건식을 ON하면 현재 편입 종목을 확인할 수 있습니다.</ConditionNotice>
          ) : status.conditionConnected && status.conditionMatches.length ? (
            <div className="grid gap-2 sm:grid-cols-2">
              {status.conditionMatches.map((match) => (
                <div
                  key={`${match.exchange ?? "US"}-${match.code}`}
                  className="flex items-center justify-between gap-3 rounded-lg border border-foreground/20 bg-surface-3/70 px-3 py-2.5 text-xs"
                >
                  <span className="min-w-0 truncate font-semibold">{match.name || match.code}</span>
                  <span className="shrink-0 text-muted-foreground">
                    {match.code}{match.exchange ? ` · ${match.exchange}` : ""}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <ConditionNotice>
              {status.conditionConnected ? "현재 편입된 종목이 없습니다." : "키움 실시간 조건검색 연결을 기다리는 중입니다."}
            </ConditionNotice>
          )}
        </div>
      ) : null}
    </article>
  );
}

function formatSyncTime(value: string | null): string {
  if (!value) return "기록 없음";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "기록 없음";
  return new Intl.DateTimeFormat("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(parsed);
}

function ConditionNotice({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-foreground/15 bg-background/40 px-3 py-4 text-center text-xs text-muted-foreground">
      {children}
    </div>
  );
}

function EmptyState({ children, danger = false }: { children: React.ReactNode; danger?: boolean }) {
  return (
    <div className={cn(
      "rounded-xl border px-4 py-10 text-center text-xs leading-5",
      danger ? "border-danger/30 bg-danger-soft/30 text-danger" : "border-border text-muted-foreground",
    )}>
      {children}
    </div>
  );
}
