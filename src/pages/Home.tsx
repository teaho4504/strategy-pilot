import { TopBar } from "@/components/layout/TopBar";
import { PortfolioCard } from "@/components/home/PortfolioCard";
import { AutomationControl } from "@/components/home/AutomationControl";
import { ActiveStrategiesCard } from "@/components/home/ActiveStrategiesCard";
import { TimelineCard } from "@/components/home/TimelineCard";
import { MarketSummary } from "@/components/home/MarketSummary";
import { BackendStatusCard } from "@/components/home/BackendStatusCard";

export default function Home() {
  return (
    <>
      <TopBar />
      <main className="space-y-3 p-4 animate-fade-in">
        <BackendStatusCard />
        <PortfolioCard />
        <AutomationControl />
        <ActiveStrategiesCard />
        <TimelineCard />
        <MarketSummary />
        <p className="px-1 pt-2 text-center text-[11px] text-muted-foreground">
          계좌 데이터는 FastAPI read-only API에서 조회합니다. 주문·정정·취소·자동매매 실행은 미연동 상태입니다.
        </p>
      </main>
    </>
  );
}
