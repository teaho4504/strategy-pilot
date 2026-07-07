import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import {
  ApiClientError,
  readonlyApiClient,
  setAccessTokenProvider,
  setUnauthorizedHandler,
} from "@/services/apiClient";

afterEach(() => {
  setAccessTokenProvider(null);
  setUnauthorizedHandler(null);
  vi.restoreAllMocks();
});

describe("frontend auth API integration", () => {
  it("does not call protected APIs before login", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");

    render(<App />);

    await screen.findByText("Strategy Pilot");
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("blocks protected API requests when no access token exists", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");

    await expect(readonlyApiClient.accounts()).rejects.toMatchObject({ type: "missing_token" });
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("adds Authorization bearer token after login", async () => {
    setAccessTokenProvider(() => "session-token");
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } }),
    );

    await readonlyApiClient.accounts();

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy.mock.calls[0][1]?.headers).toEqual({ Authorization: "Bearer session-token" });
  });

  it("stops protected API calls after logout clears the token", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    setAccessTokenProvider(() => null);

    await expect(readonlyApiClient.watchlist()).rejects.toBeInstanceOf(ApiClientError);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("runs the unauthorized handler on 401", async () => {
    setAccessTokenProvider(() => "expired-token");
    const unauthorized = vi.fn();
    setUnauthorizedHandler(unauthorized);
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 401 }));

    await expect(readonlyApiClient.accounts()).rejects.toMatchObject({ status: 401, type: "unauthorized" });

    await waitFor(() => expect(unauthorized).toHaveBeenCalledTimes(1));
  });
});
