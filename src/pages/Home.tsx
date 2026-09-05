import { TopBar } from "@/components/layout/TopBar";
import { PortfolioCard } from "@/components/home/PortfolioCard";
import { AutomationControl } from "@/components/home/AutomationControl";
import { DashboardStatusStrip } from "@/components/home/DashboardStatusStrip";

export default function Home() {
  return (
    <>
      <TopBar />
      <main className="space-y-5 p-4 animate-fade-in md:p-6 lg:p-8">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="mb-2 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-primary">
              <span className="h-px w-6 bg-primary/60" />
              Strategy Pilot Control Center
            </div>
            <h1 className="text-2xl font-bold tracking-[-0.03em] md:text-3xl">계좌 대시보드</h1>
            <p className="mt-1.5 text-xs leading-5 text-muted-foreground">계좌, 시장 데이터, 전략 상태를 한 화면에서 확인합니다.</p>
          </div>
          <div className="inline-flex w-fit items-center gap-2 rounded-full border border-border bg-surface-2/75 px-3 py-1.5 text-[11px] text-muted-foreground">
            <span className="h-1.5 w-1.5 rounded-full bg-success shadow-[0_0_10px_hsl(var(--success))]" />
            서버 경유 · 계정정보 마스킹
          </div>
        </div>
        <DashboardStatusStrip />
        <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.65fr)_minmax(320px,0.85fr)]">
          <PortfolioCard />
          <AutomationControl />
        </div>
      </main>
    </>
  );
}
