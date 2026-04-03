import { configurationsApi } from "@/lib/api";
import type { Configuration } from "@/types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  Archive,
  CheckCircle2,
  ChevronDown,
  Clock,
  Copy,
  Plus,
  Settings,
  Sparkles,
} from "lucide-react";
import { useState } from "react";

const adapterTypes = ["erp", "crm", "market_data", "payments", "trading"];

const statusConfig = {
  draft: { label: "Draft", cls: "badge-yellow" },
  active: { label: "Active", cls: "badge-green" },
  archived: { label: "Archived", cls: "badge-gray" },
} as const;

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function SkeletonRow() {
  return (
    <div className="card overflow-hidden animate-pulse">
      <div className="flex items-center gap-4 px-6 py-4">
        <div className="rounded-lg bg-gray-800 p-2">
          <div className="h-4 w-4 rounded bg-gray-700" />
        </div>
        <div className="flex-1 space-y-2">
          <div className="h-4 w-48 rounded bg-gray-700" />
          <div className="h-3 w-32 rounded bg-gray-800" />
        </div>
        <div className="h-4 w-4 rounded bg-gray-700" />
      </div>
    </div>
  );
}

export default function Configurations() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [adapterType, setAdapterType] = useState(adapterTypes[0]);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [generateSuccess, setGenerateSuccess] = useState(false);

  const { data, isLoading, error } = useQuery({
    queryKey: ["configurations"],
    queryFn: configurationsApi.list,
  });

  const generateMutation = useMutation({
    mutationFn: configurationsApi.generate,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["configurations"] });
      setShowForm(false);
      setName("");
      setGenerateError(null);
      setGenerateSuccess(true);
      setTimeout(() => setGenerateSuccess(false), 4000);
    },
    onError: (err: Error) => {
      setGenerateError(err.message ?? "Failed to generate configuration.");
    },
  });

  const configs: Configuration[] = data ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Configurations</h1>
          <p className="mt-1 text-sm text-gray-400">
            Manage and generate integration configurations
          </p>
        </div>
        <button
          type="button"
          className="btn-primary"
          onClick={() => {
            setShowForm(!showForm);
            setGenerateError(null);
          }}
        >
          {showForm ? (
            "Cancel"
          ) : (
            <>
              <Plus className="h-4 w-4" /> Generate Config
            </>
          )}
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-4 text-sm text-amber-400">
          Failed to load configurations. Check your connection and try again.
        </div>
      )}

      {generateSuccess && (
        <div className="flex items-center gap-2 rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-4 text-sm text-emerald-400">
          <CheckCircle2 className="h-4 w-4 shrink-0" />
          Configuration generated successfully.
        </div>
      )}

      {/* Generate form */}
      {showForm && (
        <div className="card p-6">
          <div className="mb-4 flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-indigo-400" />
            <h3 className="font-semibold text-white">Generate New Configuration</h3>
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (name.trim()) {
                setGenerateError(null);
                generateMutation.mutate({ name: name.trim(), adapter_type: adapterType });
              }
            }}
            className="grid gap-4 sm:grid-cols-3"
          >
            <div>
              <label htmlFor="cfg-name" className="mb-1.5 block text-xs font-medium text-gray-400">
                Configuration Name
              </label>
              <input
                id="cfg-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g., SAP Trade Settlement"
                className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white placeholder:text-gray-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label htmlFor="cfg-type" className="mb-1.5 block text-xs font-medium text-gray-400">
                Adapter Type
              </label>
              <select
                id="cfg-type"
                value={adapterType}
                onChange={(e) => setAdapterType(e.target.value)}
                className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              >
                {adapterTypes.map((t) => (
                  <option key={t} value={t}>
                    {t.replaceAll("_", " ").toUpperCase()}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex items-end">
              <button
                type="submit"
                className="btn-primary w-full justify-center"
                disabled={!name.trim() || generateMutation.isPending}
              >
                <Sparkles className="h-4 w-4" />
                {generateMutation.isPending ? "Generating..." : "Generate"}
              </button>
            </div>
          </form>
          {generateError && (
            <div className="mt-3 rounded-lg border border-red-500/20 bg-red-500/5 p-3 text-sm text-red-400">
              {generateError}
            </div>
          )}
        </div>
      )}

      {/* Config list */}
      <div className="space-y-3">
        {isLoading ? (
          <>
            <SkeletonRow />
            <SkeletonRow />
            <SkeletonRow />
          </>
        ) : configs.length === 0 && !error ? (
          <div className="card flex flex-col items-center justify-center py-16 text-center">
            <Settings className="mb-3 h-10 w-10 text-gray-600" />
            <p className="text-sm font-medium text-gray-400">No configurations yet</p>
            <p className="mt-1 text-xs text-gray-600">
              Click "Generate Config" to create your first integration configuration.
            </p>
          </div>
        ) : (
          configs.map((cfg) => {
            const st = statusConfig[cfg.status];
            const isExpanded = expandedId === cfg.id;

            return (
              <div key={cfg.id} className="card overflow-hidden">
                <button
                  type="button"
                  className="flex w-full items-center gap-4 px-6 py-4 text-left transition-colors hover:bg-gray-800/30"
                  onClick={() => setExpandedId(isExpanded ? null : cfg.id)}
                >
                  <div className="rounded-lg bg-gray-800 p-2">
                    <Settings className="h-4 w-4 text-gray-400" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <h3 className="font-medium text-white">{cfg.name}</h3>
                      <span className={st.cls}>{st.label}</span>
                    </div>
                    <div className="mt-1 flex items-center gap-3 text-xs text-gray-500">
                      <span className="uppercase tracking-wide">
                        {cfg.adapter_type.replaceAll("_", " ")}
                      </span>
                      <span>&middot;</span>
                      <span className="flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        Updated {formatDate(cfg.updated_at)}
                      </span>
                    </div>
                  </div>
                  <ChevronDown
                    className={clsx(
                      "h-4 w-4 text-gray-500 transition-transform",
                      isExpanded && "rotate-180"
                    )}
                  />
                </button>
                {isExpanded && (
                  <div className="border-t border-gray-800 bg-gray-900/40 px-6 py-4">
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-xs font-medium text-gray-400">Parameters</span>
                      <div className="flex gap-2">
                        <button
                          type="button"
                          className="btn-secondary text-xs py-1 px-2 cursor-not-allowed opacity-50"
                          disabled
                          title="Coming soon"
                        >
                          <Copy className="h-3 w-3" /> Clone
                        </button>
                        <button
                          type="button"
                          className="btn-secondary text-xs py-1 px-2 cursor-not-allowed opacity-50"
                          disabled
                          title="Coming soon"
                        >
                          <Archive className="h-3 w-3" /> Archive
                        </button>
                      </div>
                    </div>
                    <pre className="rounded-lg bg-gray-950 p-4 text-xs text-gray-300 overflow-x-auto">
                      {JSON.stringify(cfg.parameters, null, 2)}
                    </pre>
                    <div className="mt-3 text-xs text-gray-500">
                      Created {formatDate(cfg.created_at)}
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
