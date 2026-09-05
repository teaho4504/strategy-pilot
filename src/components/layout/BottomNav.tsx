import { NavLink } from "react-router-dom";
import { Home, Layers, BarChart3, Settings, Activity, Bot } from "lucide-react";
import { cn } from "@/lib/utils";

const tabs = [
  { to: "/", label: "홈", icon: Home, end: true },
  { to: "/quotes", label: "시세", icon: Activity },
  { to: "/strategies", label: "전략", icon: Layers },
  { to: "/analytics", label: "분석", icon: BarChart3 },
  { to: "/agents", label: "AI", icon: Bot },
  { to: "/settings", label: "설정", icon: Settings },
];

export function BottomNav() {
  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-surface-1/95 backdrop-blur md:hidden"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
      aria-label="하단 내비게이션"
    >
      <ul className="mx-auto flex max-w-xl items-stretch justify-between px-2">
        {tabs.map(({ to, label, icon: Icon, end }) => (
          <li key={to} className="flex-1">
            <NavLink
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  "flex h-[64px] flex-col items-center justify-center gap-1 rounded-xl text-[11px] font-medium transition-colors",
                  isActive ? "text-primary" : "text-muted-foreground hover:text-foreground"
                )
              }
            >
              {({ isActive }) => (
                <>
                  <Icon className={cn("h-[22px] w-[22px]", isActive && "stroke-[2.4]")} />
                  <span>{label}</span>
                </>
              )}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
