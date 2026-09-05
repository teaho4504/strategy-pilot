import { Component, lazy, ReactNode, Suspense } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "@/auth/AuthProvider";
import { LoginScreen } from "@/auth/LoginScreen";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AppShell } from "@/components/layout/AppShell";

const Home = lazy(() => import("./pages/Home"));
const Quotes = lazy(() => import("./pages/Quotes"));
const Strategies = lazy(() => import("./pages/Strategies"));
const Analytics = lazy(() => import("./pages/Analytics"));
const AgentOperations = lazy(() => import("./pages/AgentOperations"));
const Settings = lazy(() => import("./pages/Settings"));
const NotFound = lazy(() => import("./pages/NotFound"));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      gcTime: 5 * 60 * 1000,
      refetchOnMount: false,
      refetchOnReconnect: false,
      refetchOnWindowFocus: false,
      retry: false,
      staleTime: 10 * 1000,
    },
  },
});

// Force dark theme for the prototype
if (typeof document !== "undefined") {
  document.documentElement.classList.add("dark");
}

function AuthenticatedApp() {
  const { status } = useAuth();

  if (status === "loading") {
    return (
      <main className="grid min-h-screen place-items-center bg-background px-4 text-sm text-muted-foreground">
        키움 read-only 세션 확인 중
      </main>
    );
  }

  if (status !== "authenticated") {
    return <LoginScreen />;
  }

  return (
    <BrowserRouter>
      <RoutedAppShell />
    </BrowserRouter>
  );
}

function RoutedAppShell() {
  const location = useLocation();

  return (
    <AppShell>
      <RouteErrorBoundary resetKey={location.pathname}>
        <Suspense fallback={<PageLoading />}>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/quotes" element={<Quotes />} />
            <Route path="/strategies" element={<Strategies />} />
            <Route path="/orders" element={<Navigate to="/strategies" replace />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/agents" element={<AgentOperations />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Suspense>
      </RouteErrorBoundary>
    </AppShell>
  );
}

function PageLoading() {
  return (
    <main className="grid min-h-[60vh] place-items-center px-4 text-sm text-muted-foreground">
      화면을 불러오는 중
    </main>
  );
}

class RouteErrorBoundary extends Component<{ children: ReactNode; resetKey: string }, { hasError: boolean }> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: unknown) {
    console.error("Route render failed", error);
  }

  componentDidUpdate(prevProps: { resetKey: string }) {
    if (this.state.hasError && prevProps.resetKey !== this.props.resetKey) {
      this.setState({ hasError: false });
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <main className="space-y-3 p-4">
          <section className="card-base">
            <h1 className="text-lg font-semibold">화면을 불러오지 못했습니다</h1>
            <p className="mt-2 text-sm text-muted-foreground">새로고침 후 다시 시도하세요. 같은 문제가 반복되면 해당 탭 이름을 알려주세요.</p>
            <button
              type="button"
              onClick={() => window.location.assign("/")}
              className="mt-4 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground"
            >
              홈으로 이동
            </button>
          </section>
        </main>
      );
    }
    return this.props.children;
  }
}

const App = () => (
  <QueryClientProvider client={queryClient}>
    <AuthProvider>
      <TooltipProvider>
        <Toaster />
        <Sonner theme="dark" position="top-center" />
        <AuthenticatedApp />
      </TooltipProvider>
    </AuthProvider>
  </QueryClientProvider>
);

export default App;
