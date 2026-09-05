import { ReactNode } from "react";
import { BottomNav } from "./BottomNav";
import { SideNav } from "./SideNav";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="dashboard-shell min-h-screen bg-background">
      <SideNav />
      <div className="relative min-h-screen md:pl-56">
        <div className="mx-auto max-w-7xl pb-tabbar md:pb-8">
          {children}
        </div>
      </div>
      <BottomNav />
    </div>
  );
}
