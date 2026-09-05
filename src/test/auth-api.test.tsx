import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import {
  ApiClientError,
  postKiwoomLogout,
  readonlyApiClient,
  setAccessTokenProvider,
  setUnauthorizedHandler,
} from "@/services/apiClient";

afterEach(() => {
  setAccessTokenProvider(null);
  setUnauthorizedHandler(null);
  sessionStorage.clear();
  vi.restoreAllMocks();
});

describe("Kiwoom credential auth API integration", () => {
  it("does not call protected APIs before Kiwoom login", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");

    render(<App />);

    await screen.findByText("키움 계좌 로그인");
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("blocks protected API requests when no session token exists", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");

    await expect(readonlyApiClient.usHoldings()).rejects.toMatchObject({ type: "missing_token" });
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("shows only saved kiwoomcli profiles and hides manual broker credential inputs", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/api/auth/kiwoom/profiles")) {
        expect(init?.headers).toEqual({ "X-Dashboard-Pin": "123456" });
        return new Response(JSON.stringify([
          { profile: "실전계좌-A", mode: "real", current: false, accountLabel: "****-1001 [위탁종합]" },
          { profile: "실전계좌-B", mode: "real", current: true, accountLabel: "****-1002 [위탁종합]" },
          { profile: "실전계좌-C", mode: "real", current: false, accountLabel: "****-1003 [위탁종합]" },
        ]), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.endsWith("/api/auth/kiwoom/profile-login")) {
        expect(JSON.parse(String(init?.body))).toEqual({ profile: "실전계좌-B", accessPin: "123456" });
        return new Response(JSON.stringify({
          accessToken: "backend-session-token",
          tokenType: "Bearer",
          mode: "live",
          accountLabel: "****-0000",
          baseUrl: "https://api.kiwoom.com",
          readOnly: true,
          orderEnabled: false,
          expiresAt: new Date(Date.now() + 60_000).toISOString(),
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      return new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } });
    });

    render(<App />);

    fireEvent.change(screen.getByLabelText("대시보드 접근 PIN"), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "프로필 조회" }));
    await screen.findByText("실전계좌-B · 현재");
    expect(screen.getByText("3개 등록")).toBeInTheDocument();
    expect(screen.getByText(/\*\*\*\*-1001/)).toBeInTheDocument();
    expect(screen.getByText(/\*\*\*\*-1002/)).toBeInTheDocument();
    expect(screen.getByText(/\*\*\*\*-1003/)).toBeInTheDocument();
    expect(screen.queryByPlaceholderText("계좌번호 직접 입력")).toBeNull();
    expect(screen.queryByPlaceholderText("키움에서 발급받은 App Key")).toBeNull();
    expect(screen.queryByPlaceholderText("사용자만 알고 있는 Secret Key")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /실전계좌-B.*로그인/ }));

    await screen.findByText("평가자산");
    expect(fetchSpy).toHaveBeenCalled();
    const stored = sessionStorage.getItem("strategy-pilot-kiwoom-session") ?? "";
    expect(stored).toContain("backend-session-token");
    expect(stored).not.toContain("test-secret-key");
    expect(stored).not.toContain("test-app-key");
    expect(stored).not.toContain("test-account");
  });

  it("uses a saved kiwoomcli profile without storing broker credentials in the browser", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/api/auth/kiwoom/profiles")) {
        expect(init?.headers).toEqual({ "X-Dashboard-Pin": "123456" });
        return new Response(JSON.stringify([
          { profile: "실전계좌", mode: "real", current: true, accountLabel: "****-6911" },
        ]), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.endsWith("/api/auth/kiwoom/profile-login")) {
        expect(JSON.parse(String(init?.body))).toEqual({ profile: "실전계좌", accessPin: "123456" });
        return new Response(JSON.stringify({
          accessToken: "backend-session-token",
          tokenType: "Bearer",
          mode: "live",
          accountLabel: "****-계좌",
          baseUrl: "https://api.kiwoom.com",
          readOnly: true,
          orderEnabled: false,
          expiresAt: new Date(Date.now() + 60_000).toISOString(),
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      return new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } });
    });

    render(<App />);

    fireEvent.change(screen.getByLabelText("대시보드 접근 PIN"), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "프로필 조회" }));
    fireEvent.click(await screen.findByRole("button", { name: /실전계좌.*로그인/ }));

    await screen.findByText("평가자산");
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining("/api/auth/kiwoom/profile-login"),
      expect.objectContaining({ method: "POST" }),
    );
    const stored = sessionStorage.getItem("strategy-pilot-kiwoom-session") ?? "";
    expect(stored).toContain("backend-session-token");
    expect(stored).not.toContain("test-app-key");
    expect(stored).not.toContain("test-secret-key");
    expect(stored).not.toContain("test-account");
  });

  it("explains a blocked token endpoint redirect without exposing response data", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/api/auth/kiwoom/profiles")) {
        return new Response(JSON.stringify([
          { profile: "실전계좌", mode: "real", current: true, accountLabel: "****-6911" },
        ]), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.endsWith("/api/auth/kiwoom/profile-login")) {
        return new Response(JSON.stringify({
          detail: {
            message: "Kiwoom CLI profile verification failed",
            httpStatus: 302,
            returnCode: "TOKEN_ENDPOINT_REDIRECT",
            returnMessage: "Secure token issuance is temporarily unavailable",
          },
        }), { status: 401, headers: { "Content-Type": "application/json" } });
      }
      return new Response("{}", { status: 404 });
    });

    render(<App />);

    fireEvent.change(screen.getByLabelText("대시보드 접근 PIN"), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "프로필 조회" }));
    fireEvent.click(await screen.findByRole("button", { name: /실전계좌.*로그인/ }));

    expect(await screen.findByText(/키움 토큰 서버가 정상 응답 대신 다른 페이지로 연결/)).toBeInTheDocument();
    expect(screen.queryByText(/Secure token issuance/)).toBeNull();
  });

  it("adds Authorization bearer session token after login", async () => {
    setAccessTokenProvider(() => "backend-session-token");
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } }),
    );

    await readonlyApiClient.usHoldings();

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy.mock.calls[0][1]?.headers).toEqual({ Authorization: "Bearer backend-session-token" });
  });

  it("stops protected API calls after logout clears the token", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    setAccessTokenProvider(() => null);

    await expect(readonlyApiClient.usHoldings()).rejects.toBeInstanceOf(ApiClientError);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("notifies the backend when a Kiwoom session logs out", async () => {
    setAccessTokenProvider(() => "backend-session-token");
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(null, { status: 204 }),
    );

    await postKiwoomLogout();

    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining("/api/auth/kiwoom/logout"),
      {
        method: "POST",
        headers: { Authorization: "Bearer backend-session-token" },
      },
    );
  });

  it("runs the unauthorized handler on 401", async () => {
    setAccessTokenProvider(() => "expired-session-token");
    const unauthorized = vi.fn();
    setUnauthorizedHandler(unauthorized);
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 401 }));

    await expect(readonlyApiClient.usHoldings()).rejects.toMatchObject({ status: 401, type: "unauthorized" });

    await waitFor(() => expect(unauthorized).toHaveBeenCalledTimes(1));
  });

  it("clears a stored Kiwoom session when backend validation returns 401", async () => {
    sessionStorage.setItem("strategy-pilot-kiwoom-session", JSON.stringify({
      accessToken: "stale-backend-session",
      mode: "live",
      accountLabel: "****-6043",
      baseUrl: "https://api.kiwoom.com",
      readOnly: false,
      orderEnabled: true,
      expiresAt: new Date(Date.now() + 60_000).toISOString(),
    }));
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/api/us/orders/status")) {
        return new Response("{}", { status: 401 });
      }
      if (url.endsWith("/api/auth/kiwoom/profiles")) {
        return new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } });
      }
      return new Response("{}", { status: 404 });
    });

    render(<App />);

    await screen.findByText("키움 계좌 로그인");
    expect(sessionStorage.getItem("strategy-pilot-kiwoom-session")).toBeNull();
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining("/api/us/orders/status"),
      expect.objectContaining({ headers: { Authorization: "Bearer stale-backend-session" } }),
    );
  });
});
