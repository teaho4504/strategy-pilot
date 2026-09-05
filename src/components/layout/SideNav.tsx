import { Activity, BarChart3, Bot, Home, Layers, Settings, ShieldCheck } from "lucide-react";
import { NavLink } from "react-router-dom";
import { cn } from "@/lib/utils";

const items = [
  { to: "/", label: "대시보드", icon: Home, end: true },
  { to: "/quotes", label: "시세", icon: Activity },
  { to: "/strategies", label: "전략", icon: Layers },
  { to: "/analytics", label: "성과", icon: BarChart3 },
  { to: "/agents", label: "에이전트", icon: Bot },
  { to: "/settings", label: "설정", icon: Settings },
];

export function SideNav() {
  return (
    <aside className="fixed inset-y-0 left-0 z-40 hidden w-56 border-r border-border bg-surface-1 md:flex md:flex-col">
      <div className="border-b border-border px-5 py-5">
        <div className="flex items-center gap-3">
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-primary text-primary-foreground">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <div>
            <div className="text-sm font-bold tracking-tight">Strategy Pilot</div>
            <div className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground">Kiwoom US</div>
          </div>
        </div>
      </div>
      <div className="mx-3 mt-3 rounded-xl border border-primary/20 bg-primary/5 p-3">
        <div className="flex items-center gap-2 text-[11px] font-semibold text-primary">
          <span className="h-1.5 w-1.5 rounded-full bg-primary shadow-[0_0_8px_hsl(var(--primary))]" />
          CONTROL CENTER
        </div>
        <p className="mt-1.5 text-[10px] leading-4 text-muted-foreground">계좌·시세·전략 상태를 통합 모니터링합니다.</p>
      </div>
      <nav className="flex-1 space-y-1 p-3" aria-label="주요 메뉴">
        {items.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) => cn(
              "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors",
              isActive ? "bg-primary/12 text-primary" : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            <Icon className="h-[18px] w-[18px]" />
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="border-t border-border p-4 text-[11px] leading-5 text-muted-foreground">
        <div className="mb-1 font-semibold text-foreground">Kiwoom data gateway</div>
        서버 경유 · 비밀정보 보호<br />주문 정책은 서버에서 검증
      </div>
    </aside>
  );
}
