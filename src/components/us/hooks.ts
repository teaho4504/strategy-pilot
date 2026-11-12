import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { usClient } from "@/services/us/client";
import { mockPlan, mockPositions, mockQuote, mockTop10 } from "@/services/us/mock";

export const useHealth = () => useQuery({ queryKey: ["us", "health"], queryFn: usClient.health, refetchInterval: 5000 });
export const useControl = () => useQuery({ queryKey: ["us", "control"], queryFn: usClient.control, refetchInterval: 5000 });
export const useTop10 = () => useQuery({ queryKey: ["us", "top10"], queryFn: async () => mockTop10(), refetchInterval: 5000 });
export const useQuote = (symbol: string | null) =>
  useQuery({ queryKey: ["us", "quote", symbol], queryFn: async () => mockQuote(symbol!), enabled: !!symbol, refetchInterval: 2000 });
export const usePlan = (symbol: string | null) =>
  useQuery({ queryKey: ["us", "plan", symbol], queryFn: async () => mockPlan(symbol!), enabled: !!symbol });
export const usePositions = () => useQuery({ queryKey: ["us", "positions"], queryFn: async () => mockPositions() });

export function useNow(intervalMs = 1000) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}
