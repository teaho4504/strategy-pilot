import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, BarChart3, Clock3, Radio, RefreshCw, ShieldAlert, TrendingUp, WifiOff } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { TopBar } from "@/components/layout/TopBar";
import { readonlyApiClient, type UsQuoteResponse } from "@/services/apiClient";
import type { MarketRankItem, MarketRankingResponse, UsRealtimeWindowItem, UsRealtimeWindowResponse } from "@/types";
import { cn } from "@/lib/utils";
import { useDeferredPageReady } from "@/hooks/use-deferred-page-ready";
import { extractHoldingWatchItems, type HoldingWatchItem } from "@/lib/exit-alerts";
import { formatDataAge, getRealtimeFreshness } from "@/lib/realtime-freshness";
import { useAuth } from "@/auth/AuthProvider";
import { useRankingRealtime } from "@/hooks/use-ranking-realtime";
import { useQuoteRealtime, type QuoteRealtimeItem, type RealtimeConnectionState } from "@/hooks/use-quote-realtime";
import { mergeRankingRealtime } from "@/lib/ranking-realtime";

type RankingTab = "change-rate" | "volume";
type ViewTab = RankingTab | "holdings";

const TABS: { value: ViewTab; label: string; description: string }[] = [
  { value: "change-rate", label: "당일 급등률", description: "전일 종가 대비 상승률이 높은 미국주식" },
  { value: "volume", label: "거래량 갱신", description: "거래량 상위 미국주식" },
  { value: "holdings", label: "보유 감시", description: "실계좌 보유종목의 ±2% 매도 검토 상태" },
];

export default function Quotes() {
  const { session } = useAuth();
  const [searchParams] = useSearchParams();
  const selectedSymbol = safeSymbol(searchParams.get("symbol"));
  const selectedExchange = safeExchange(searchParams.get("exchange"));
  const [activeTab, setActiveTab] = useState<ViewTab>(() => selectedSymbol ? "holdings" : "change-rate");
  const pageReady = useDeferredPageReady(250);

  const ranking = useQuery({
    queryKey: ["quotes-lite", activeTab],
    queryFn: () => readonlyApiClient.usRanking(activeTab === "holdings" ? "change-rate" : activeTab),
    enabled: pageReady && activeTab !== "holdings",
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
    retry: false,
  });
  const holdings = useQuery({
    queryKey: ["portfolio-card", "us-holdings"],
    queryFn: readonlyApiClient.usHoldings,
    enabled: pageReady,
    refetchInterval: 5_000,
    retry: false,
  });
  const selectedRealtime = useQuery({
    queryKey: ["quotes", "selected-realtime", selectedSymbol],
    queryFn: () => readonlyApiClient.usRealtimeWindow(
      selectedSymbol ? [selectedSymbol] : [],
      selectedSymbol ? { [selectedSymbol]: selectedExchange } : {},
    ),
    enabled: pageReady && Boolean(selectedSymbol),
    refetchInterval: false,
    retry: false,
  });
  const selectedRestQuote = useQuery({
    queryKey: ["quotes", "selected-rest", selectedSymbol, selectedExchange],
    queryFn: () => readonlyApiClient.usQuote(selectedSymbol, selectedExchange),
    enabled: pageReady && Boolean(selectedSymbol),
    refetchInterval: 60_000,
    retry: false,
  });

  const rows = useMemo(() => (ranking.data?.items ?? []).slice(0, 30), [ranking.data?.items]);
  const rankingRealtime = useRankingRealtime(
    session?.accessToken ?? "",
    rows,
    pageReady && activeTab !== "holdings",
  );
  const quoteRealtime = useQuoteRealtime(
    session?.accessToken ?? "",
    selectedSymbol,
    selectedExchange,
    pageReady && Boolean(selectedSymbol),
  );
  const realtimeRows = useMemo(
    () => activeTab === "holdings" ? rows : mergeRankingRealtime(rows, rankingRealtime.items, activeTab),
    [activeTab, rankingRealtime.items, rows],
  );
  const watchRows = extractHoldingWatchItems(holdings.data);
  const selectedHolding = watchRows.find((item) => item.symbol.toUpperCase() === selectedSymbol);
  const selectedQuote = quoteRealtime.item
    ?? selectedRealtime.data?.items.find((item) => item.symbol.toUpperCase() === selectedSymbol);
  const activeSpec = TABS.find((tab) => tab.value === activeTab) ?? TABS[0];

  return (
    <>
      <TopBar />
      <main className="space-y-3 p-4">
        <section className="card-base space-y-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h1 className="text-xl font-bold">시세분석</h1>
              <p className="mt-1 text-xs text-muted-foreground">키움 미국주식 순위 데이터 기준</p>
            </div>
            <span className="chip">
              <RefreshCw className={cn("h-3.5 w-3.5", (activeTab === "holdings" ? holdings.isFetching : ranking.isFetching) && "animate-spin")} />
              {(activeTab === "holdings" ? holdings.isFetching : ranking.isFetching)
                ? "갱신 중"
                : activeTab === "holdings"
                  ? "5초 갱신"
                  : rankingRealtime.state === "connected"
                    ? "WebSocket 2초"
                    : "순위 30초"}
            </span>
          </div>

          <div className="grid grid-cols-3 gap-1 rounded-xl border border-border bg-background p-1">
            {TABS.map((tab) => (
              <button
                key={tab.value}
                type="button"
                onClick={() => setActiveTab(tab.value)}
                className={cn(
                  "rounded-lg px-3 py-2 text-sm font-semibold",
                  activeTab === tab.value ? "bg-primary text-primary-foreground" : "text-muted-foreground",
                )}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <div className="rounded-xl border border-border bg-surface-3/40 px-3 py-2">
            <div className="flex items-center gap-2 text-sm font-semibold">
              {activeTab === "change-rate" ? <TrendingUp className="h-4 w-4 text-primary" /> : activeTab === "volume" ? <BarChart3 className="h-4 w-4 text-primary" /> : <ShieldAlert className="h-4 w-4 text-primary" />}
              {activeSpec.label}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">{activeSpec.description}</p>
          </div>
        </section>

        {selectedSymbol ? (
          <SelectedSecurityCard
            symbol={selectedSymbol}
            exchange={selectedHolding?.exchange ?? selectedExchange}
            holding={selectedHolding}
            quote={selectedQuote}
            restQuote={selectedRestQuote.data}
            monitorConnected={quoteRealtime.monitorConnected}
            monitored={quoteRealtime.monitoredSymbols.includes(selectedSymbol)}
            realtimeState={quoteRealtime.state}
            monitorLastError={quoteRealtime.lastError}
            marketSession={selectedRealtime.data?.marketSession}
            holdingsUpdatedAt={holdings.data?.updatedAt}
            loading={quoteRealtime.state === "connecting" && !selectedQuote && selectedRestQuote.isLoading}
            error={quoteRealtime.state === "unavailable" && selectedRealtime.isError && selectedRestQuote.isError}
          />
        ) : null}

        {activeTab === "holdings" ? (
          <HoldingWatchList
            rows={watchRows}
            loading={holdings.isLoading || !pageReady}
            error={holdings.isError}
            updatedAt={holdings.data?.updatedAt}
          />
        ) : (
          <RankingList
            query={ranking.data}
            rows={realtimeRows}
            loading={ranking.isLoading || !pageReady}
            error={ranking.isError}
            realtimeState={rankingRealtime.state}
            realtimeUpdatedAt={rankingRealtime.updatedAt}
            monitoredCount={rankingRealtime.monitoredCount}
          />
        )}
      </main>
    </>
  );
}

function HoldingWatchList({ rows, loading, error, updatedAt }: { rows: HoldingWatchItem[]; loading: boolean; error: boolean; updatedAt?: string }) {
  if (loading) return <section className="card-base py-8 text-center text-sm text-muted-foreground">실계좌 보유종목을 확인하는 중입니다.</section>;
  if (error) return <section className="card-base"><div className="rounded-xl border border-warning/40 bg-warning-soft/40 px-3 py-4 text-sm text-warning">보유종목을 불러오지 못했습니다. 로그인 세션과 백엔드 연결을 확인하세요.</div></section>;

  return (
    <section className="card-base space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div><h2 className="font-semibold">보유종목 감시</h2><p className="text-xs text-muted-foreground">{updatedAt ? formatTime(updatedAt) : "최근 갱신 대기"}</p></div>
        <span className="chip"><Activity className="h-3.5 w-3.5" />{rows.length}개</span>
      </div>
      {!rows.length ? <div className="rounded-xl border border-border bg-background px-3 py-8 text-center text-sm text-muted-foreground">현재 감시할 미국주식 보유종목이 없습니다.</div> : (
        <div className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-background">
          {rows.map((row) => <HoldingWatchRow key={`${row.exchange}-${row.symbol}`} row={row} />)}
        </div>
      )}
      <p className="text-[10.5px] text-muted-foreground">상태 알림만 제공하며 주문은 전송하지 않습니다.</p>
    </section>
  );
}

function HoldingWatchRow({ row }: { row: HoldingWatchItem }) {
  const status = row.reason === "take_profit" ? "익절 검토" : row.reason === "stop_loss" ? "손절 검토" : "대기";
  return (
    <Link to={`/quotes?symbol=${encodeURIComponent(row.symbol)}&exchange=${encodeURIComponent(row.exchange)}`} className="grid grid-cols-[1fr_auto] items-center gap-3 px-3 py-3 hover:bg-muted/60">
      <div className="min-w-0"><div className="truncate text-sm font-semibold">{row.name}</div><div className="mt-0.5 text-[11px] text-muted-foreground">{row.symbol} · {row.exchange}</div></div>
      <div className="text-right">
        <div className={cn("num text-sm font-bold", row.reason === "take_profit" ? "text-up" : row.reason === "stop_loss" ? "text-down" : "text-foreground")}>{formatSignedPercent(row.returnRate)}</div>
        <div className={cn("mt-0.5 text-[10px] font-semibold", row.reason === "waiting" ? "text-muted-foreground" : "text-warning")}>{status}</div>
      </div>
    </Link>
  );
}

function SelectedSecurityCard({
  symbol,
  exchange,
  holding,
  quote,
  restQuote,
  monitorConnected,
  monitored,
  realtimeState,
  monitorLastError,
  marketSession,
  holdingsUpdatedAt,
  loading,
  error,
}: {
  symbol: string;
  exchange: string;
  holding?: HoldingWatchItem;
  quote?: QuoteRealtimeItem | UsRealtimeWindowItem;
  restQuote?: UsQuoteResponse;
  monitorConnected: boolean;
  monitored: boolean;
  realtimeState: RealtimeConnectionState;
  monitorLastError: string | null;
  marketSession?: string;
  holdingsUpdatedAt?: string;
  loading: boolean;
  error: boolean;
}) {
  const status = holding?.reason === "take_profit" ? "익절 검토" : holding?.reason === "stop_loss" ? "손절 검토" : holding ? "대기" : "보유 아님";
  const freshness = getRealtimeFreshness(quote);
  const connected = monitorConnected && monitored && realtimeState === "connected";
  const realtimeFresh = connected && freshness.state === "fresh";
  const realtimePrice = realtimeFresh ? quote?.latestPrice : undefined;
  const displayPrice = realtimePrice ?? holding?.price ?? restQuote?.price;
  const quoteSource = realtimePrice != null
    ? "WebSocket"
    : holding?.price != null
      ? "계좌 현재가"
      : restQuote?.price != null
        ? "REST 현재가"
        : restQuote?.name
          ? "REST 종목정보"
          : "데이터 없음";
  return (
    <section className="card-base space-y-3 border-primary/25">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2"><h2 className="truncate text-lg font-bold">{holding?.name ?? restQuote?.name ?? symbol}</h2><span className="chip">{symbol} · {exchange}</span></div>
          <div className="mt-1 flex items-center gap-1.5 text-[11px] text-muted-foreground"><Radio className={cn("h-3 w-3", connected && realtimeFresh && "text-success")} />{connected && realtimeFresh ? "실시간 연결" : `보완 조회 · ${quoteSource}`}</div>
        </div>
        <Link to="/quotes" className="text-xs font-medium text-muted-foreground hover:text-foreground">선택 해제</Link>
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <QuoteMetric label={`현재가 · ${quoteSource}`} value={displayPrice == null ? "-" : formatPrice(displayPrice)} />
        <QuoteMetric label="계좌 수익률" value={holding ? formatSignedPercent(holding.returnRate) : "-"} tone={holding?.returnRate} />
        <QuoteMetric label="매수호가" value={!realtimeFresh || quote?.bid == null ? "-" : formatPrice(quote.bid)} />
        <QuoteMetric label="매도호가" value={!realtimeFresh || quote?.ask == null ? "-" : formatPrice(quote.ask)} />
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <DataStatus
          label="실시간 상태"
          value={!monitored ? "미구독" : freshness.state === "fresh" ? "신선" : freshness.state === "stale" ? "오래됨" : "수신 없음"}
          warning={!monitored || freshness.state !== "fresh"}
          icon={!monitored ? <WifiOff className="h-3.5 w-3.5" /> : <Radio className="h-3.5 w-3.5" />}
        />
        <DataStatus label="마지막 이벤트" value={formatDataAge(freshness.ageMs)} warning={freshness.state === "stale"} icon={<Clock3 className="h-3.5 w-3.5" />} />
        <DataStatus label="수신 지연" value={freshness.receiveDelayMs === null ? "측정 없음" : `${freshness.receiveDelayMs.toLocaleString("ko-KR")}ms`} warning={freshness.delayed} />
        <DataStatus label="미국장 세션" value={marketSessionLabel(marketSession)} />
      </div>
      <p className="text-[10.5px] text-muted-foreground">
        {realtimeFresh && quote?.lastEventAt
          ? `실시간 수신 ${formatDateTime(quote.lastEventAt)}`
          : holding?.price != null && holdingsUpdatedAt
            ? `계좌 현재가 조회 ${formatDateTime(holdingsUpdatedAt)}`
            : restQuote?.updatedAt
              ? `종목정보 조회 ${formatDateTime(restQuote.updatedAt)}`
              : "확인 가능한 데이터 시각이 없습니다."}
      </p>
      <div className={cn("rounded-lg border px-3 py-2 text-xs", holding?.reason === "waiting" || !holding ? "border-border text-muted-foreground" : "border-warning/40 bg-warning-soft/40 text-warning")}>{status} · 주문 전송 없음</div>
      {loading ? <p className="text-xs text-muted-foreground">실시간 데이터를 확인하는 중입니다.</p> : null}
      {error ? <p className="text-xs text-warning">실시간 데이터를 불러오지 못했습니다.</p> : null}
      {monitorLastError ? <p className="text-xs text-warning">WebSocket 재연결 중 · {monitorLastError}</p> : null}
    </section>
  );
}

function DataStatus({ label, value, warning = false, icon }: { label: string; value: string; warning?: boolean; icon?: React.ReactNode }) {
  return (
    <div className={cn("rounded-xl border bg-background px-3 py-2.5", warning ? "border-warning/40" : "border-border")}>
      <div className="flex items-center gap-1 text-[10.5px] text-muted-foreground">{icon}{label}</div>
      <div className={cn("mt-1 text-xs font-semibold", warning ? "text-warning" : "text-foreground")}>{value}</div>
    </div>
  );
}

function QuoteMetric({ label, value, tone }: { label: string; value: string; tone?: number }) {
  return <div className="rounded-xl border border-border bg-background px-3 py-3"><div className="text-[10.5px] text-muted-foreground">{label}</div><div className={cn("num mt-1 text-sm font-bold", tone === undefined ? "text-foreground" : tone >= 0 ? "text-up" : "text-down")}>{value}</div></div>;
}

function RankingList({
  query,
  rows,
  loading,
  error,
  realtimeState,
  realtimeUpdatedAt,
  monitoredCount,
}: {
  query?: MarketRankingResponse;
  rows: MarketRankItem[];
  loading: boolean;
  error: boolean;
  realtimeState: "idle" | "connecting" | "connected" | "reconnecting" | "unavailable";
  realtimeUpdatedAt: string | null;
  monitoredCount: number;
}) {
  if (loading) {
    return (
      <section className="card-base">
        <div className="py-8 text-center text-sm text-muted-foreground">시세 데이터를 불러오는 중입니다.</div>
      </section>
    );
  }

  if (error) {
    return (
      <section className="card-base">
        <div className="rounded-xl border border-warning/40 bg-warning-soft/40 px-3 py-4 text-sm text-warning">
          시세 데이터를 불러오지 못했습니다. 로그인 세션과 백엔드 연결을 확인하세요.
        </div>
      </section>
    );
  }

  return (
    <section className="card-base space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div>
          <h2 className="font-semibold">종목 리스트</h2>
          <p className="text-xs text-muted-foreground">{query?.updatedAt ? formatTime(query.updatedAt) : "최근 갱신 대기"}</p>
        </div>
        <span className="chip">
          <Activity className="h-3.5 w-3.5" />
          {rows.length}개
        </span>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-surface-3/40 px-3 py-2 text-[11px] text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <Radio className={cn("h-3.5 w-3.5", realtimeState === "connected" && "text-success")} />
          {realtimeState === "connected" ? "WebSocket 2초 연결" : realtimeState === "reconnecting" ? "WebSocket 재연결 중" : "WebSocket 연결 중"}
        </span>
        <span>가격·등락률·거래량 {monitoredCount}/20 · {realtimeUpdatedAt ? formatTime(realtimeUpdatedAt) : "수신 대기"}</span>
      </div>

      {!rows.length ? (
        <div className="rounded-xl border border-border bg-background px-3 py-8 text-center text-sm text-muted-foreground">
          표시할 종목이 없습니다.
        </div>
      ) : (
        <div className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-background">
          {rows.map((row) => <RankingRow key={`${row.rank}-${row.exchange ?? "US"}-${row.code}`} row={row} />)}
        </div>
      )}
    </section>
  );
}

function RankingRow({ row }: { row: MarketRankItem }) {
  const positive = row.changeRate >= 0;
  return (
    <Link to={`/quotes?symbol=${encodeURIComponent(row.code)}&exchange=${encodeURIComponent(safeExchange(row.exchange))}`} className="grid grid-cols-[42px_1fr_auto] items-center gap-3 px-3 py-3 hover:bg-muted/60">
      <div className="num text-center text-sm font-bold text-muted-foreground">{row.rank}</div>
      <div className="min-w-0">
        <div className="flex min-w-0 items-center gap-2">
          <span className="truncate text-sm font-semibold">{row.code}</span>
          {row.exchange ? <span className="rounded bg-surface-3 px-1.5 py-0.5 text-[10px] text-muted-foreground">{row.exchange}</span> : null}
        </div>
        <div className="mt-0.5 truncate text-xs text-muted-foreground">{row.name || row.reason || "-"}</div>
        <div className="mt-1 flex gap-3 text-[11px] text-muted-foreground">
          <span>거래량 {formatCompact(row.volume)}</span>
          <span>거래대금 {formatCompact(row.tradingValue)}</span>
        </div>
      </div>
      <div className="text-right">
        <div className="num text-sm font-bold">{formatPrice(row.price)}</div>
        <div className={cn("num mt-0.5 text-xs font-semibold", positive ? "text-up" : "text-down")}>
          {formatSignedPercent(row.changeRate)}
        </div>
      </div>
    </Link>
  );
}

function safeSymbol(value: string | null) {
  const symbol = String(value ?? "").trim().toUpperCase();
  return /^[A-Z0-9.-]{1,12}$/.test(symbol) ? symbol : "";
}

function safeExchange(value: string | null) {
  const exchange = String(value ?? "").trim().toUpperCase();
  return ["ND", "NY", "NA"].includes(exchange) ? exchange : "ND";
}

function formatPrice(value: number) {
  if (!Number.isFinite(value)) return "-";
  return `$${value.toLocaleString("ko-KR", { maximumFractionDigits: 4 })}`;
}

function formatSignedPercent(value: number) {
  if (!Number.isFinite(value)) return "-";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toLocaleString("ko-KR", { maximumFractionDigits: 2 })}%`;
}

function formatCompact(value: number | null) {
  if (value === null || !Number.isFinite(value)) return "-";
  return value.toLocaleString("ko-KR", { notation: "compact", maximumFractionDigits: 1 });
}

function formatTime(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "최근 갱신";
  return `${parsed.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })} 갱신`;
}

function formatDateTime(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "시각 확인 불가";
  return parsed.toLocaleString("ko-KR", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function marketSessionLabel(value?: string) {
  if (value === "premarket") return "프리마켓";
  if (value === "regular") return "정규장";
  if (value === "afterhours") return "애프터마켓";
  if (value === "closed") return "장 마감";
  return "확인 중";
}
