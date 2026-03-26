import { BrowserRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Layout from "@/components/Layout";
import Dashboard from "@/pages/Dashboard";
import Adapters from "@/pages/Adapters";
import Documents from "@/pages/Documents";
import Configurations from "@/pages/Configurations";
import Simulations from "@/pages/Simulations";
import Audit from "@/pages/Audit";

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
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/adapters" element={<Adapters />} />
            <Route path="/documents" element={<Documents />} />
            <Route path="/configurations" element={<Configurations />} />
            <Route path="/simulations" element={<Simulations />} />
            <Route path="/audit" element={<Audit />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
