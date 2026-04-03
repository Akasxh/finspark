import { configurationsApi, simulationsApi } from "@/lib/api";
import type { Configuration, Simulation } from "@/types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  Clock,
  FlaskConical,
  Loader2,
  Play,
  XCircle,
  Zap,
} from "lucide-react";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const fallbackSims: Simulation[] = [
  {
    id: "1",
    name: "Q1 Trade Settlement Test",
    configuration_id: "1",
    status: "completed",
    created_at: "2026-03-27T09:00:00Z",
    completed_at: "2026-03-27T09:02:30Z",
    results: {
      success_rate: 99.2,
      total_records: 5000,
      processed_records: 4960,
      errors: 40,
      warnings: 12,
      duration_ms: 150000,
    },
  },
  {
    id: "2",
    name: "Bloomberg Feed Stress Test",
    configuration_id: "2",
    status: "completed",
    created_at: "2026-03-26T14:00:00Z",
    completed_at: "2026-03-26T14:05:00Z",
    results: {
      success_rate: 97.8,
      total_records: 50000,
      processed_records: 48900,
      errors: 1100,
      warnings: 230,
      duration_ms: 300000,
    },
  },
  {
    id: "3",
    name: "SWIFT MT103 Validation",
    configuration_id: "3",
    status: "running",
    created_at: "2026-03-27T10:30:00Z",
  },
  {
    id: "4",
    name: "CRM Sync Dry Run",
    configuration_id: "5",
    status: "completed",
    created_at: "2026-03-25T08:00:00Z",
    completed_at: "2026-03-25T08:01:00Z",
    results: {
      success_rate: 100,
      total_records: 1200,
      processed_records: 1200,
      errors: 0,
      warnings: 3,
      duration_ms: 60000,
    },
  },
  {
    id: "5",
    name: "FIX Order Routing Fail Test",
    configuration_id: "4",
    status: "failed",
    created_at: "2026-03-24T16:00:00Z",
    completed_at: "2026-03-24T16:00:30Z",
    results: {
      success_rate: 23.5,
      total_records: 200,
      processed_records: 47,
      errors: 153,
      warnings: 45,
      duration_ms: 30000,
    },
  },
];

const fallbackConfigs: Configuration[] = [
  {
    id: "1",
    name: "SAP Trade Settlement",
    adapter_type: "erp",
    status: "active",
    created_at: "",
    updated_at: "",
    parameters: {},
  },
  {
    id: "2",
    name: "Bloomberg Real-Time Feed",
    adapter_type: "market_data",
    status: "active",
    created_at: "",
    updated_at: "",
    parameters: {},
  },
];

const statusConfig: Record<string, { label: string; icon: typeof Clock; cls: string }> = {
  pending: { label: "Pending", icon: Clock, cls: "badge-yellow" },
  queued: { label: "Queued", icon: Clock, cls: "badge-yellow" },
  running: { label: "Running", icon: Loader2, cls: "badge-blue" },
  completed: { label: "Completed", icon: CheckCircle2, cls: "badge-green" },
  passed: { label: "Passed", icon: CheckCircle2, cls: "badge-green" },
  failed: { label: "Failed", icon: XCircle, cls: "badge-red" },
  cancelled: { label: "Cancelled", icon: XCircle, cls: "badge-gray" },
  timed_out: { label: "Timed Out", icon: AlertTriangle, cls: "badge-red" },
};

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
}

export default function Simulations() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [simName, setSimName] = useState("");
  const [configId, setConfigId] = useState("");

  const { data: simData, error: simError } = useQuery({
    queryKey: ["simulations"],
    queryFn: simulationsApi.list,
  });

  const { data: configData } = useQuery({
    queryKey: ["configurations"],
    queryFn: configurationsApi.list,
  });

  const runMutation = useMutation({
    mutationFn: simulationsApi.run,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["simulations"] });
      setShowForm(false);
      setSimName("");
      setConfigId("");
    },
  });

  const simulations = simData ?? fallbackSims;
  const configs = configData ?? fallbackConfigs;

  const completedSims = simulations.filter((s) => s.results);
  const chartData = completedSims.map((s) => {
    const label = s.name ?? s.scenario ?? "Simulation";
    return {
      name: label.length > 20 ? `${label.slice(0, 20)}...` : label,
      success: s.results?.success_rate ?? 0,
      errors: s.results?.errors ?? 0,
    };
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Simulations</h1>
          <p className="mt-1 text-sm text-gray-400">Run and monitor integration simulations</p>
        </div>
        <button type="button" className="btn-primary" onClick={() => setShowForm(!showForm)}>
          {showForm ? (
            "Cancel"
          ) : (
            <>
              <Play className="h-4 w-4" /> Run Simulation
            </>
          )}
        </button>
      </div>

      {simError && (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-4 text-sm text-amber-400">
          Backend unavailable. Showing sample data.
        </div>
      )}

      {/* Run form */}
      {showForm && (
        <div className="card p-6">
          <div className="mb-4 flex items-center gap-2">
            <Zap className="h-4 w-4 text-indigo-400" />
            <h3 className="font-semibold text-white">New Simulation</h3>
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (simName.trim() && configId) {
                runMutation.mutate({
                  name: simName.trim(),
                  configuration_id: configId,
                });
              }
            }}
            className="grid gap-4 sm:grid-cols-3"
          >
            <div>
              <label htmlFor="sim-name" className="mb-1.5 block text-xs font-medium text-gray-400">
                Simulation Name
              </label>
              <input
                id="sim-name"
                type="text"
                value={simName}
                onChange={(e) => setSimName(e.target.value)}
                placeholder="e.g., Q1 Trade Test"
                className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white placeholder:text-gray-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label
                htmlFor="sim-config"
                className="mb-1.5 block text-xs font-medium text-gray-400"
              >
                Configuration
              </label>
              <select
                id="sim-config"
                value={configId}
                onChange={(e) => setConfigId(e.target.value)}
                className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              >
                <option value="">Select configuration...</option>
                {configs.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex items-end">
              <button
                type="submit"
                className="btn-primary w-full justify-center"
                disabled={!simName.trim() || !configId || runMutation.isPending}
              >
                <Play className="h-4 w-4" />
                {runMutation.isPending ? "Starting..." : "Run"}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Results chart */}
      {chartData.length > 0 && (
        <div className="card p-6">
          <div className="mb-4 flex items-center gap-2">
            <BarChart3 className="h-4 w-4 text-gray-400" />
            <h3 className="font-semibold text-white">Success Rates</h3>
          </div>
          <div className="h-52">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis type="number" domain={[0, 100]} stroke="#6b7280" fontSize={12} />
                <YAxis type="category" dataKey="name" stroke="#6b7280" fontSize={11} width={160} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#111827",
                    border: "1px solid #374151",
                    borderRadius: "8px",
                    fontSize: "12px",
                  }}
                />
                <Bar dataKey="success" fill="#6366f1" radius={[0, 4, 4, 0]} name="Success %" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Simulation list */}
      <div className="space-y-3">
        {simulations.map((sim) => {
          const st = statusConfig[sim.status] ?? statusConfig.pending;
          const StatusIcon = st.icon;

          return (
            <div key={sim.id} className="card p-5">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div className="rounded-lg bg-gray-800 p-2">
                    <FlaskConical className="h-4 w-4 text-gray-400" />
                  </div>
                  <div>
                    <h3 className="font-medium text-white">
                      {sim.name ?? sim.scenario ?? "Simulation"}
                    </h3>
                    <p className="mt-0.5 text-xs text-gray-500">
                      {new Date(sim.created_at ?? sim.queued_at ?? "").toLocaleString()}
                    </p>
                  </div>
                </div>
                <span className={st.cls}>
                  <StatusIcon
                    className={clsx("mr-1 h-3 w-3", sim.status === "running" && "animate-spin")}
                  />
                  {st.label}
                </span>
              </div>

              {sim.results && (
                <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-5">
                  <div className="rounded-lg bg-gray-800/50 p-3">
                    <p className="text-xs text-gray-500">Success Rate</p>
                    <p
                      className={clsx(
                        "mt-1 text-lg font-bold",
                        sim.results.success_rate >= 95
                          ? "text-emerald-400"
                          : sim.results.success_rate >= 80
                            ? "text-amber-400"
                            : "text-red-400"
                      )}
                    >
                      {sim.results.success_rate}%
                    </p>
                  </div>
                  <div className="rounded-lg bg-gray-800/50 p-3">
                    <p className="text-xs text-gray-500">Records</p>
                    <p className="mt-1 text-lg font-bold text-white">
                      {sim.results.processed_records.toLocaleString()}
                      <span className="text-xs font-normal text-gray-500">
                        /{sim.results.total_records.toLocaleString()}
                      </span>
                    </p>
                  </div>
                  <div className="rounded-lg bg-gray-800/50 p-3">
                    <p className="text-xs text-gray-500">Errors</p>
                    <p className="mt-1 text-lg font-bold text-red-400">{sim.results.errors}</p>
                  </div>
                  <div className="rounded-lg bg-gray-800/50 p-3">
                    <p className="text-xs text-gray-500">Warnings</p>
                    <p className="mt-1 flex items-center gap-1 text-lg font-bold text-amber-400">
                      <AlertTriangle className="h-3.5 w-3.5" />
                      {sim.results.warnings}
                    </p>
                  </div>
                  <div className="rounded-lg bg-gray-800/50 p-3">
                    <p className="text-xs text-gray-500">Duration</p>
                    <p className="mt-1 text-lg font-bold text-gray-300">
                      {formatDuration(sim.results.duration_ms)}
                    </p>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
