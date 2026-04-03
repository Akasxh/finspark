import { adaptersApi } from "@/lib/api";
import type { Adapter } from "@/types";
import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Clock, ExternalLink, Plug, RefreshCw } from "lucide-react";

const fallbackAdapters: Adapter[] = [
  {
    id: "1",
    name: "SAP ERP",
    type: "erp",
    description: "SAP S/4HANA integration via RFC/BAPI",
    status: "active",
    version: "2.1.0",
    last_sync: "2026-03-27T10:30:00Z",
  },
  {
    id: "2",
    name: "Salesforce CRM",
    type: "crm",
    description: "Salesforce REST API connector",
    status: "active",
    version: "3.0.1",
    last_sync: "2026-03-27T10:25:00Z",
  },
  {
    id: "3",
    name: "Bloomberg Terminal",
    type: "market_data",
    description: "Bloomberg B-PIPE real-time market data",
    status: "active",
    version: "1.4.2",
    last_sync: "2026-03-27T10:31:00Z",
  },
  {
    id: "4",
    name: "SWIFT Alliance",
    type: "payments",
    description: "SWIFT messaging gateway (MT/MX)",
    status: "active",
    version: "2.0.0",
    last_sync: "2026-03-27T10:28:00Z",
  },
  {
    id: "5",
    name: "FIX Engine",
    type: "trading",
    description: "FIX 4.4 order routing engine",
    status: "inactive",
    version: "1.2.0",
  },
  {
    id: "6",
    name: "Reuters Eikon",
    type: "market_data",
    description: "Refinitiv Eikon data feed connector",
    status: "error",
    version: "1.1.3",
    last_sync: "2026-03-26T18:00:00Z",
  },
  {
    id: "7",
    name: "Oracle Financials",
    type: "erp",
    description: "Oracle Cloud ERP REST integration",
    status: "active",
    version: "1.8.0",
    last_sync: "2026-03-27T09:45:00Z",
  },
  {
    id: "8",
    name: "Murex MX.3",
    type: "trading",
    description: "Murex trading & risk platform connector",
    status: "active",
    version: "2.3.0",
    last_sync: "2026-03-27T10:15:00Z",
  },
];

const statusConfig: Record<string, { label: string; cls: string }> = {
  active: { label: "Active", cls: "badge-green" },
  inactive: { label: "Inactive", cls: "badge-gray" },
  error: { label: "Error", cls: "badge-red" },
};

const typeColors: Record<string, string> = {
  erp: "text-blue-400 bg-blue-500/10",
  crm: "text-purple-400 bg-purple-500/10",
  market_data: "text-emerald-400 bg-emerald-500/10",
  payments: "text-amber-400 bg-amber-500/10",
  trading: "text-rose-400 bg-rose-500/10",
  bureau: "text-blue-400 bg-blue-500/10",
  kyc: "text-teal-400 bg-teal-500/10",
  gst: "text-orange-400 bg-orange-500/10",
  payment: "text-amber-400 bg-amber-500/10",
  fraud: "text-red-400 bg-red-500/10",
  notification: "text-indigo-400 bg-indigo-500/10",
  open_banking: "text-cyan-400 bg-cyan-500/10",
};

function formatTimeAgo(dateStr?: string): string {
  if (!dateStr) return "Never";
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export default function Adapters() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["adapters"],
    queryFn: adaptersApi.list,
  });

  const rawAdapters = data ?? fallbackAdapters;
  const adapters = rawAdapters.map((a) => ({
    ...a,
    type: a.type ?? a.category ?? "unknown",
    status: a.status ?? (a.is_active ? "active" : ("inactive" as const)),
    version: a.version ?? a.versions?.[0]?.version ?? "-",
    description: a.description ?? "",
  }));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Adapters</h1>
          <p className="mt-1 text-sm text-gray-400">Integration connectors and data sources</p>
        </div>
        <button type="button" className="btn-secondary" onClick={() => refetch()}>
          <RefreshCw className={clsx("h-4 w-4", isLoading && "animate-spin")} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-4 text-sm text-amber-400">
          Backend unavailable. Showing sample data.
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {adapters.map((adapter) => {
          const st = statusConfig[adapter.status];
          const typeColor = typeColors[adapter.type] ?? "text-gray-400 bg-gray-500/10";

          return (
            <div key={adapter.id} className="card-hover group p-5">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div className={clsx("rounded-lg p-2", typeColor)}>
                    <Plug className="h-4 w-4" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-white group-hover:text-indigo-300 transition-colors">
                      {adapter.name}
                    </h3>
                    <span
                      className={clsx(
                        "mt-0.5 inline-block rounded-md px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide",
                        typeColor
                      )}
                    >
                      {adapter.type.replace("_", " ")}
                    </span>
                  </div>
                </div>
                <span className={st.cls}>{st.label}</span>
              </div>
              <p className="mt-3 text-sm leading-relaxed text-gray-400">{adapter.description}</p>
              <div className="mt-4 flex items-center justify-between border-t border-gray-800 pt-3">
                <div className="flex items-center gap-1.5 text-xs text-gray-500">
                  <Clock className="h-3 w-3" />
                  {formatTimeAgo(adapter.last_sync)}
                </div>
                <div className="flex items-center gap-3 text-xs text-gray-500">
                  <span>v{adapter.version}</span>
                  <ExternalLink className="h-3 w-3 opacity-0 transition-opacity group-hover:opacity-100 text-indigo-400 cursor-pointer" />
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
