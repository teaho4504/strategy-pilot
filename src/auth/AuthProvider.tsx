import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { useQueryClient } from "@tanstack/react-query";
import { isSupabaseConfigured, supabase } from "@/integrations/supabase/client";
import { setAccessTokenProvider, setUnauthorizedHandler } from "@/services/apiClient";

type AuthStatus = "loading" | "authenticated" | "unauthenticated";

interface AuthContextValue {
  status: AuthStatus;
  session: Session | null;
  email: string | null;
  configured: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [session, setSession] = useState<Session | null>(null);
  const [status, setStatus] = useState<AuthStatus>(isSupabaseConfigured ? "loading" : "unauthenticated");

  const clearSession = useCallback(() => {
    setSession(null);
    setStatus("unauthenticated");
    queryClient.clear();
  }, [queryClient]);

  useEffect(() => {
    setAccessTokenProvider(() => session?.access_token ?? null);
  }, [session]);

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
      setStatus(data.session ? "authenticated" : "unauthenticated");
    });

    const { data: listener } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession);
      setStatus(nextSession ? "authenticated" : "unauthenticated");
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
    signOut,
  }), [session, signIn, signOut, status]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
