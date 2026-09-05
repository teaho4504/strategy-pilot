import { useEffect, useMemo, useState } from "react";
import { apiWebSocketUrl, type UsAutoTradeStrategyStatusItem } from "@/services/apiClient";
import type { RealtimeConnectionState } from "@/hooks/use-quote-realtime";

export interface ConditionRealtimeItem {
  seq: string;
  selectedSeq: string | null;
  selectedName: string | null;
  connected: boolean;
  matchCount: number;
  matches: UsAutoTradeStrategyStatusItem["conditionMatches"];
  error: string | null;
  errorType?: string | null;
}

interface ConditionSnapshot {
  type: "CONDITION_SNAPSHOT";
  items: ConditionRealtimeItem[];
}

export function useConditionRealtime(
  sessionToken: string,
  requestedSeqs: string[],
  enabled: boolean,
) {
  const seqs = useMemo(
    () => Array.from(new Set(requestedSeqs.filter(Boolean))).slice(0, 10),
    [requestedSeqs],
  );
  const signature = seqs.join(",");
  const [items, setItems] = useState<ReadonlyMap<string, ConditionRealtimeItem>>(new Map());
  const [state, setState] = useState<RealtimeConnectionState>("idle");
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled || !sessionToken || !seqs.length) {
      setState("idle");
      setItems(new Map());
      return;
    }

    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let reconnectAttempt = 0;
    let stopped = false;

    const connect = () => {
      setState(reconnectAttempt ? "reconnecting" : "connecting");
      socket = new WebSocket(apiWebSocketUrl("/api/realtime/us/conditions/ws"));
      socket.onopen = () => {
        socket?.send(JSON.stringify({
          type: "AUTH",
          token: sessionToken,
          provider: "kiwoom",
          seqs,
        }));
      };
      socket.onmessage = (event) => {
        let message: ConditionSnapshot | { type?: string; errorType?: string };
        try {
          message = JSON.parse(String(event.data));
        } catch {
          return;
        }
        if (message.type === "CONDITION_STATUS") {
          reconnectAttempt = 0;
          setState("connected");
          return;
        }
        if (message.type !== "CONDITION_SNAPSHOT") return;
        const snapshot = message as ConditionSnapshot;
        setItems(new Map(snapshot.items.map((item) => [item.seq, item])));
        setUpdatedAt(new Date().toISOString());
        setState("connected");
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
  // signature intentionally stabilizes the condition subscription.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, sessionToken, signature]);

  return { items, state, updatedAt };
}
