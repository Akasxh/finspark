import { auditApi } from "@/lib/api";
import type { AuditEntry } from "@/types";
import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import {
  AlertTriangle,
  CheckCircle2,
  Play,
  Plug,
  RefreshCw,
  Settings,
  Shield,
  Upload,
  User,
  XCircle,
} from "lucide-react";

const fallbackAudit: AuditEntry[] = [
  {
    id: "1",
    action: "document.upload",
    entity_type: "document",
    entity_id: "doc-001",
    user: "akash@finspark.io",
    timestamp: "2026-03-27T10:30:00Z",
    status: "success",
    details: { filename: "trade_report_q1.xlsx" },
  },
  {
    id: "2",
    action: "simulation.run",
    entity_type: "simulation",
    entity_id: "sim-001",
    user: "akash@finspark.io",
    timestamp: "2026-03-27T10:25:00Z",
    status: "success",
    details: { name: "Q1 Trade Settlement Test", duration_ms: 150000 },
  },
  {
    id: "3",
    action: "configuration.generate",
    entity_type: "configuration",
    entity_id: "cfg-003",
    user: "sarah@finspark.io",
    timestamp: "2026-03-27T10:15:00Z",
    status: "success",
    details: { name: "SWIFT MT103 Payments" },
  },
  {
    id: "4",
    action: "adapter.sync",
    entity_type: "adapter",
    entity_id: "adp-006",
    user: "system",
    timestamp: "2026-03-27T10:10:00Z",
    status: "failure",
    details: { adapter: "Reuters Eikon", error: "Connection timeout after 30s" },
  },
  {
    id: "5",
    action: "simulation.run",
    entity_type: "simulation",
    entity_id: "sim-005",
    user: "david@finspark.io",
    timestamp: "2026-03-27T09:45:00Z",
    status: "warning",
    details: { name: "FIX Order Routing Fail Test", success_rate: 23.5 },
  },
  {
    id: "6",
    action: "configuration.update",
    entity_type: "configuration",
    entity_id: "cfg-001",
    user: "akash@finspark.io",
    timestamp: "2026-03-27T09:30:00Z",
    status: "success",
    details: { field: "batch_size", old: 250, new: 500 },
  },
  {
    id: "7",
    action: "adapter.activate",
    entity_type: "adapter",
    entity_id: "adp-008",
    user: "sarah@finspark.io",
    timestamp: "2026-03-27T09:00:00Z",
    status: "success",
    details: { adapter: "Murex MX.3" },
  },
  {
    id: "8",
    action: "document.process",
    entity_type: "document",
    entity_id: "doc-003",
    user: "system",
    timestamp: "2026-03-27T08:45:00Z",
    status: "success",
    details: { filename: "swift_messages.xml", records_extracted: 342 },
  },
  {
    id: "9",
    action: "adapter.sync",
    entity_type: "adapter",
    entity_id: "adp-001",
    user: "system",
    timestamp: "2026-03-27T08:30:00Z",
    status: "success",
    details: { adapter: "SAP ERP", records_synced: 1250 },
  },
  {
    id: "10",
    action: "document.upload",
    entity_type: "document",
    entity_id: "doc-005",
    user: "david@finspark.io",
    timestamp: "2026-03-25T16:00:00Z",
    status: "failure",
    details: { filename: "risk_assessment.csv", error: "Invalid CSV structure" },
  },
];

const actionIcons: Record<string, React.ComponentType<{ className?: string }>> = {
  "document.upload": Upload,
  "document.process": RefreshCw,
  "simulation.run": Play,
  "configuration.generate": Settings,
  "configuration.update": Settings,
  "adapter.sync": RefreshCw,
  "adapter.activate": Plug,
};

const statusConfig = {
  success: { icon: CheckCircle2, cls: "text-emerald-400", bg: "bg-emerald-500/10" },
  failure: { icon: XCircle, cls: "text-red-400", bg: "bg-red-500/10" },
  warning: { icon: AlertTriangle, cls: "text-amber-400", bg: "bg-amber-500/10" },
} as const;

function formatTime(dateStr: string): string {
  const d = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMins = Math.floor(diffMs / 60000);

  if (diffMins < 1) return "Just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;

  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function Audit() {
  const { data, error } = useQuery({
    queryKey: ["audit"],
    queryFn: auditApi.list,
  });

  const entries = (data ?? fallbackAudit).map((e) => ({
    ...e,
    status: e.status ?? e.outcome ?? ("success" as const),
    timestamp: e.timestamp ?? e.created_at ?? new Date().toISOString(),
    entity_type: e.entity_type ?? e.resource_type ?? "",
    entity_id: e.entity_id ?? e.resource_id ?? "",
    user: e.user ?? e.actor ?? e.actor_email ?? "system",
  }));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Audit Log</h1>
        <p className="mt-1 text-sm text-gray-400">Activity timeline and compliance tracking</p>
      </div>

      {error && (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-4 text-sm text-amber-400">
          Backend unavailable. Showing sample data.
        </div>
      )}

      {/* Summary stats */}
      <div className="grid grid-cols-3 gap-4">
        <div className="card p-4 text-center">
          <p className="text-2xl font-bold text-emerald-400">
            {entries.filter((e) => e.status === "success").length}
          </p>
          <p className="text-xs text-gray-400">Successful</p>
        </div>
        <div className="card p-4 text-center">
          <p className="text-2xl font-bold text-amber-400">
            {entries.filter((e) => e.status === "warning").length}
          </p>
          <p className="text-xs text-gray-400">Warnings</p>
        </div>
        <div className="card p-4 text-center">
          <p className="text-2xl font-bold text-red-400">
            {entries.filter((e) => e.status === "failure").length}
          </p>
          <p className="text-xs text-gray-400">Failures</p>
        </div>
      </div>

      {/* Timeline */}
      <div className="card overflow-hidden">
        <div className="border-b border-gray-800 px-6 py-4">
          <div className="flex items-center gap-2">
            <Shield className="h-4 w-4 text-gray-400" />
            <h3 className="font-semibold text-white">Activity Timeline</h3>
          </div>
        </div>
        <div className="relative">
          {/* Timeline line */}
          <div className="absolute left-[39px] top-0 bottom-0 w-px bg-gray-800" />

          {entries.map((entry, i) => {
            const stKey = entry.status as keyof typeof statusConfig;
            const st = statusConfig[stKey] ?? statusConfig.success;
            const StatusIcon = st.icon;
            const ActionIcon = actionIcons[entry.action] ?? Shield;

            return (
              <div
                key={entry.id}
                className={clsx(
                  "relative flex gap-4 px-6 py-4 transition-colors hover:bg-gray-800/20",
                  i !== entries.length - 1 && "border-b border-gray-800/40"
                )}
              >
                {/* Timeline dot */}
                <div
                  className={clsx(
                    "relative z-10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
                    st.bg
                  )}
                >
                  <ActionIcon className={clsx("h-3.5 w-3.5", st.cls)} />
                </div>

                {/* Content */}
                <div className="min-w-0 flex-1">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-white text-sm">
                          {entry.action.replace(".", " ").replace(/\b\w/g, (c) => c.toUpperCase())}
                        </span>
                        <StatusIcon className={clsx("h-3.5 w-3.5", st.cls)} />
                      </div>
                      <div className="mt-1 flex items-center gap-2 text-xs text-gray-500">
                        <User className="h-3 w-3" />
                        <span>{entry.user}</span>
                        <span>&middot;</span>
                        <span>
                          {entry.entity_type}/{entry.entity_id}
                        </span>
                      </div>
                    </div>
                    <span className="shrink-0 text-xs text-gray-500">
                      {formatTime(entry.timestamp)}
                    </span>
                  </div>

                  {entry.details && Object.keys(entry.details).length > 0 && (
                    <div className="mt-2 rounded-lg bg-gray-950/60 px-3 py-2 text-xs text-gray-400">
                      {Object.entries(entry.details).map(([k, v]) => (
                        <span key={k} className="mr-3">
                          <span className="text-gray-500">{k}:</span>{" "}
                          <span className="text-gray-300">{String(v)}</span>
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
