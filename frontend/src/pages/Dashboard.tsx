import { adaptersApi, configurationsApi, documentsApi, simulationsApi } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";
import { Activity, FileText, FlaskConical, Plug, Settings } from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const activityData = [
  { name: "Mon", documents: 12, simulations: 4 },
  { name: "Tue", documents: 19, simulations: 7 },
  { name: "Wed", documents: 8, simulations: 3 },
  { name: "Thu", documents: 24, simulations: 9 },
  { name: "Fri", documents: 16, simulations: 6 },
  { name: "Sat", documents: 5, simulations: 2 },
  { name: "Sun", documents: 3, simulations: 1 },
];

const statusData = [
  { name: "Active", value: 8, color: "#10b981" },
  { name: "Inactive", value: 3, color: "#6b7280" },
  { name: "Error", value: 1, color: "#ef4444" },
];

const throughputData = [
  { hour: "00:00", records: 1200 },
  { hour: "04:00", records: 800 },
  { hour: "08:00", records: 2400 },
  { hour: "12:00", records: 3200 },
  { hour: "16:00", records: 2800 },
  { hour: "20:00", records: 1800 },
];

interface MetricCardProps {
  title: string;
  value: string | number;
  subtitle: string;
  icon: React.ComponentType<{ className?: string }>;
  color: string;
}

function MetricCard({ title, value, subtitle, icon: Icon, color }: MetricCardProps) {
  return (
    <div className="card-hover p-6">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-gray-400">{title}</p>
          <p className="mt-2 text-3xl font-bold text-white">{value}</p>
          <p className="mt-1 text-xs text-gray-500">{subtitle}</p>
        </div>
        <div className={`rounded-lg p-2.5 ${color}`}>
          <Icon className="h-5 w-5" />
        </div>
      </div>
    </div>
  );
}

function MetricCardSkeleton() {
  return (
    <div className="card-hover p-6 animate-pulse">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="h-4 w-28 rounded bg-gray-700" />
          <div className="mt-3 h-8 w-16 rounded bg-gray-700" />
          <div className="mt-2 h-3 w-36 rounded bg-gray-700" />
        </div>
        <div className="h-10 w-10 rounded-lg bg-gray-700" />
      </div>
    </div>
  );
}

function SampleBadge() {
  return (
    <span className="inline-flex items-center rounded-md border border-gray-600/40 bg-gray-700/40 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-gray-500">
      Sample data
    </span>
  );
}

export default function Dashboard() {
  const adapters = useQuery({ queryKey: ["adapters"], queryFn: adaptersApi.list });
  const documents = useQuery({ queryKey: ["documents"], queryFn: documentsApi.list });
  const configs = useQuery({ queryKey: ["configurations"], queryFn: configurationsApi.list });
  const sims = useQuery({ queryKey: ["simulations"], queryFn: simulationsApi.list });

  const isLoading =
    adapters.isLoading || documents.isLoading || configs.isLoading || sims.isLoading;
  const hasError = adapters.error || documents.error || configs.error || sims.error;

  const adapterCount = adapters.data?.length ?? 0;
  const docCount = documents.data?.length ?? 0;
  const configCount = configs.data?.length ?? 0;
  const simCount = sims.data?.length ?? 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Dashboard</h1>
        <p className="mt-1 text-sm text-gray-400">Integration platform overview and metrics</p>
      </div>

      {hasError && (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-4 text-sm text-amber-400">
          Backend unavailable. Showing sample data.
        </div>
      )}

      {/* Metric cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {isLoading ? (
          <>
            <MetricCardSkeleton />
            <MetricCardSkeleton />
            <MetricCardSkeleton />
            <MetricCardSkeleton />
          </>
        ) : (
          <>
            <MetricCard
              title="Active Adapters"
              value={adapterCount}
              subtitle="Integration connectors"
              icon={Plug}
              color="bg-indigo-500/10 text-indigo-400"
            />
            <MetricCard
              title="Documents"
              value={docCount}
              subtitle="Uploaded & processed"
              icon={FileText}
              color="bg-emerald-500/10 text-emerald-400"
            />
            <MetricCard
              title="Configurations"
              value={configCount}
              subtitle="Active configs"
              icon={Settings}
              color="bg-amber-500/10 text-amber-400"
            />
            <MetricCard
              title="Simulations"
              value={simCount}
              subtitle="Total runs"
              icon={FlaskConical}
              color="bg-purple-500/10 text-purple-400"
            />
          </>
        )}
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Activity chart */}
        <div className="card p-6 lg:col-span-2">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-semibold text-white">Weekly Activity</h3>
                <SampleBadge />
              </div>
              <p className="text-xs text-gray-400">Documents & simulations processed</p>
            </div>
            <Activity className="h-4 w-4 text-gray-500" />
          </div>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={activityData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis dataKey="name" stroke="#6b7280" fontSize={12} />
                <YAxis stroke="#6b7280" fontSize={12} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#111827",
                    border: "1px solid #374151",
                    borderRadius: "8px",
                    fontSize: "12px",
                  }}
                />
                <Bar dataKey="documents" fill="#6366f1" radius={[4, 4, 0, 0]} />
                <Bar dataKey="simulations" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Status pie */}
        <div className="card p-6">
          <div className="mb-4">
            <div className="flex items-center gap-2">
              <h3 className="font-semibold text-white">Adapter Status</h3>
              <SampleBadge />
            </div>
            <p className="text-xs text-gray-400">Current distribution</p>
          </div>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={statusData}
                  cx="50%"
                  cy="50%"
                  innerRadius={50}
                  outerRadius={75}
                  paddingAngle={4}
                  dataKey="value"
                >
                  {statusData.map((entry) => (
                    <Cell key={entry.name} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#111827",
                    border: "1px solid #374151",
                    borderRadius: "8px",
                    fontSize: "12px",
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-2 space-y-2">
            {statusData.map((s) => (
              <div key={s.name} className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <div className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: s.color }} />
                  <span className="text-gray-400">{s.name}</span>
                </div>
                <span className="font-medium text-gray-300">{s.value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Throughput chart */}
      <div className="card p-6">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-semibold text-white">Data Throughput</h3>
              <SampleBadge />
            </div>
            <p className="text-xs text-gray-400">Records processed per hour (today)</p>
          </div>
        </div>
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={throughputData}>
              <defs>
                <linearGradient id="throughputGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey="hour" stroke="#6b7280" fontSize={12} />
              <YAxis stroke="#6b7280" fontSize={12} />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#111827",
                  border: "1px solid #374151",
                  borderRadius: "8px",
                  fontSize: "12px",
                }}
              />
              <Area
                type="monotone"
                dataKey="records"
                stroke="#6366f1"
                strokeWidth={2}
                fill="url(#throughputGrad)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
