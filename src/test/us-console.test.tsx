import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import UsConsole from "@/pages/UsConsole";

vi.mock("recharts", async (orig) => {
  const mod = await orig<typeof import("recharts")>();
  return { ...mod, ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div style={{ width: 400, height: 160 }}>{children}</div> };
});

const renderAt = (url: string) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[url]}>
        <UsConsole />
      </MemoryRouter>
    </QueryClientProvider>,
  );

describe("UsConsole", () => {
  it("잠금 상태·ET 시계·읽기 전용을 표시하고 주문 버튼이 없다", async () => {
    renderAt("/");
    expect(await screen.findByTestId("gate-pill")).toHaveTextContent("주문 잠금");
    expect(screen.getByTestId("et-clock")).toHaveTextContent(/^ET \d{2}:\d{2}:\d{2}$/);
    expect(screen.getAllByText("읽기 전용").length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: /매수|매도|주문 실행|관리자 ON/ })).toBeNull();
  });

  it("URL symbol 선택 시 해당 종목 패널과 스프레드 평가", async () => {
    renderAt("/?symbol=NXXT&exchange=NASDAQ");
    const panel = await screen.findByRole("region", { name: "NXXT 상세" });
    expect(await within(panel).findByTestId("spread-eval")).toHaveTextContent("호가 역전");
  });

  it("잘못된 symbol 파라미터는 첫 적격 종목으로 대체", async () => {
    renderAt("/?symbol=<script>");
    expect(await screen.findByRole("region", { name: "PLCE 상세" })).toBeInTheDocument();
  });

  it("검증 요약은 미완료", async () => {
    renderAt("/");
    expect(await screen.findByTestId("verdict")).toHaveTextContent("미완료");
  });
});
