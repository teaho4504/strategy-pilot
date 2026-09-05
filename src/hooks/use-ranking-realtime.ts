import { useEffect, useMemo, useRef, useState } from "react";
import type { MarketRankItem } from "@/types";
import { apiWebSocketUrl } from "@/services/apiClient";
import type { RankingRealtimeItem } from "@/lib/ranking-realtime";

type ConnectionState = "idle" | "connecting" | "connected" | "reconnecting" | "unavailable";

interface RankingSnapshot {
  type: "RANKING_SNAPSHOT";
  monitorConnected: boolean;
  items: RankingRealtimeItem[];
}

export function useRankingRealtime(sessionToken: string, rows: MarketRankItem[], enabled: boolean) {
  const symbols = useMemo(() => rows.slice(0, 20).map((row) => ({
    symbol: row.code.toUpperCase(),
    exchange: row.exchange || "ND",
  })), [rows]);
  const signature = symbols.map((item) => `${item.symbol}:${item.exchange}`).join(",");
  const [items, setItems] = useState<ReadonlyMap<string, RankingRealtimeItem>>(new Map());
  const [state, setState] = useState<ConnectionState>("idle");
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const reconnectAttempt = useRef(0);

  useEffect(() => {
    if (!enabled || !sessionToken || !symbols.length) {
      setState("idle");
      setItems(new Map());
      return;
    }

    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let stopped = false;

    const connect = () => {
      setState(reconnectAttempt.current ? "reconnecting" : "connecting");
      socket = new WebSocket(apiWebSocketUrl("/api/realtime/rankings/ws"));
      socket.onopen = () => {
        reconnectAttempt.current = 0;
        socket?.send(JSON.stringify({ type: "AUTH", token: sessionToken, symbols }));
      };
      socket.onmessage = (event) => {
        let message: RankingSnapshot | { type?: string; errorType?: string };
        try {
          message = JSON.parse(String(event.data));
        } catch {
          return;
        }
        if (message.type !== "RANKING_SNAPSHOT") return;
        setState(message.monitorConnected ? "connected" : "reconnecting");
        setItems(new Map(message.items.map((item) => [item.symbol.toUpperCase(), item])));
        setUpdatedAt(new Date().toISOString());
      };
      socket.onerror = () => socket?.close();
      socket.onclose = () => {
        if (stopped) return;
        reconnectAttempt.current += 1;
        setState("reconnecting");
        const delay = Math.min(10_000, 1_000 * (2 ** Math.min(reconnectAttempt.current - 1, 3)));
        reconnectTimer = window.setTimeout(connect, delay);
      };
    };

    connect();
    return () => {
      stopped = true;
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  // signature intentionally stabilizes the top-20 subscription.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, sessionToken, signature]);

  return { items, state, updatedAt, monitoredCount: items.size };
}
