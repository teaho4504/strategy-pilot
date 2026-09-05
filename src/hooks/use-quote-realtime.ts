import { useEffect, useState } from "react";
import { apiWebSocketUrl } from "@/services/apiClient";

export type RealtimeConnectionState =
  | "idle"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "unavailable";

export interface QuoteRealtimeItem {
  symbol: string;
  tickCount: number;
  orderbookCount: number;
  latestPrice: number | null;
  latestChangeRate: number | null;
  latestVolume: number | null;
  volume10sDelta: number | null;
  volume10sIncreasing: boolean | null;
  tradeStrength: number | null;
  tradeStrengthIncreasing: boolean | null;
  bid: number | null;
  ask: number | null;
  spreadPct: number | null;
  spreadWithin01Pct: boolean | null;
  lastEventAt: string | null;
  sourceEventTime: string | null;
  receiveDelayMs: number | null;
}

interface QuoteSnapshot {
  type: "QUOTE_SNAPSHOT";
  monitorConnected: boolean;
  monitoredSymbols: string[];
  lastError: string | null;
  items: QuoteRealtimeItem[];
}

export function useQuoteRealtime(
  sessionToken: string,
  symbol: string,
  exchange: string,
  enabled: boolean,
) {
  const [item, setItem] = useState<QuoteRealtimeItem | undefined>();
  const [state, setState] = useState<RealtimeConnectionState>("idle");
  const [monitorConnected, setMonitorConnected] = useState(false);
  const [monitoredSymbols, setMonitoredSymbols] = useState<string[]>([]);
  const [lastError, setLastError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled || !sessionToken || !symbol) {
      setState("idle");
      setItem(undefined);
      setMonitorConnected(false);
      setMonitoredSymbols([]);
      return;
    }

    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let reconnectAttempt = 0;
    let stopped = false;

    const connect = () => {
      setState(reconnectAttempt ? "reconnecting" : "connecting");
      socket = new WebSocket(apiWebSocketUrl("/api/realtime/quotes/ws"));
      socket.onopen = () => {
        socket?.send(JSON.stringify({
          type: "AUTH",
          token: sessionToken,
          provider: "kiwoom",
          symbols: [symbol],
          exchanges: { [symbol]: exchange },
        }));
      };
      socket.onmessage = (event) => {
        let message: QuoteSnapshot | { type?: string; errorType?: string };
        try {
          message = JSON.parse(String(event.data));
        } catch {
          return;
        }
        if (message.type === "STATUS") {
          reconnectAttempt = 0;
          setState("connected");
          return;
        }
        if (message.type !== "QUOTE_SNAPSHOT") return;
        const snapshot = message as QuoteSnapshot;
        setMonitorConnected(snapshot.monitorConnected);
        setMonitoredSymbols(snapshot.monitoredSymbols);
        setLastError(snapshot.lastError);
        setItem(snapshot.items.find((row) => row.symbol.toUpperCase() === symbol.toUpperCase()));
        setUpdatedAt(new Date().toISOString());
        setState(snapshot.monitorConnected ? "connected" : "reconnecting");
      };
      socket.onerror = () => socket?.close();
      socket.onclose = () => {
        if (stopped) return;
        reconnectAttempt += 1;
        setState("reconnecting");
        const delay = Math.min(10_000, 1_000 * (2 ** Math.min(reconnectAttempt - 1, 3)));
        reconnectTimer = window.setTimeout(connect, delay);
      };
    };

    connect();
    return () => {
      stopped = true;
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [enabled, exchange, sessionToken, symbol]);

  return {
    item,
    state,
    monitorConnected,
    monitoredSymbols,
    lastError,
    updatedAt,
  };
}
