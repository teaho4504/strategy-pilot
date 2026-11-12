import { Link, useSearchParams } from "react-router-dom";
import { ConsoleTopBar } from "@/components/us/ConsoleTopBar";
import { Top10Watch } from "@/components/us/Top10Watch";
import { SymbolPanel } from "@/components/us/SymbolPanel";
import { GatePanel } from "@/components/us/GatePanel";
import { VerificationPanel } from "@/components/us/VerificationPanel";
import { useTop10 } from "@/components/us/hooks";
import { mockVerification } from "@/services/us/mock";

const SYMBOL_RE = /^[A-Z][A-Z0-9.]{0,9}$/;
const EXCHANGE_RE = /^[A-Z]{2,8}$/;

/** 홈 WTS 3열: 좌 TOP10 / 중 종목 상세 / 우 게이트·검증 (인계서 1.1) */
export default function UsConsole() {
  const [params, setParams] = useSearchParams();
  const top10 = useTop10();
  const raw = params.get("symbol")?.toUpperCase() ?? "";
  const ex = params.get("exchange")?.toUpperCase() ?? "";
  const fallback = top10.data?.items.find((i) => i.state !== "excluded")?.symbol ?? null;
  const symbol = SYMBOL_RE.test(raw) && (!ex || EXCHANGE_RE.test(ex)) ? raw : fallback;

  return (
    <>
      <ConsoleTopBar />
      <main className="grid gap-3 p-3 lg:grid-cols-[300px_1fr] xl:grid-cols-[300px_1fr_320px]">
        <div className="order-2 lg:order-1">
          <Top10Watch selected={symbol} onSelect={(i) => setParams({ symbol: i.symbol, exchange: i.exchange })} />
        </div>
        <div className="order-1 space-y-3 lg:order-2">
          <SymbolPanel symbol={symbol} />
        </div>
        <div className="order-3 space-y-3 lg:col-span-2 xl:col-span-1">
          <GatePanel />
          <VerificationPanel input={mockVerification("pending")} compact />
          <Link to="/verify" className="block text-center text-xs text-primary hover:underline">검증 상세 · 시나리오 보기 →</Link>
        </div>
      </main>
    </>
  );
}
