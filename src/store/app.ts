import { create } from "zustand";

// Lightweight app state. Kept tiny — most data flows through service adapters.
// (zustand will be added as a dep alongside this file.)

interface AppState {
  // Demo flag — entire app is demo for prototype
  demoMode: true;
  // 자동매매 전체 상태
  automation: "idle" | "running" | "paused";
  setAutomation: (s: AppState["automation"]) => void;
  selectedAccountId: string;
  setAccount: (id: string) => void;
}

export const useApp = create<AppState>((set) => ({
  demoMode: true,
  automation: "paused",
  setAutomation: (s) => set({ automation: s }),
  selectedAccountId: "acc-demo-1",
  setAccount: (id) => set({ selectedAccountId: id }),
}));
