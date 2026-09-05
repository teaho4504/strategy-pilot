import { createElement } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import AgentOperations, { AGENT_STAGES, SAMPLE_SIGNAL } from "@/pages/AgentOperations";

vi.mock("@/components/layout/TopBar", () => ({
  TopBar: () => createElement("div", { "data-testid": "top-bar" }),
}));

afterEach(cleanup);

describe("Codex agent operations dashboard", () => {
  it("shows the official orchestration stages in dependency order", () => {
    expect(AGENT_STAGES.map((stage) => stage.id)).toEqual([
      "condition_intake",
      "realtime_market_analyst",
      "pullback_pattern_learner",
      "risk_signal_gate",
      "signal_publisher",
    ]);
    expect(AGENT_STAGES.filter((stage) => stage.lane === "parallel")).toHaveLength(2);
  });

  it("keeps the sample signal non-executing", () => {
    expect(SAMPLE_SIGNAL.executionAuthorized).toBe(false);
    expect(SAMPLE_SIGNAL.destination).toBe("dashboard");
  });

  it("renders every agent in the operations dashboard", () => {
    render(createElement(AgentOperations));

    expect(screen.getByRole("heading", { name: "에이전트 운영 대시보드" })).toBeInTheDocument();
    expect(screen.getByText("조건검색 인테이크")).toBeInTheDocument();
    expect(screen.getByText("실시간 시장 분석")).toBeInTheDocument();
    expect(screen.getByText("눌림 패턴 평가")).toBeInTheDocument();
    expect(screen.getByText("독립 리스크 게이트")).toBeInTheDocument();
    expect(screen.getByText("신호 퍼블리셔")).toBeInTheDocument();
    expect(screen.getByText("READ-ONLY · ORDER BLOCKED")).toBeInTheDocument();
  });
});
