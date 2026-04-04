import ErrorBoundary from "@/components/ErrorBoundary";
import Layout from "@/components/Layout";
import NotFound from "@/components/NotFound";
import PageErrorBoundary from "@/components/PageErrorBoundary";
import { ToastProvider } from "@/components/Toast";
import Adapters from "@/pages/Adapters";
import Audit from "@/pages/Audit";
import Configurations from "@/pages/Configurations";
import Documents from "@/pages/Documents";
import Search from "@/pages/Search";
import Simulations from "@/pages/Simulations";
import Webhooks from "@/pages/Webhooks";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Suspense, lazy } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";

const Dashboard = lazy(() => import("@/pages/Dashboard"));

function Loading() {
  return (
    <div className="flex flex-1 items-center justify-center p-8">
      <p style={{ color: "var(--color-text-secondary)" }}>Loading...</p>
    </div>
  );
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
  },
});

export default function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <BrowserRouter>
            <Routes>
              <Route element={<Layout />}>
                <Route path="/" element={<PageErrorBoundary><Suspense fallback={<Loading />}><Dashboard /></Suspense></PageErrorBoundary>} />
                <Route path="/adapters" element={<PageErrorBoundary><Adapters /></PageErrorBoundary>} />
                <Route path="/documents" element={<PageErrorBoundary><Documents /></PageErrorBoundary>} />
                <Route path="/configurations" element={<PageErrorBoundary><Configurations /></PageErrorBoundary>} />
                <Route path="/simulations" element={<PageErrorBoundary><Simulations /></PageErrorBoundary>} />
                <Route path="/audit" element={<PageErrorBoundary><Audit /></PageErrorBoundary>} />
                <Route path="/search" element={<PageErrorBoundary><Search /></PageErrorBoundary>} />
                <Route path="/webhooks" element={<PageErrorBoundary><Webhooks /></PageErrorBoundary>} />
              </Route>
              <Route path="*" element={<NotFound />} />
            </Routes>
          </BrowserRouter>
        </ToastProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
