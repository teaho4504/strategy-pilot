import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { QueryClient, useQueryClient } from "@tanstack/react-query";
import {
  KiwoomLoginPayload,
  KiwoomLoginResult,
  postKiwoomLogin,
  postKiwoomLogout,
  postKiwoomProfileLogin,
  setAccessTokenProvider,
  setUnauthorizedHandler,
  validateKiwoomSession,
} from "@/services/apiClient";

type AuthStatus = "loading" | "authenticated" | "unauthenticated";

interface KiwoomSessionState {
  accessToken: string;
  mode: "live";
  accountLabel: string;
  baseUrl: string;
  readOnly: boolean;
  orderEnabled: boolean;
  expiresAt: string;
}

interface AuthContextValue {
  status: AuthStatus;
  session: KiwoomSessionState | null;
  email: string | null;
  configured: boolean;
  signIn: (payload: KiwoomLoginPayload) => Promise<void>;
  signInWithProfile: (profile: string | undefined, accessPin: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const SESSION_STORAGE_KEY = "strategy-pilot-kiwoom-session";
const AuthContext = createContext<AuthContextValue | null>(null);

function readStoredSession(): KiwoomSessionState | null {
  if (typeof sessionStorage === "undefined") return null;
  const raw = sessionStorage.getItem(SESSION_STORAGE_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as KiwoomSessionState;
    if (!parsed.accessToken || !parsed.expiresAt || Date.parse(parsed.expiresAt) <= Date.now()) {
      sessionStorage.removeItem(SESSION_STORAGE_KEY);
      return null;
    }
    return parsed;
  } catch {
    sessionStorage.removeItem(SESSION_STORAGE_KEY);
    return null;
  }
}

function storeSession(session: KiwoomLoginResult) {
  const nextSession: KiwoomSessionState = {
    accessToken: session.accessToken,
    mode: session.mode,
    accountLabel: session.accountLabel,
    baseUrl: session.baseUrl,
    readOnly: session.readOnly,
    orderEnabled: session.orderEnabled,
    expiresAt: session.expiresAt,
  };
  sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(nextSession));
  return nextSession;
}

function applySession(
  loginResult: KiwoomLoginResult,
  queryClient: QueryClient,
  setSession: (session: KiwoomSessionState) => void,
  setStatus: (status: AuthStatus) => void,
) {
  const nextSession = storeSession(loginResult);
  setAccessTokenProvider(() => nextSession.accessToken);
  queryClient.removeQueries({ queryKey: ["us-backdata"] });
  setSession(nextSession);
  setStatus("authenticated");
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [session, setSession] = useState<KiwoomSessionState | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");

  const clearSession = useCallback(() => {
    if (typeof sessionStorage !== "undefined") sessionStorage.removeItem(SESSION_STORAGE_KEY);
    setAccessTokenProvider(null);
    setSession(null);
    setStatus("unauthenticated");
    queryClient.clear();
  }, [queryClient]);

  useEffect(() => {
    let cancelled = false;
    const stored = readStoredSession();
    if (stored) {
      setAccessTokenProvider(() => stored.accessToken);
      queryClient.removeQueries({ queryKey: ["us-backdata"] });
      validateKiwoomSession()
        .then(() => {
          if (cancelled) return;
          setSession(stored);
          setStatus("authenticated");
        })
        .catch(() => {
          if (cancelled) return;
          clearSession();
        });
      return () => {
        cancelled = true;
      };
    }
    setSession(null);
    setStatus("unauthenticated");
    return () => {
      cancelled = true;
    };
  }, [clearSession, queryClient]);

  useEffect(() => {
    setAccessTokenProvider(() => (status === "authenticated" ? session?.accessToken ?? null : null));
  }, [session, status]);

  useEffect(() => {
    setUnauthorizedHandler(() => clearSession());
    return () => {
      setAccessTokenProvider(null);
      setUnauthorizedHandler(null);
    };
  }, [clearSession]);

  const signIn = useCallback(async (payload: KiwoomLoginPayload) => {
    const loginResult = await postKiwoomLogin(payload);
    applySession(loginResult, queryClient, setSession, setStatus);
  }, [queryClient]);

  const signInWithProfile = useCallback(async (profile: string | undefined, accessPin: string) => {
    const loginResult = await postKiwoomProfileLogin(profile, accessPin);
    applySession(loginResult, queryClient, setSession, setStatus);
  }, [queryClient]);

  const signOut = useCallback(async () => {
    try {
      await postKiwoomLogout();
    } finally {
      clearSession();
    }
  }, [clearSession]);

  const value = useMemo<AuthContextValue>(() => ({
    status,
    session,
    email: session ? `${session.mode === "live" ? "실매매" : "모의투자"} · ${session.accountLabel}` : null,
    configured: true,
    signIn,
    signInWithProfile,
    signOut,
  }), [session, signIn, signInWithProfile, signOut, status]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
