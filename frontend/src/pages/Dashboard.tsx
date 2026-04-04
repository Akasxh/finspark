import { adaptersApi, analyticsApi, configurationsApi, documentsApi } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  FileText,
  FlaskConical,
  Plug,
  Settings,
  TrendingUp,
} from "lucide-react";
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

const SAMPLE_ACTIVITY_DATA = [
  { name: "Mon", documents: 12, simulations: 4 },
  { name: "Tue", documents: 19, simulations: 7 },
  { name: "Wed", documents: 8, simulations: 3 },
  { name: "Thu", documents: 24, simulations: 9 },
  { name: "Fri", documents: 16, simulations: 6 },
  { name: "Sat", documents: 5, simulations: 2 },
  { name: "Sun", documents: 3, simulations: 1 },
];

const SAMPLE_THROUGHPUT_DATA = [
  { hour: "00:00", records: 1200 },
  { hour: "04:00", records: 800 },
  { hour: "08:00", records: 2400 },
  { hour: "12:00", records: 3200 },
  { hour: "16:00", records: 2800 },
  { hour: "20:00", records: 1800 },
];

const STATUS_COLORS: Record<string, string> = {
  Active: "#10b981",
  Inactive: "#6b7280",
  Error: "#ef4444",
};

interface MetricCardProps {
  title: string;
  value: string | number;
  subtitle: string;
  icon: React.ComponentType<{ className?: string }>;
  trend?: string;
  color: string;
}

function MetricCard({ title, value, subtitle, icon: Icon, trend, color }: MetricCardProps) {
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
      {trend && (
        <div className="mt-3 flex items-center gap-1 text-xs text-emerald-400">
          <TrendingUp className="h-3 w-3" />
          {trend}
        </div>
      )}
    </div>
  );
}

function formatProcessed(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k processed` : `${n} processed`;
}

function resolveChartSeries<T>(
  raw: T[] | undefined,
  fallback: T[]
): { data: T[]; isSample: boolean } {
  const hasData = raw && raw.length > 0;
  return { data: hasData ? raw : fallback, isSample: !hasData };
}

function buildAdapterPieData(adapterList: Array<{ is_active: boolean; status?: string }>) {
  const counts: Record<string, number> = { Active: 0, Inactive: 0, Error: 0 };
  for (const a of adapterList) {
    if (a.is_active) counts.Active++;
    else if (a.status === "error") counts.Error++;
    else counts.Inactive++;
  }
  return Object.entries(counts)
    .filter(([, v]) => v > 0)
    .map(([name, value]) => ({ name, value, color: STATUS_COLORS[name] ?? "#6b7280" }));
}

const FALLBACK_PIE = [
  { name: "Active", value: 8, color: STATUS_COLORS.Active },
  { name: "Inactive", value: 3, color: STATUS_COLORS.Inactive },
  { name: "Error", value: 1, color: STATUS_COLORS.Error },
];

export default function Dashboard() {
  const adapters = useQuery({ queryKey: ["adapters"], queryFn: () => adaptersApi.list() });
  const documents = useQuery({ queryKey: ["documents"], queryFn: () => documentsApi.list() });
  const configs = useQuery({
    queryKey: ["configurations"],
    queryFn: () => configurationsApi.list(),
  });
  const analytics = useQuery({
    queryKey: ["analytics", "dashboard"],
    queryFn: () => analyticsApi.dashboard(),
    retry: false,
  });

  const adapterCount = adapters.data?.data?.total ?? 0;
  const docCount = documents.data?.data?.length ?? 0;
  const configCount = configs.data?.data?.length ?? 0;

  const analyticsData = analytics.data?.data;

  const activity = resolveChartSeries(analyticsData?.weekly_activity, SAMPLE_ACTIVITY_DATA);
  const activityData = activity.data;
  const activityLabel = activity.isSample
    ? "Documents & simulations processed (Sample data)"
    : "Documents & simulations processed";

  const throughput = resolveChartSeries(analyticsData?.throughput, SAMPLE_THROUGHPUT_DATA);
  const throughputData = throughput.data;
  const throughputLabel = throughput.isSample
    ? "Records processed per hour (Sample data)"
    : "Records processed per hour (today)";

  const totalProcessed = analyticsData?.total_processed ?? 12200;
  const totalWarnings = analyticsData?.total_warnings ?? 23;
  const processedLabel = formatProcessed(totalProcessed);

  const adapterList = adapters.data?.data?.adapters ?? [];
  const statusData = buildAdapterPieData(adapterList);
  const pieData = statusData.length > 0 ? statusData : FALLBACK_PIE;
  const pieSubtitle =
    statusData.length === 0 ? "Current distribution (Sample data)" : "Current distribution";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Dashboard</h1>
        <p className="mt-1 text-sm text-gray-400">Integration platform overview and metrics</p>
      </div>

      {/* Metric cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          title="Active Adapters"
          value={adapterCount}
          subtitle="Integration connectors"
          icon={Plug}
          trend="+2 this week"
          color="bg-indigo-500/10 text-indigo-400"
        />
        <MetricCard
          title="Documents"
          value={docCount}
          subtitle="Uploaded & processed"
          icon={FileText}
          trend="+18 today"
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
          value="—"
          subtitle="Run from Simulations tab"
          icon={FlaskConical}
          color="bg-purple-500/10 text-purple-400"
        />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Activity chart */}
        <div className="card p-6 lg:col-span-2">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="font-semibold text-white">Weekly Activity</h2>
              <p className="text-xs text-gray-400">{activityLabel}</p>
            </div>
            <Activity className="h-4 w-4 text-gray-500" aria-hidden="true" />
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
            <h2 className="font-semibold text-white">Adapter Status</h2>
            <p className="text-xs text-gray-400">{pieSubtitle}</p>
          </div>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={50}
                  outerRadius={75}
                  paddingAngle={4}
                  dataKey="value"
                >
                  {pieData.map((entry) => (
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
            {pieData.map((s) => (
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
            <h2 className="font-semibold text-white">Data Throughput</h2>
            <p className="text-xs text-gray-400">{throughputLabel}</p>
          </div>
          <div className="flex items-center gap-4 text-xs">
            <div className="flex items-center gap-1.5">
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" aria-hidden="true" />
              <span className="text-gray-400">{processedLabel}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <AlertTriangle className="h-3.5 w-3.5 text-amber-400" aria-hidden="true" />
              <span className="text-gray-400">{totalWarnings} warnings</span>
            </div>
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
