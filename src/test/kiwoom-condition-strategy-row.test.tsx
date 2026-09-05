import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ConditionStrategyRow } from "@/pages/Strategies";

describe("ConditionStrategyRow", () => {
  it("shows a Kiwoom HTS condition and its realtime TR flow", () => {
    const onToggle = vi.fn();
    const onExpand = vi.fn();

    const { rerender } = render(
      <ConditionStrategyRow
        status={{
          strategy: "kiwoom-condition-007",
          strategyName: "HTS 급등 조건",
          enabled: true,
          conditionSeq: "007",
          conditionName: "HTS 급등 조건",
          conditionConnected: true,
          conditionRegistered: true,
          conditionMatchCount: 12,
          conditionMatches: [{ code: "NVDA", name: "NVIDIA", exchange: "ND", price: 100, changeRate: 2, volume: 1_000_000 }],
          conditionError: null,
          conditionLastConnectedAt: "2026-09-05T10:00:00+09:00",
          conditionLastReceivedAt: "2026-09-05T10:00:01+09:00",
          conditionReconnectCount: 0,
          conditionNextRetrySeconds: null,
        }}
        expanded={false}
        toggling={false}
        onToggle={onToggle}
        onExpand={onExpand}
      />,
    );

    expect(screen.getByText("HTS 급등 조건")).toBeInTheDocument();
    expect(screen.getByText("12종목 편입")).toBeInTheDocument();
    expect(screen.getByText("감시 ON")).toBeInTheDocument();
    expect(screen.getByText("실주문 차단")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("switch"));
    expect(onToggle).toHaveBeenCalledWith(false);

    rerender(
      <ConditionStrategyRow
        status={{
          strategy: "kiwoom-condition-007",
          strategyName: "HTS 급등 조건",
          enabled: true,
          conditionSeq: "007",
          conditionName: "HTS 급등 조건",
          conditionConnected: true,
          conditionRegistered: true,
          conditionMatchCount: 12,
          conditionMatches: [{ code: "NVDA", name: "NVIDIA", exchange: "ND", price: 100, changeRate: 2, volume: 1_000_000 }],
          conditionError: null,
          conditionLastConnectedAt: "2026-09-05T10:00:00+09:00",
          conditionLastReceivedAt: "2026-09-05T10:00:01+09:00",
          conditionReconnectCount: 0,
          conditionNextRetrySeconds: null,
        }}
        expanded
        toggling={false}
        onToggle={onToggle}
        onExpand={onExpand}
      />,
    );

    expect(screen.getByText("현재 편입 종목")).toBeInTheDocument();
    expect(screen.getByText("백엔드 WebSocket")).toBeInTheDocument();
    expect(screen.getByText("키움 조건식 등록")).toBeInTheDocument();
    expect(screen.getByText("등록됨")).toBeInTheDocument();
    expect(screen.getByText("NVIDIA")).toBeInTheDocument();
    expect(screen.getByText("NVDA · ND")).toBeInTheDocument();
    expect(screen.queryByText("usa20280")).not.toBeInTheDocument();
  });
});
