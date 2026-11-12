import { ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";
import { BottomNav } from "./BottomNav";

export function AppShell({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  // 미국 운영 콘솔(/, /verify)은 데스크톱 3열, 나머지 KR 데모는 모바일 폭 유지
  const wide = pathname === "/" || pathname === "/verify";
  return (
    <div className="min-h-screen bg-background">
      <div className={cn("mx-auto pb-tabbar", wide ? "max-w-[1440px]" : "max-w-xl")}>
        {children}
      </div>
      <BottomNav />
    </div>
  );
}
