import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { useQueryClient } from "@tanstack/react-query";
import { isSupabaseConfigured, supabase } from "@/integrations/supabase/client";
import { setAccessTokenProvider, setUnauthorizedHandler } from "@/services/apiClient";

type AuthStatus = "loading" | "authenticated" | "unauthenticated" | "recovery";

interface AuthContextValue {
  status: AuthStatus;
  session: Session | null;
  email: string | null;
  configured: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  updateRecoveryPassword: (password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function isRecoveryRedirectUrl() {
  if (typeof window === "undefined") return false;
  const hashParams = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  const queryParams = new URLSearchParams(window.location.search);
  return hashParams.get("type") === "recovery" || queryParams.get("type") === "recovery";
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [session, setSession] = useState<Session | null>(null);
  const [status, setStatus] = useState<AuthStatus>(isSupabaseConfigured ? (isRecoveryRedirectUrl() ? "recovery" : "loading") : "unauthenticated");

  const clearRecoveryUrl = useCallback(() => {
    if (typeof window !== "undefined" && (window.location.hash || window.location.search)) {
      window.history.replaceState(null, document.title, window.location.pathname);
    }
  }, []);

  const clearSession = useCallback(() => {
    setSession(null);
    setStatus("unauthenticated");
    queryClient.clear();
    clearRecoveryUrl();
  }, [clearRecoveryUrl, queryClient]);

  useEffect(() => {
    setAccessTokenProvider(() => (status === "authenticated" ? session?.access_token ?? null : null));
  }, [session, status]);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      void supabase?.auth.signOut();
      clearSession();
    });
    return () => {
      setAccessTokenProvider(null);
      setUnauthorizedHandler(null);
    };
  }, [clearSession]);

  useEffect(() => {
    if (!supabase) {
      clearSession();
      return;
    }

    let mounted = true;
    supabase.auth.getSession().then(({ data }) => {
      if (!mounted) return;
      setSession(data.session ?? null);
      if (isRecoveryRedirectUrl()) {
        setStatus("recovery");
        return;
      }
      setStatus(data.session ? "authenticated" : "unauthenticated");
    });

    const { data: listener } = supabase.auth.onAuthStateChange((event, nextSession) => {
      setSession(nextSession);
      setStatus(event === "PASSWORD_RECOVERY" ? "recovery" : nextSession ? "authenticated" : "unauthenticated");
      if (!nextSession) queryClient.clear();
    });

    return () => {
      mounted = false;
      listener.subscription.unsubscribe();
    };
  }, [clearSession, queryClient]);

  const signIn = useCallback(async (email: string, password: string) => {
    if (!supabase) throw new Error("Supabase is not configured");
    const { data, error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) throw error;
    setSession(data.session ?? null);
    setStatus(data.session ? "authenticated" : "unauthenticated");
  }, []);

  const updateRecoveryPassword = useCallback(async (password: string) => {
    if (!supabase) throw new Error("Supabase is not configured");
    const { error } = await supabase.auth.updateUser({ password });
    if (error) throw error;
    await supabase.auth.signOut();
    clearSession();
  }, [clearSession]);

  const signOut = useCallback(async () => {
    if (supabase) await supabase.auth.signOut();
    clearSession();
  }, [clearSession]);

  const value = useMemo<AuthContextValue>(() => ({
    status,
    session,
    email: session?.user.email ?? null,
    configured: isSupabaseConfigured,
    signIn,
    updateRecoveryPassword,
    signOut,
  }), [session, signIn, signOut, status, updateRecoveryPassword]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
