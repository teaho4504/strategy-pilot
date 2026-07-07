import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import {
  ApiClientError,
  readonlyApiClient,
  setAccessTokenProvider,
  setUnauthorizedHandler,
} from "@/services/apiClient";

let authStateCallback: ((event: string, session: unknown) => void) | null = null;

vi.mock("@/integrations/supabase/client", () => ({
  isSupabaseConfigured: true,
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
      onAuthStateChange: vi.fn((callback) => {
        authStateCallback = callback;
        return { data: { subscription: { unsubscribe: vi.fn() } } };
      }),
      signInWithPassword: vi.fn(),
      updateUser: vi.fn().mockResolvedValue({ data: { user: null }, error: null }),
      signOut: vi.fn().mockResolvedValue({ error: null }),
    },
  },
}));

beforeEach(async () => {
  const { supabase } = await import("@/integrations/supabase/client");
  vi.mocked(supabase?.auth.getSession).mockResolvedValue({ data: { session: null }, error: null });
  vi.mocked(supabase?.auth.onAuthStateChange).mockImplementation((callback) => {
    authStateCallback = callback;
    return { data: { subscription: { id: "test-subscription", callback, unsubscribe: vi.fn() } } };
  });
  vi.mocked(supabase?.auth.signInWithPassword).mockResolvedValue({ data: { session: null, user: null }, error: null });
  vi.mocked(supabase?.auth.updateUser).mockResolvedValue({ data: { user: null }, error: null });
  vi.mocked(supabase?.auth.signOut).mockResolvedValue({ error: null });
});

afterEach(() => {
  setAccessTokenProvider(null);
  setUnauthorizedHandler(null);
  window.history.replaceState(null, document.title, "/");
  vi.restoreAllMocks();
  authStateCallback = null;
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

  it("renders password recovery without protected API calls", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");

    render(<App />);
    await screen.findByText("Strategy Pilot");

    act(() => {
      authStateCallback?.("PASSWORD_RECOVERY", { access_token: "recovery-token", user: { email: "user@example.com" } });
    });

    await screen.findByText("새 비밀번호 설정");
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("detects recovery redirect URL before rendering dashboard", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    window.history.replaceState(null, document.title, "/#type=recovery&access_token=placeholder");

    render(<App />);

    await screen.findByText("새 비밀번호 설정");
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("updates recovery password then signs out", async () => {
    const { supabase } = await import("@/integrations/supabase/client");

    render(<App />);
    await screen.findByText("Strategy Pilot");
    act(() => {
      authStateCallback?.("PASSWORD_RECOVERY", { access_token: "recovery-token", user: { email: "user@example.com" } });
    });

    fireEvent.change(await screen.findByLabelText("새 비밀번호"), { target: { value: "new-password-1" } });
    fireEvent.change(screen.getByLabelText("새 비밀번호 확인"), { target: { value: "new-password-1" } });
    fireEvent.click(screen.getByRole("button", { name: "비밀번호 설정" }));

    await waitFor(() => expect(supabase?.auth.updateUser).toHaveBeenCalledWith({ password: "new-password-1" }));
    await waitFor(() => expect(supabase?.auth.signOut).toHaveBeenCalled());
  });
});
