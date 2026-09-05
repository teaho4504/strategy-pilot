import { useEffect, useState } from "react";
import { apiWebSocketUrl } from "@/services/apiClient";
import type { UsLiquidityAnalysisResponse } from "@/types";
import type { RealtimeConnectionState } from "@/hooks/use-quote-realtime";

interface LiquiditySnapshot {
  type: "LIQUIDITY_SNAPSHOT";
  analysis: UsLiquidityAnalysisResponse;
}

export function useLiquidityRealtime(
  sessionToken: string,
  symbol: string,
  exchange = "ND",
  enabled = true,
) {
  const [data, setData] = useState<UsLiquidityAnalysisResponse>();
  const [state, setState] = useState<RealtimeConnectionState>("idle");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled || !sessionToken || !symbol) {
      setState("idle");
      setData(undefined);
      setError(null);
      return;
    }
    let socket: WebSocket | null = null;
    let timer: number | null = null;
    let attempt = 0;
    let stopped = false;
    const connect = () => {
      setState(attempt ? "reconnecting" : "connecting");
      socket = new WebSocket(apiWebSocketUrl("/api/realtime/us/liquidity/ws"));
      socket.onopen = () => socket?.send(JSON.stringify({
        type: "AUTH", token: sessionToken, provider: "kiwoom", symbol, exchange,
        thresholdKrw: 10_000_000,
      }));
      socket.onmessage = (event) => {
        let message: LiquiditySnapshot | { type?: string; errorType?: string };
        try { message = JSON.parse(String(event.data)); } catch { return; }
        if (message.type === "LIQUIDITY_STATUS") {
          attempt = 0;
          setState("connected");
          setError(null);
          return;
        }
        if (message.type === "ERROR") {
          setError(message.errorType ?? "LIQUIDITY_STREAM_UNAVAILABLE");
          setState("unavailable");
          return;
        }
        if (message.type !== "LIQUIDITY_SNAPSHOT") return;
        const snapshot = message as LiquiditySnapshot;
        setData(snapshot.analysis);
        setError(snapshot.analysis.monitor.lastError);
        // This state describes the browser-to-FastAPI socket. Broker FE/FT
        // health is reported independently in analysis.observationQuality.
        setState("connected");
      };
      socket.onerror = () => socket?.close();
      socket.onclose = () => {
        if (stopped) return;
        attempt += 1;
        setState("reconnecting");
        const delay = Math.min(10_000, 1_000 * (2 ** Math.min(attempt - 1, 3)));
        timer = window.setTimeout(connect, delay);
      };
    };
    connect();
    return () => {
      stopped = true;
      if (timer !== null) window.clearTimeout(timer);
      socket?.close();
    };
  }, [enabled, exchange, sessionToken, symbol]);

  return { data, state, error };
}
