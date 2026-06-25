import { TopBar } from "@/components/layout/TopBar";
import { PortfolioCard } from "@/components/home/PortfolioCard";
import { AutomationControl } from "@/components/home/AutomationControl";
import { ActiveStrategiesCard } from "@/components/home/ActiveStrategiesCard";
import { TimelineCard } from "@/components/home/TimelineCard";
import { MarketSummary } from "@/components/home/MarketSummary";

export default function Home() {
  return (
    <>
      <TopBar />
      <main className="space-y-3 p-4 animate-fade-in">
        <PortfolioCard />
        <AutomationControl />
        <ActiveStrategiesCard />
        <TimelineCard />
        <MarketSummary />
        <p className="px-1 pt-2 text-center text-[11px] text-muted-foreground">
          모든 금액·수익률·체결은 예시 데이터입니다. 실거래·실주문 연동 없음.
        </p>
      </main>
    </>
  );
}
