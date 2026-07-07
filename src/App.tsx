import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "@/auth/AuthProvider";
import { LoginScreen } from "@/auth/LoginScreen";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AppShell } from "@/components/layout/AppShell";
import Home from "./pages/Home";
import Strategies from "./pages/Strategies";
import StrategyBuilder from "./pages/StrategyBuilder";
import Orders from "./pages/Orders";
import Analytics from "./pages/Analytics";
import Settings from "./pages/Settings";
import NotFound from "./pages/NotFound";

const queryClient = new QueryClient();

// Force dark theme for the prototype
if (typeof document !== "undefined") {
  document.documentElement.classList.add("dark");
}

function AuthenticatedApp() {
  const { status } = useAuth();

  if (status === "loading") {
    return (
      <main className="grid min-h-screen place-items-center bg-background px-4 text-sm text-muted-foreground">
        Supabase session 확인 중
      </main>
    );
  }

  if (status !== "authenticated") {
    return <LoginScreen />;
  }

  return (
    <BrowserRouter>
      <AppShell>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/strategies" element={<Strategies />} />
          <Route path="/strategies/builder" element={<StrategyBuilder />} />
          <Route path="/orders" element={<Orders />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </AppShell>
    </BrowserRouter>
  );
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
