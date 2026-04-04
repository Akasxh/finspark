import { useToast } from "@/components/Toast";
import { adaptersApi, configurationsApi, documentsApi } from "@/lib/api";
import type {
  Adapter,
  ConfigHistoryEntry,
  ConfigValidationResult,
  Configuration,
  FieldMapping,
} from "@/types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  BarChart3,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Download,
  History,
  PlayCircle,
  Plus,
  Rocket,
  RotateCcw,
  Save,
  Settings,
  Sparkles,
} from "lucide-react";
import { useState } from "react";

// ── Constants ────────────────────────────────────────────────────────────────

const STATUS_STEPS = ["draft", "configured", "testing", "active"] as const;
type StatusStep = (typeof STATUS_STEPS)[number];

const STATUS_CONFIG: Record<string, { label: string; cls: string }> = {
  draft: { label: "Draft", cls: "badge-yellow" },
  configured: { label: "Configured", cls: "badge-blue" },
  validating: { label: "Validating", cls: "badge-blue" },
  testing: { label: "Testing", cls: "badge-blue" },
  active: { label: "Active", cls: "badge-green" },
  deprecated: { label: "Deprecated", cls: "badge-gray" },
};

const TRANSITION_BUTTONS: Record<
  string,
  { label: string; icon: React.ElementType; targetState: string }[]
> = {
  draft: [{ label: "Mark Configured", icon: CheckCircle2, targetState: "configured" }],
  configured: [{ label: "Start Testing", icon: PlayCircle, targetState: "testing" }],
  testing: [{ label: "Deploy", icon: Rocket, targetState: "active" }],
};

const TRANSFORM_OPTIONS = [
  "none", "upper", "lower", "parse_number", "parse_date",
  "normalize_phone", "validate_email", "to_string", "format_date", "parse_boolean",
];

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmtDate(s: string) {
  return new Date(s).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function fmtDateTime(s: string) {
  return new Date(s).toLocaleString("en-US", {
    month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

// ── Sub-components ────────────────────────────────────────────────────────────

function SkeletonRow() {
  return (
    <div className="card animate-pulse overflow-hidden">
      <div style={{ display: "flex", alignItems: "center", gap: 16, padding: "16px 24px" }}>
        <div style={{ width: 36, height: 36, borderRadius: 8, background: "var(--color-bg-raised)" }} />
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ height: 14, width: 192, borderRadius: 4, background: "var(--color-border-strong)" }} />
          <div style={{ height: 11, width: 128, borderRadius: 4, background: "var(--color-border)" }} />
        </div>
      </div>
    </div>
  );
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const barColor = pct >= 70 ? "var(--color-teal)" : pct >= 50 ? "var(--color-warning)" : "var(--color-error)";
  const textColor = pct >= 70 ? "var(--color-teal)" : pct >= 50 ? "var(--color-warning-text)" : "var(--color-error-text)";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{ flex: 1, height: 5, borderRadius: 9999, background: "var(--color-border-strong)", overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", borderRadius: 9999, background: barColor, transition: "width 300ms ease" }} />
      </div>
      <span style={{ fontSize: 11, fontVariantNumeric: "tabular-nums", fontWeight: 500, color: textColor, minWidth: 28, textAlign: "right" }}>
        {pct}%
      </span>
    </div>
  );
}

function StatusStepper({ status }: { status: string }) {
  const currentIdx = STATUS_STEPS.indexOf(status as StatusStep);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 0 }}>
      {STATUS_STEPS.map((step, idx) => {
        const isPast = idx < currentIdx;
        const isCurrent = idx === currentIdx;
        const dotColor = isPast ? "var(--color-teal)" : isCurrent ? "var(--color-brand-light)" : "var(--color-border-strong)";
        const labelColor = isPast ? "var(--color-teal)" : isCurrent ? "var(--color-brand-light)" : "var(--color-text-muted)";
        const lineColor = isPast ? "var(--color-teal)" : "var(--color-border)";
        return (
          <div key={step} style={{ display: "flex", alignItems: "center" }}>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
              <div style={{
                width: 10, height: 10, borderRadius: "50%", background: dotColor,
                boxShadow: isCurrent ? `0 0 0 3px rgba(45, 143, 206, 0.2)` : "none",
                transition: "all 150ms ease",
              }} />
              <span style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", color: labelColor, whiteSpace: "nowrap" }}>
                {step}
              </span>
            </div>
            {idx < STATUS_STEPS.length - 1 && (
              <div style={{ width: 32, height: 1, background: lineColor, margin: "0 4px", marginBottom: 16, transition: "background 150ms ease" }} />
            )}
          </div>
        );
      })}
    </div>
  );
}

function ValidationPanel({ configId }: { configId: string }) {
  const [result, setResult] = useState<ConfigValidationResult | null>(null);
  const [ran, setRan] = useState(false);

  const validateMutation = useMutation({
    mutationFn: () => configurationsApi.validate(configId),
    onSuccess: (resp) => {
      if (resp.data) { setResult(resp.data); setRan(true); }
    },
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <button
          type="button"
          className="btn-secondary"
          style={{ fontSize: 12, padding: "6px 12px" }}
          onClick={() => validateMutation.mutate()}
          disabled={validateMutation.isPending}
        >
          <BarChart3 style={{ width: 13, height: 13 }} />
          {validateMutation.isPending ? "Validating..." : ran ? "Re-validate" : "Run Validation"}
        </button>
        {ran && result && (
          <span style={{ fontSize: 12, fontWeight: 600, color: result.is_valid ? "var(--color-teal)" : "var(--color-error-text)" }}>
            {result.is_valid ? "Valid" : "Invalid"}
          </span>
        )}
      </div>

      {ran && result && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 11, color: "var(--color-text-muted)", minWidth: 60 }}>Coverage</span>
            <div style={{ flex: 1, maxWidth: 200 }}>
              <ConfidenceBar value={result.coverage_score} />
            </div>
          </div>

          {result.errors.length > 0 && (
            <div style={{ borderRadius: 6, border: "1px solid rgba(220,38,38,0.2)", background: "rgba(220,38,38,0.05)", padding: 12 }}>
              <p style={{ fontSize: 11, fontWeight: 600, color: "var(--color-error-text)", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                Errors ({result.errors.length})
              </p>
              {result.errors.map((e) => (
                <div key={e} style={{ display: "flex", alignItems: "flex-start", gap: 6, marginBottom: 4 }}>
                  <AlertCircle style={{ width: 12, height: 12, color: "var(--color-error-text)", marginTop: 1, flexShrink: 0 }} />
                  <span style={{ fontSize: 12, color: "var(--color-error-text)" }}>{e}</span>
                </div>
              ))}
            </div>
          )}

          {result.warnings.length > 0 && (
            <div style={{ borderRadius: 6, border: "1px solid rgba(217,119,6,0.2)", background: "rgba(217,119,6,0.05)", padding: 12 }}>
              <p style={{ fontSize: 11, fontWeight: 600, color: "var(--color-warning-text)", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                Warnings ({result.warnings.length})
              </p>
              {result.warnings.map((w) => (
                <p key={w} style={{ fontSize: 12, color: "var(--color-warning-text)", marginBottom: 2 }}>{w}</p>
              ))}
            </div>
          )}

          {result.missing_required_fields.length > 0 && (
            <p style={{ fontSize: 11, color: "var(--color-text-muted)" }}>
              Missing required: <span style={{ fontFamily: "monospace", color: "var(--color-text-secondary)" }}>{result.missing_required_fields.join(", ")}</span>
            </p>
          )}
        </div>
      )}

      {validateMutation.isError && (
        <p style={{ fontSize: 12, color: "var(--color-error-text)" }}>Validation request failed. Check connection.</p>
      )}
    </div>
  );
}

function HistoryPanel({ configId, currentVersion }: { configId: string; currentVersion: number }) {
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["config-history", configId],
    queryFn: () => configurationsApi.history(configId),
  });

  const rollbackMutation = useMutation({
    mutationFn: (v: number) => configurationsApi.rollback(configId, v),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["configurations"] });
      queryClient.invalidateQueries({ queryKey: ["config-history", configId] });
      toast("Rolled back successfully.", "success");
    },
    onError: () => { toast("Rollback failed.", "error"); },
  });

  const handleRollback = (entry: ConfigHistoryEntry) => {
    if (window.confirm(`Roll back to version ${entry.version}? This creates a new version from that snapshot.`)) {
      rollbackMutation.mutate(entry.version);
    }
  };

  if (isLoading) return <p style={{ fontSize: 12, color: "var(--color-text-muted)", padding: "8px 0" }}>Loading history...</p>;
  if (isError) return <p style={{ fontSize: 12, color: "var(--color-error-text)", padding: "8px 0" }}>Failed to load history.</p>;

  const entries: ConfigHistoryEntry[] = data?.data ?? [];
  if (entries.length === 0) return <p style={{ fontSize: 12, color: "var(--color-text-muted)", padding: "8px 0" }}>No history available.</p>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {entries.map((entry) => (
        <div
          key={entry.version}
          style={{
            display: "flex", alignItems: "center", gap: 12,
            borderRadius: 6, border: "1px solid var(--color-border)",
            background: "var(--color-bg-base)", padding: "8px 12px",
          }}
        >
          <div style={{
            width: 28, height: 28, borderRadius: "50%", flexShrink: 0,
            background: "var(--color-brand-subtle)", display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 10, fontWeight: 700, color: "var(--color-brand-light)",
          }}>
            v{entry.version}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <p style={{ fontSize: 12, fontWeight: 500, color: "var(--color-text-primary)", textTransform: "capitalize" }}>
              {entry.change_type.replace(/_/g, " ")}
            </p>
            <p style={{ fontSize: 11, color: "var(--color-text-muted)" }}>
              {entry.changed_by} · {fmtDateTime(entry.timestamp)}
            </p>
          </div>
          {entry.version === currentVersion ? (
            <span style={{ fontSize: 11, fontWeight: 600, color: "var(--color-teal)" }}>current</span>
          ) : (
            <button
              type="button"
              className="btn-secondary"
              style={{ fontSize: 11, padding: "4px 8px" }}
              disabled={rollbackMutation.isPending}
              onClick={() => handleRollback(entry)}
            >
              <RotateCcw style={{ width: 11, height: 11 }} />
              Rollback
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

function MappingsTable({ cfg }: { cfg: Configuration }) {
  const { toast } = useToast();
  const [mappings, setMappings] = useState<FieldMapping[]>(() => cfg.field_mappings.map((fm) => ({ ...fm })));
  const [isDirty, setIsDirty] = useState(false);

  const updateTarget = (idx: number, value: string) => {
    setMappings((prev) => { const next = [...prev]; next[idx] = { ...next[idx], target_field: value }; return next; });
    setIsDirty(true);
  };

  const updateTransform = (idx: number, value: string) => {
    setMappings((prev) => { const next = [...prev]; next[idx] = { ...next[idx], transformation: value === "none" ? undefined : value }; return next; });
    setIsDirty(true);
  };

  if (mappings.length === 0) {
    return <p style={{ fontSize: 12, color: "var(--color-text-muted)" }}>No field mappings configured.</p>;
  }

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <span style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--color-text-muted)" }}>
          {mappings.length} Mappings
        </span>
        {isDirty && (
          <button
            type="button"
            className="btn-primary"
            style={{ fontSize: 11, padding: "4px 10px" }}
            onClick={() => { toast("Mappings saved (PATCH pending backend support).", "success"); setIsDirty(false); }}
          >
            <Save style={{ width: 11, height: 11 }} />
            Save
          </button>
        )}
      </div>
      <div style={{ overflowX: "auto", borderRadius: 6, border: "1px solid var(--color-border)" }}>
        <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--color-border)", background: "var(--color-bg-base)" }}>
              {["Source", "→", "Target", "Confidence", "Transform"].map((h) => (
                <th key={h} style={{ padding: "8px 12px", textAlign: h === "→" ? "center" : "left", fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--color-text-muted)" }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {mappings.map((fm, i) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: field mappings have no stable id
              <tr key={i} style={{ borderBottom: "1px solid var(--color-border)" }}>
                <td style={{ padding: "8px 12px" }}>
                  <span className="mono" style={{ color: "var(--color-text-primary)", fontSize: 12 }}>{fm.source_field}</span>
                </td>
                <td style={{ padding: "8px 12px", textAlign: "center", color: "var(--color-text-muted)" }}>
                  <ChevronRight style={{ width: 12, height: 12, margin: "0 auto" }} />
                </td>
                <td style={{ padding: "8px 12px", minWidth: 160 }}>
                  <input
                    type="text"
                    value={fm.target_field}
                    placeholder="target field..."
                    onChange={(e) => updateTarget(i, e.target.value)}
                    style={{
                      width: "100%", borderRadius: 4, border: "1px solid var(--color-border-strong)",
                      background: "var(--color-bg-raised)", padding: "4px 8px",
                      fontFamily: "monospace", fontSize: 12, color: "var(--color-text-primary)",
                      outline: "none", boxSizing: "border-box",
                    }}
                    onFocus={(e) => { e.currentTarget.style.borderColor = "var(--color-brand-light)"; }}
                    onBlur={(e) => { e.currentTarget.style.borderColor = "var(--color-border-strong)"; }}
                  />
                </td>
                <td style={{ padding: "8px 12px", minWidth: 120 }}>
                  <ConfidenceBar value={fm.confidence} />
                </td>
                <td style={{ padding: "8px 12px" }}>
                  <select
                    value={fm.transformation ?? "none"}
                    onChange={(e) => updateTransform(i, e.target.value)}
                    style={{
                      borderRadius: 4, border: "1px solid var(--color-border-strong)",
                      background: "var(--color-bg-raised)", padding: "4px 8px",
                      fontSize: 12, color: "var(--color-text-primary)", outline: "none",
                    }}
                    onFocus={(e) => { e.currentTarget.style.borderColor = "var(--color-brand-light)"; }}
                    onBlur={(e) => { e.currentTarget.style.borderColor = "var(--color-border-strong)"; }}
                  >
                    {TRANSFORM_OPTIONS.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

type DetailTab = "mappings" | "history" | "validation";

function ConfigDetail({ cfg }: { cfg: Configuration }) {
  const [activeTab, setActiveTab] = useState<DetailTab>("mappings");
  const { toast } = useToast();

  const handleExport = async (format: "json" | "yaml") => {
    try {
      const blob = await configurationsApi.export(cfg.id, format);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${cfg.name.replace(/\s+/g, "_")}_v${cfg.version}.${format}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      toast("Export failed.", "error");
    }
  };

  const tabs: { id: DetailTab; label: string; icon: React.ElementType }[] = [
    { id: "mappings", label: "Mappings", icon: Settings },
    { id: "history", label: "History", icon: History },
    { id: "validation", label: "Validation", icon: BarChart3 },
  ];

  return (
    <div className="animate-fade-in" style={{ borderTop: "1px solid var(--color-border)", background: "var(--color-bg-base)", padding: "20px 24px", display: "flex", flexDirection: "column", gap: 20 }}>

      {/* Status pipeline */}
      <div>
        <p style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--color-text-muted)", marginBottom: 12 }}>
          Lifecycle
        </p>
        <StatusStepper status={cfg.status} />
      </div>

      {/* Export */}
      <div>
        <p style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--color-text-muted)", marginBottom: 8 }}>
          Export
        </p>
        <div style={{ display: "flex", gap: 8 }}>
          <button type="button" className="btn-secondary" style={{ fontSize: 12, padding: "5px 12px" }} onClick={() => handleExport("json")}>
            <Download style={{ width: 13, height: 13 }} />
            JSON
          </button>
          <button type="button" className="btn-secondary" style={{ fontSize: 12, padding: "5px 12px" }} onClick={() => handleExport("yaml")}>
            <Download style={{ width: 13, height: 13 }} />
            YAML
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div>
        <div style={{ display: "flex", borderBottom: "1px solid var(--color-border)", marginBottom: 16, gap: 0 }}>
          {tabs.map(({ id, label, icon: Icon }) => {
            const isActive = activeTab === id;
            return (
              <button
                key={id}
                type="button"
                onClick={() => setActiveTab(id)}
                style={{
                  display: "inline-flex", alignItems: "center", gap: 6,
                  padding: "8px 14px", fontSize: 12, fontWeight: 500,
                  borderBottom: isActive ? "2px solid var(--color-brand-light)" : "2px solid transparent",
                  marginBottom: -1, color: isActive ? "var(--color-brand-light)" : "var(--color-text-muted)",
                  background: "transparent", cursor: "pointer", transition: "color 120ms ease",
                }}
              >
                <Icon style={{ width: 12, height: 12 }} />
                {label}
              </button>
            );
          })}
        </div>

        {activeTab === "mappings" && <MappingsTable cfg={cfg} />}
        {activeTab === "history" && <HistoryPanel configId={cfg.id} currentVersion={cfg.version} />}
        {activeTab === "validation" && <ValidationPanel configId={cfg.id} />}
      </div>

      {/* Meta */}
      <p style={{ fontSize: 11, color: "var(--color-text-muted)" }}>
        Adapter version: <code style={{ fontFamily: "monospace", color: "var(--color-text-secondary)" }}>{cfg.adapter_version_id}</code>
        {" · "}Created {fmtDate(cfg.created_at)}
      </p>
    </div>
  );
}

// ── Generate Form ─────────────────────────────────────────────────────────────

const inputStyle: React.CSSProperties = {
  width: "100%", borderRadius: 6, border: "1px solid var(--color-border-strong)",
  background: "var(--color-bg-raised)", padding: "8px 12px",
  fontSize: 13, color: "var(--color-text-primary)", outline: "none", boxSizing: "border-box",
};

function GenerateForm({ onDone }: { onDone: () => void }) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [documentId, setDocumentId] = useState("");
  const [selectedAdapterId, setSelectedAdapterId] = useState("");
  const [adapterVersionId, setAdapterVersionId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: docsData } = useQuery({ queryKey: ["documents"], queryFn: () => documentsApi.list() });
  const { data: adaptersData } = useQuery({ queryKey: ["adapters"], queryFn: () => adaptersApi.list() });

  const docs = docsData?.data ?? [];
  const adapters: Adapter[] = adaptersData?.data?.adapters ?? [];
  const selectedAdapter = adapters.find((a) => a.id === selectedAdapterId);

  const generateMutation = useMutation({
    mutationFn: configurationsApi.generate,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["configurations"] });
      toast("Configuration generated.", "success");
      onDone();
    },
    onError: (err: Error) => { setError(err.message ?? "Generation failed."); },
  });

  const handleAdapterChange = (id: string) => {
    setSelectedAdapterId(id);
    setAdapterVersionId("");
    const adapter = adapters.find((a) => a.id === id);
    if (adapter && !name) setName(`${adapter.name} Integration`);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !documentId || !adapterVersionId) return;
    setError(null);
    generateMutation.mutate({ name: name.trim(), document_id: documentId, adapter_version_id: adapterVersionId, auto_map: true });
  };

  const focusStyle = (e: React.FocusEvent<HTMLSelectElement | HTMLInputElement>) => {
    e.currentTarget.style.borderColor = "var(--color-brand-light)";
  };
  const blurStyle = (e: React.FocusEvent<HTMLSelectElement | HTMLInputElement>) => {
    e.currentTarget.style.borderColor = "var(--color-border-strong)";
  };

  return (
    <div className="card animate-fade-in" style={{ padding: 24 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 20 }}>
        <Sparkles style={{ width: 16, height: 16, color: "var(--color-brand-light)" }} />
        <h2 style={{ fontSize: 15, fontWeight: 600, color: "var(--color-text-primary)" }}>Generate Configuration</h2>
      </div>

      <form onSubmit={handleSubmit} style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 16 }}>
        <div>
          <label style={{ display: "block", fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--color-text-muted)", marginBottom: 6 }}>
            Document
          </label>
          <select value={documentId} onChange={(e) => setDocumentId(e.target.value)} style={inputStyle} onFocus={focusStyle} onBlur={blurStyle}>
            <option value="">Select document...</option>
            {docs.map((doc) => (
              <option key={doc.id} value={doc.id}>{doc.filename} ({doc.status})</option>
            ))}
          </select>
        </div>

        <div>
          <label style={{ display: "block", fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--color-text-muted)", marginBottom: 6 }}>
            Adapter
          </label>
          <select value={selectedAdapterId} onChange={(e) => handleAdapterChange(e.target.value)} style={inputStyle} onFocus={focusStyle} onBlur={blurStyle}>
            <option value="">Select adapter...</option>
            {adapters.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        </div>

        <div>
          <label style={{ display: "block", fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--color-text-muted)", marginBottom: 6 }}>
            Version
          </label>
          <select
            value={adapterVersionId}
            onChange={(e) => setAdapterVersionId(e.target.value)}
            disabled={!selectedAdapter}
            style={{ ...inputStyle, opacity: selectedAdapter ? 1 : 0.5 }}
            onFocus={focusStyle} onBlur={blurStyle}
          >
            <option value="">{selectedAdapter ? "Select version..." : "Select adapter first"}</option>
            {selectedAdapter?.versions.map((v) => (
              <option key={v.id} value={v.id}>v{v.version} — {v.status}</option>
            ))}
          </select>
        </div>

        <div>
          <label style={{ display: "block", fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--color-text-muted)", marginBottom: 6 }}>
            Name
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Credit Bureau Integration"
            style={inputStyle}
            onFocus={focusStyle} onBlur={blurStyle}
          />
        </div>

        <div style={{ gridColumn: "1 / -1", display: "flex", justifyContent: "flex-end", gap: 8 }}>
          {error && (
            <div style={{ flex: 1, borderRadius: 6, border: "1px solid rgba(220,38,38,0.2)", background: "rgba(220,38,38,0.05)", padding: "8px 12px", fontSize: 12, color: "var(--color-error-text)" }}>
              {error}
            </div>
          )}
          <button type="submit" className="btn-primary" disabled={!name.trim() || !documentId || !adapterVersionId || generateMutation.isPending}>
            <Sparkles style={{ width: 14, height: 14 }} />
            {generateMutation.isPending ? "Generating..." : "Generate"}
          </button>
        </div>
      </form>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function Configurations() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [showForm, setShowForm] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ["configurations"],
    queryFn: () => configurationsApi.list(),
  });

  const transitionMutation = useMutation({
    mutationFn: ({ id, targetState }: { id: string; targetState: string }) =>
      configurationsApi.transition(id, targetState),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["configurations"] });
      toast("State updated.", "success");
    },
    onError: () => { toast("Transition failed.", "error"); },
  });

  const configs: Configuration[] = data?.data ?? [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--color-text-primary)", marginBottom: 4 }}>Configurations</h1>
          <p style={{ fontSize: 13, color: "var(--color-text-secondary)" }}>
            Generate and manage integration configurations
          </p>
        </div>
        <button
          type="button"
          className={showForm ? "btn-secondary" : "btn-primary"}
          onClick={() => setShowForm((v) => !v)}
        >
          {showForm ? "Cancel" : <><Plus style={{ width: 15, height: 15 }} /> Generate Config</>}
        </button>
      </div>

      {/* Error banner */}
      {error && (
        <div style={{ borderRadius: 8, border: "1px solid rgba(217,119,6,0.2)", background: "rgba(217,119,6,0.05)", padding: "12px 16px", fontSize: 13, color: "var(--color-warning-text)" }}>
          Failed to load configurations. Check your connection and try again.
        </div>
      )}

      {/* Generate form slide-in */}
      {showForm && <GenerateForm onDone={() => setShowForm(false)} />}

      {/* Config list */}
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {isLoading ? (
          <><SkeletonRow /><SkeletonRow /><SkeletonRow /></>
        ) : configs.length === 0 && !error ? (
          <div className="card" style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "64px 24px", textAlign: "center" }}>
            <Settings style={{ width: 40, height: 40, color: "var(--color-text-muted)", marginBottom: 12 }} />
            <p style={{ fontSize: 14, fontWeight: 500, color: "var(--color-text-secondary)", marginBottom: 4 }}>No configurations yet</p>
            <p style={{ fontSize: 12, color: "var(--color-text-muted)" }}>Click "Generate Config" to create your first integration configuration.</p>
          </div>
        ) : (
          configs.map((cfg) => {
            const st = STATUS_CONFIG[cfg.status] ?? { label: cfg.status, cls: "badge-gray" };
            const isExpanded = expandedId === cfg.id;
            const transitions = TRANSITION_BUTTONS[cfg.status] ?? [];

            return (
              <div key={cfg.id} className="card" style={{ overflow: "hidden" }}>
                {/* Row header */}
                <button
                  type="button"
                  style={{
                    display: "flex", width: "100%", alignItems: "center", gap: 16,
                    padding: "14px 20px", textAlign: "left", background: "transparent", cursor: "pointer",
                    transition: "background 100ms ease",
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = "var(--color-bg-raised)"; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
                  onClick={() => setExpandedId(isExpanded ? null : cfg.id)}
                >
                  <div style={{ width: 36, height: 36, borderRadius: 8, background: "var(--color-bg-raised)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                    <Settings style={{ width: 16, height: 16, color: "var(--color-text-muted)" }} />
                  </div>

                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 4 }}>
                      <span style={{ fontSize: 14, fontWeight: 600, color: "var(--color-text-primary)" }}>{cfg.name}</span>
                      <span className={st.cls}>{st.label}</span>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 12, color: "var(--color-text-muted)" }}>
                      <span className="mono" style={{ fontSize: 12 }}>v{cfg.version}</span>
                      <span>·</span>
                      <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                        <Clock style={{ width: 11, height: 11 }} />
                        {fmtDate(cfg.updated_at)}
                      </span>
                      <span>·</span>
                      <span>{cfg.field_mappings.length} mappings</span>
                    </div>
                  </div>

                  {/* Lifecycle transition buttons */}
                  {transitions.length > 0 && (
                    <div style={{ display: "flex", gap: 8 }} onClick={(e) => e.stopPropagation()}>
                      {transitions.map((t) => {
                        const TIcon = t.icon;
                        return (
                          <button
                            key={t.targetState}
                            type="button"
                            className="btn-secondary"
                            style={{ fontSize: 11, padding: "5px 10px" }}
                            disabled={transitionMutation.isPending}
                            onClick={() => transitionMutation.mutate({ id: cfg.id, targetState: t.targetState })}
                          >
                            <TIcon style={{ width: 12, height: 12 }} />
                            {t.label}
                          </button>
                        );
                      })}
                    </div>
                  )}

                  <ChevronDown style={{
                    width: 15, height: 15, color: "var(--color-text-muted)", flexShrink: 0,
                    transform: isExpanded ? "rotate(180deg)" : "rotate(0deg)", transition: "transform 150ms ease",
                  }} />
                </button>

                {/* Expanded detail */}
                {isExpanded && <ConfigDetail cfg={cfg} />}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
