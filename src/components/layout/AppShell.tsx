import { ReactNode } from "react";
import { BottomNav } from "./BottomNav";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-xl pb-tabbar">
        {children}
      </div>
      <BottomNav />
    </div>
  );
}
