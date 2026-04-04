import { useToast } from "@/components/Toast";
import { documentsApi } from "@/lib/api";
import type { Document } from "@/types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  FileCode,
  FileSpreadsheet,
  FileText,
  Layers,
  Link2,
  Loader2,
  Search,
  Shield,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import type { FileRejection } from "react-dropzone";

// ── Types ────────────────────────────────────────────────────────────────────

type ParsedResult = {
  title?: string;
  summary?: string;
  confidence_score?: number;
  endpoints?: Array<{ path: string; method: string; description?: string; summary?: string }>;
  fields?: Array<{
    name: string;
    data_type?: string;
    is_required?: boolean;
    source_section?: string;
    description?: string;
  }>;
  auth_requirements?: Array<{
    auth_type: string;
    details?: { name?: string; scheme?: string; in?: string };
  }>;
  services_identified?: string[];
  raw_entities?: string[];
  parse_errors?: string[];
};

type DocumentDetail = Document & { parsed_result?: ParsedResult };
type DetailTab = "summary" | "endpoints" | "fields" | "auth" | "raw";

// ── Helpers ──────────────────────────────────────────────────────────────────

function fileIcon(ft: string) {
  if (ft === "json" || ft === "yaml" || ft === "yml") return FileCode;
  if (ft === "xlsx" || ft === "csv") return FileSpreadsheet;
  return FileText;
}

function formatDate(d: string) {
  return new Date(d).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const STATUS_DOT: Record<string, { color: string; label: string; pulse?: boolean }> = {
  parsed: { color: "var(--color-teal)", label: "Parsed" },
  completed: { color: "var(--color-teal)", label: "Completed" },
  done: { color: "var(--color-teal)", label: "Done" },
  parsing: { color: "#fbbf24", label: "Parsing", pulse: true },
  processing: { color: "#fbbf24", label: "Processing", pulse: true },
  pending: { color: "#fbbf24", label: "Pending" },
  uploaded: { color: "#64748b", label: "Uploaded" },
  failed: { color: "var(--color-error)", label: "Failed" },
};

const DOC_TYPE_BADGE: Record<string, string> = {
  api_spec: "badge-blue",
  brd: "badge-teal",
};

const METHOD_COLOR: Record<string, { bg: string; text: string }> = {
  GET: { bg: "rgba(15,184,154,0.12)", text: "#0fb89a" },
  POST: { bg: "rgba(29,111,164,0.15)", text: "#60a5fa" },
  PUT: { bg: "rgba(217,119,6,0.12)", text: "#fbbf24" },
  PATCH: { bg: "rgba(217,119,6,0.12)", text: "#fbbf24" },
  DELETE: { bg: "rgba(220,38,38,0.12)", text: "#f87171" },
};

// ── StatusDot ─────────────────────────────────────────────────────────────────

function StatusDot({ status }: { status: string }) {
  const cfg = STATUS_DOT[status] ?? { color: "#64748b", label: status };
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "0.375rem",
        fontSize: "0.75rem",
        fontWeight: 500,
        color: "var(--color-text-secondary)",
      }}
    >
      <span
        style={{
          width: 7,
          height: 7,
          borderRadius: "50%",
          backgroundColor: cfg.color,
          flexShrink: 0,
          boxShadow: cfg.pulse ? `0 0 0 0 ${cfg.color}` : undefined,
          animation: cfg.pulse ? "statusPulse 1.5s ease-in-out infinite" : undefined,
        }}
      />
      {cfg.label}
      <style>{"@keyframes statusPulse{0%,100%{opacity:1}50%{opacity:.4}}"}</style>
    </span>
  );
}

// ── DetailModal ───────────────────────────────────────────────────────────────

// biome-ignore lint/complexity/noExcessiveCognitiveComplexity: multi-tab modal
function DetailModal({ doc, onClose }: { doc: Document; onClose: () => void }) {
  const [tab, setTab] = useState<DetailTab>("summary");

  const { data, isLoading, error } = useQuery({
    queryKey: ["document", doc.id],
    queryFn: () => documentsApi.get(doc.id),
  });

  const detail = data?.data as DocumentDetail | null;
  const parsed = detail?.parsed_result;
  const FileIcon = fileIcon(doc.file_type);

  const tabs: { id: DetailTab; label: string; Icon: React.ElementType }[] = [
    { id: "summary", label: "Summary", Icon: FileText },
    {
      id: "endpoints",
      label: `Endpoints${parsed?.endpoints?.length ? ` (${parsed.endpoints.length})` : ""}`,
      Icon: Link2,
    },
    {
      id: "fields",
      label: `Fields${parsed?.fields?.length ? ` (${parsed.fields.length})` : ""}`,
      Icon: Layers,
    },
    { id: "auth", label: "Auth", Icon: Shield },
    { id: "raw", label: "Raw JSON", Icon: FileCode },
  ];

  return (
    // biome-ignore lint/a11y/useKeyWithClickEvents: overlay dismiss, keyboard handled by X button
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.65)" }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="animate-fade-in relative z-10 flex w-full max-w-3xl flex-col rounded-xl shadow-2xl"
        style={{
          maxHeight: "86vh",
          background: "var(--color-bg-elevated)",
          border: "1px solid var(--color-border-strong)",
        }}
      >
        {/* Header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.75rem",
            borderBottom: "1px solid var(--color-border)",
            padding: "1rem 1.25rem",
          }}
        >
          <div
            style={{
              background: "var(--color-bg-raised)",
              borderRadius: "0.5rem",
              padding: "0.5rem",
              flexShrink: 0,
            }}
          >
            <FileIcon style={{ width: 16, height: 16, color: "var(--color-text-muted)" }} />
          </div>
          <div style={{ minWidth: 0, flex: 1 }}>
            <p
              className="mono"
              style={{
                color: "var(--color-text-primary)",
                fontWeight: 600,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {doc.filename}
            </p>
            <p style={{ fontSize: "0.6875rem", color: "var(--color-text-muted)", marginTop: 2 }}>
              {doc.file_type.toUpperCase()} &middot; {formatDate(doc.created_at)}
            </p>
          </div>
          <StatusDot status={doc.status} />
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            style={{
              color: "var(--color-text-muted)",
              marginLeft: "0.5rem",
              background: "none",
              border: "none",
              cursor: "pointer",
              padding: 4,
            }}
          >
            <X style={{ width: 18, height: 18 }} />
          </button>
        </div>

        {/* Tabs */}
        <div
          style={{
            display: "flex",
            borderBottom: "1px solid var(--color-border)",
            padding: "0 1rem",
            gap: "0.25rem",
            flexShrink: 0,
          }}
        >
          {tabs.map(({ id, label, Icon }) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.375rem",
                padding: "0.5rem 0.75rem",
                fontSize: "0.6875rem",
                fontWeight: 600,
                textTransform: "uppercase",
                letterSpacing: "0.06em",
                border: "none",
                borderBottom:
                  tab === id ? "2px solid var(--color-brand-light)" : "2px solid transparent",
                background: "none",
                color: tab === id ? "var(--color-brand-light)" : "var(--color-text-muted)",
                cursor: "pointer",
                transition: "color 120ms, border-color 120ms",
              }}
            >
              <Icon style={{ width: 12, height: 12 }} />
              {label}
            </button>
          ))}
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflow: "auto", padding: "1.25rem" }}>
          {isLoading ? (
            <div style={{ display: "flex", justifyContent: "center", padding: "3rem" }}>
              <Loader2
                style={{
                  width: 24,
                  height: 24,
                  color: "var(--color-brand-light)",
                  animation: "spin 1s linear infinite",
                }}
              />
              <style>{"@keyframes spin{to{transform:rotate(360deg)}}"}</style>
            </div>
          ) : error || !parsed ? (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: "0.75rem",
                padding: "3rem",
                textAlign: "center",
              }}
            >
              <AlertCircle style={{ width: 32, height: 32, color: "var(--color-text-muted)" }} />
              <p style={{ fontSize: "0.875rem", color: "var(--color-text-secondary)" }}>
                {error ? "Failed to load document details." : "No parsed data available."}
              </p>
            </div>
          ) : tab === "summary" ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              {parsed.title && (
                <div>
                  <p
                    style={{
                      fontSize: "0.6875rem",
                      fontWeight: 600,
                      textTransform: "uppercase",
                      letterSpacing: "0.06em",
                      color: "var(--color-text-muted)",
                      marginBottom: 4,
                    }}
                  >
                    Title
                  </p>
                  <p style={{ fontSize: "0.875rem", color: "var(--color-text-primary)" }}>
                    {parsed.title}
                  </p>
                </div>
              )}
              {parsed.summary && (
                <div>
                  <p
                    style={{
                      fontSize: "0.6875rem",
                      fontWeight: 600,
                      textTransform: "uppercase",
                      letterSpacing: "0.06em",
                      color: "var(--color-text-muted)",
                      marginBottom: 4,
                    }}
                  >
                    Summary
                  </p>
                  <p
                    style={{
                      fontSize: "0.8125rem",
                      color: "var(--color-text-secondary)",
                      lineHeight: 1.6,
                      whiteSpace: "pre-line",
                    }}
                  >
                    {parsed.summary}
                  </p>
                </div>
              )}
              <div
                style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "0.75rem" }}
              >
                {[
                  {
                    label: "Confidence",
                    value:
                      parsed.confidence_score != null
                        ? `${Math.round(parsed.confidence_score * 100)}%`
                        : "—",
                    accent: "var(--color-teal)",
                  },
                  {
                    label: "Endpoints",
                    value: String(parsed.endpoints?.length ?? 0),
                    accent: "var(--color-brand-light)",
                  },
                  {
                    label: "Fields",
                    value: String(parsed.fields?.length ?? 0),
                    accent: "var(--color-brand-light)",
                  },
                  {
                    label: "Auth Schemes",
                    value: String(parsed.auth_requirements?.length ?? 0),
                    accent: "var(--color-brand-light)",
                  },
                ].map(({ label, value, accent }) => (
                  <div
                    key={label}
                    style={{
                      background: "var(--color-bg-raised)",
                      borderRadius: "0.5rem",
                      padding: "0.75rem",
                      border: "1px solid var(--color-border)",
                    }}
                  >
                    <p
                      style={{
                        fontSize: "0.6875rem",
                        color: "var(--color-text-muted)",
                        fontWeight: 500,
                      }}
                    >
                      {label}
                    </p>
                    <p
                      style={{ fontSize: "1.25rem", fontWeight: 700, color: accent, marginTop: 4 }}
                    >
                      {value}
                    </p>
                  </div>
                ))}
              </div>
              {parsed.services_identified && parsed.services_identified.length > 0 && (
                <div>
                  <p
                    style={{
                      fontSize: "0.6875rem",
                      fontWeight: 600,
                      textTransform: "uppercase",
                      letterSpacing: "0.06em",
                      color: "var(--color-text-muted)",
                      marginBottom: 8,
                    }}
                  >
                    Services Identified
                  </p>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                    {parsed.services_identified.map((s) => (
                      <span key={s} className="badge-teal">
                        {s}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {parsed.parse_errors && parsed.parse_errors.length > 0 && (
                <div
                  style={{
                    border: "1px solid rgba(220,38,38,0.2)",
                    background: "rgba(220,38,38,0.05)",
                    borderRadius: "0.5rem",
                    padding: "0.75rem",
                  }}
                >
                  <p
                    style={{
                      fontSize: "0.6875rem",
                      fontWeight: 600,
                      color: "var(--color-error-text)",
                      marginBottom: 4,
                    }}
                  >
                    Parse Errors
                  </p>
                  {parsed.parse_errors.map((e) => (
                    <p key={e} style={{ fontSize: "0.75rem", color: "var(--color-error-text)" }}>
                      {e}
                    </p>
                  ))}
                </div>
              )}
            </div>
          ) : tab === "endpoints" ? (
            parsed.endpoints && parsed.endpoints.length > 0 ? (
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8125rem" }}>
                <thead>
                  <tr>
                    {["Method", "Path", "Description"].map((h) => (
                      <th
                        key={h}
                        className="table-header"
                        style={{ textAlign: "left", paddingLeft: h === "Method" ? 0 : undefined }}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {parsed.endpoints.map((ep, i) => {
                    const mc = METHOD_COLOR[ep.method] ?? {
                      bg: "rgba(71,85,105,0.15)",
                      text: "#94a3b8",
                    };
                    return (
                      // biome-ignore lint/suspicious/noArrayIndexKey: endpoints lack stable id
                      <tr key={i} className="table-row">
                        <td style={{ paddingLeft: 0, paddingRight: "0.75rem", width: "5rem" }}>
                          <span
                            style={{
                              display: "inline-block",
                              padding: "0.125rem 0.5rem",
                              borderRadius: "0.25rem",
                              fontSize: "0.6875rem",
                              fontWeight: 700,
                              background: mc.bg,
                              color: mc.text,
                              letterSpacing: "0.04em",
                            }}
                          >
                            {ep.method}
                          </span>
                        </td>
                        <td
                          className="mono"
                          style={{ paddingRight: "0.75rem", color: "var(--color-text-primary)" }}
                        >
                          {ep.path}
                        </td>
                        <td style={{ color: "var(--color-text-secondary)" }}>
                          {ep.description ?? ep.summary ?? "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            ) : (
              <p
                style={{
                  fontSize: "0.875rem",
                  color: "var(--color-text-muted)",
                  textAlign: "center",
                  padding: "3rem 0",
                }}
              >
                No endpoints extracted.
              </p>
            )
          ) : tab === "fields" ? (
            parsed.fields && parsed.fields.length > 0 ? (
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8125rem" }}>
                <thead>
                  <tr>
                    {["Name", "Type", "Required", "Source"].map((h) => (
                      <th key={h} className="table-header" style={{ textAlign: "left" }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {parsed.fields.map((f, i) => (
                    // biome-ignore lint/suspicious/noArrayIndexKey: field list lacks stable id
                    <tr key={i} className="table-row">
                      <td
                        className="mono"
                        style={{
                          paddingRight: "0.75rem",
                          color: "var(--color-text-primary)",
                          fontWeight: 500,
                        }}
                      >
                        {f.name}
                      </td>
                      <td style={{ paddingRight: "0.75rem", color: "var(--color-brand-light)" }}>
                        {f.data_type ?? "—"}
                      </td>
                      <td style={{ paddingRight: "0.75rem" }}>
                        {f.is_required ? (
                          <span style={{ color: "var(--color-teal)", fontWeight: 600 }}>Yes</span>
                        ) : (
                          <span style={{ color: "var(--color-text-muted)" }}>No</span>
                        )}
                      </td>
                      <td style={{ color: "var(--color-text-muted)", fontSize: "0.6875rem" }}>
                        {f.source_section ?? "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p
                style={{
                  fontSize: "0.875rem",
                  color: "var(--color-text-muted)",
                  textAlign: "center",
                  padding: "3rem 0",
                }}
              >
                No fields extracted.
              </p>
            )
          ) : tab === "auth" ? (
            parsed.auth_requirements && parsed.auth_requirements.length > 0 ? (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                {parsed.auth_requirements.map((auth, i) => (
                  <div
                    key={`${auth.auth_type}-${i}`}
                    style={{
                      border: "1px solid var(--color-border)",
                      background: "var(--color-bg-raised)",
                      borderRadius: "0.5rem",
                      padding: "1rem",
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "0.5rem",
                        marginBottom: "0.5rem",
                      }}
                    >
                      <Shield
                        style={{ width: 14, height: 14, color: "var(--color-brand-light)" }}
                      />
                      <span
                        style={{
                          fontSize: "0.6875rem",
                          fontWeight: 700,
                          textTransform: "uppercase",
                          letterSpacing: "0.06em",
                          color: "var(--color-brand-light)",
                        }}
                      >
                        {auth.auth_type}
                      </span>
                    </div>
                    {auth.details?.name && (
                      <p style={{ fontSize: "0.75rem", color: "var(--color-text-secondary)" }}>
                        Name:{" "}
                        <code
                          style={{
                            fontFamily: '"IBM Plex Mono", monospace',
                            color: "var(--color-text-primary)",
                          }}
                        >
                          {auth.details.name}
                        </code>
                      </p>
                    )}
                    {auth.details?.in && (
                      <p style={{ fontSize: "0.75rem", color: "var(--color-text-secondary)" }}>
                        Location:{" "}
                        <code
                          style={{
                            fontFamily: '"IBM Plex Mono", monospace',
                            color: "var(--color-text-primary)",
                          }}
                        >
                          {auth.details.in}
                        </code>
                      </p>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p
                style={{
                  fontSize: "0.875rem",
                  color: "var(--color-text-muted)",
                  textAlign: "center",
                  padding: "3rem 0",
                }}
              >
                No auth requirements extracted.
              </p>
            )
          ) : (
            <pre
              style={{
                background: "var(--color-bg-base)",
                border: "1px solid var(--color-border)",
                borderRadius: "0.5rem",
                padding: "1rem",
                fontSize: "0.75rem",
                color: "var(--color-text-secondary)",
                overflowX: "auto",
                lineHeight: 1.6,
              }}
            >
              {JSON.stringify(detail, null, 2)}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Documents page ────────────────────────────────────────────────────────────

// biome-ignore lint/complexity/noExcessiveCognitiveComplexity: page-level component managing upload, list, modals
export default function Documents() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [uploadQueue, setUploadQueue] = useState<string[]>([]);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [selectedDoc, setSelectedDoc] = useState<Document | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<Document | null>(null);
  const [search, setSearch] = useState("");
  const [hoveredRow, setHoveredRow] = useState<string | null>(null);

  const { data, error, isLoading } = useQuery({
    queryKey: ["documents"],
    queryFn: () => documentsApi.list(),
  });

  const uploadMutation = useMutation({
    mutationFn: (file: File) => documentsApi.upload(file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
    onError: (err: unknown) => {
      setUploadError(err instanceof Error ? err.message : "Upload failed. Please try again.");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => documentsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      setConfirmDelete(null);
      toast("Document deleted.", "success");
    },
    onError: () => {
      toast("Failed to delete document.", "error");
      setConfirmDelete(null);
    },
  });

  const onDrop = useCallback(
    (accepted: File[]) => {
      setUploadError(null);
      for (const file of accepted) {
        setUploadQueue((q) => [...q, file.name]);
        uploadMutation.mutate(file, {
          onSettled: () => setUploadQueue((q) => q.filter((n) => n !== file.name)),
        });
      }
    },
    [uploadMutation]
  );

  const onDropRejected = useCallback((rejected: FileRejection[]) => {
    const msgs = rejected.flatMap((r) =>
      r.errors.map((e) =>
        e.code === "file-too-large" ? `${r.file.name} exceeds the 50 MB limit` : e.message
      )
    );
    setUploadError(msgs.join("; "));
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    onDropRejected,
    disabled: !!error,
    maxSize: 50 * 1024 * 1024,
    accept: {
      "application/pdf": [".pdf"],
      "application/json": [".json"],
      "application/xml": [".xml"],
      "text/csv": [".csv"],
      "application/x-yaml": [".yaml", ".yml"],
      "text/yaml": [".yaml", ".yml"],
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
    },
  });

  const allDocs: Document[] = data?.data ?? [];
  const docs = search.trim()
    ? allDocs.filter((d) => d.filename.toLowerCase().includes(search.toLowerCase().trim()))
    : allDocs;

  return (
    <div
      className="animate-fade-in"
      style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}
    >
      {/* Page header */}
      <div>
        <h1
          style={{
            fontSize: "1.25rem",
            fontWeight: 700,
            color: "var(--color-text-primary)",
            marginBottom: 2,
          }}
        >
          Documents
        </h1>
        <p style={{ fontSize: "0.8125rem", color: "var(--color-text-muted)" }}>
          Upload and manage integration documents
        </p>
      </div>

      {/* Alerts */}
      {error && (
        <div
          style={{
            border: "1px solid rgba(217,119,6,0.25)",
            background: "rgba(217,119,6,0.05)",
            borderRadius: "0.5rem",
            padding: "0.75rem 1rem",
            fontSize: "0.8125rem",
            color: "var(--color-warning-text)",
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
          }}
        >
          <AlertCircle style={{ width: 14, height: 14, flexShrink: 0 }} />
          Backend unavailable — uploads disabled.
        </div>
      )}
      {uploadError && (
        <div
          style={{
            border: "1px solid rgba(220,38,38,0.25)",
            background: "rgba(220,38,38,0.05)",
            borderRadius: "0.5rem",
            padding: "0.75rem 1rem",
            fontSize: "0.8125rem",
            color: "var(--color-error-text)",
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
          }}
        >
          <AlertCircle style={{ width: 14, height: 14, flexShrink: 0 }} />
          {uploadError}
          <button
            type="button"
            onClick={() => setUploadError(null)}
            style={{
              marginLeft: "auto",
              background: "none",
              border: "none",
              cursor: "pointer",
              color: "inherit",
              padding: 0,
            }}
          >
            <X style={{ width: 14, height: 14 }} />
          </button>
        </div>
      )}

      {/* Drop zone */}
      <div
        {...getRootProps()}
        style={{
          border: `2px dashed ${isDragActive ? "var(--color-brand-light)" : "var(--color-border-strong)"}`,
          background: isDragActive ? "var(--color-brand-subtle)" : "var(--color-bg-elevated)",
          borderRadius: "0.75rem",
          padding: "2.5rem 1.5rem",
          textAlign: "center",
          cursor: error ? "not-allowed" : "pointer",
          opacity: error ? 0.5 : 1,
          transition: "border-color 150ms, background 150ms",
        }}
      >
        <input {...getInputProps()} />
        <div
          style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "0.75rem" }}
        >
          <div
            style={{
              width: 44,
              height: 44,
              borderRadius: "50%",
              background: isDragActive ? "var(--color-brand-subtle)" : "var(--color-bg-raised)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              border: `1px solid ${isDragActive ? "var(--color-brand)" : "var(--color-border)"}`,
            }}
          >
            <Upload
              style={{
                width: 20,
                height: 20,
                color: isDragActive ? "var(--color-brand-light)" : "var(--color-text-muted)",
              }}
            />
          </div>
          <div>
            <p
              style={{
                fontSize: "0.875rem",
                fontWeight: 600,
                color: isDragActive ? "var(--color-brand-light)" : "var(--color-text-primary)",
              }}
            >
              {error
                ? "Upload unavailable — backend offline"
                : isDragActive
                  ? "Drop to upload"
                  : "Drag & drop files, or click to browse"}
            </p>
            <p style={{ fontSize: "0.6875rem", color: "var(--color-text-muted)", marginTop: 4 }}>
              PDF, DOCX, YAML, JSON, XML, CSV, XLSX &middot; max 50 MB
            </p>
          </div>
        </div>
      </div>

      {/* Upload queue */}
      {uploadQueue.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {uploadQueue.map((name) => (
            <div
              key={name}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.75rem",
                border: "1px solid var(--color-brand-subtle)",
                background: "var(--color-brand-subtle)",
                borderRadius: "0.5rem",
                padding: "0.625rem 0.875rem",
              }}
            >
              <Loader2
                style={{
                  width: 14,
                  height: 14,
                  color: "var(--color-brand-light)",
                  animation: "spin 1s linear infinite",
                }}
              />
              <span
                className="mono"
                style={{
                  fontSize: "0.8125rem",
                  color: "var(--color-text-primary)",
                  flex: 1,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {name}
              </span>
              <span style={{ fontSize: "0.6875rem", color: "var(--color-text-muted)" }}>
                Uploading…
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Document table */}
      <div className="card" style={{ overflow: "hidden" }}>
        {/* Table toolbar */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.75rem",
            borderBottom: "1px solid var(--color-border)",
            padding: "0.875rem 1.25rem",
          }}
        >
          <h2
            style={{
              flex: 1,
              fontSize: "0.875rem",
              fontWeight: 600,
              color: "var(--color-text-primary)",
            }}
          >
            Documents
            {!isLoading && (
              <span
                style={{
                  marginLeft: "0.375rem",
                  fontWeight: 400,
                  color: "var(--color-text-muted)",
                  fontSize: "0.8125rem",
                }}
              >
                ({docs.length})
              </span>
            )}
          </h2>
          <div style={{ position: "relative" }}>
            <Search
              style={{
                position: "absolute",
                left: "0.625rem",
                top: "50%",
                transform: "translateY(-50%)",
                width: 13,
                height: 13,
                color: "var(--color-text-muted)",
                pointerEvents: "none",
              }}
            />
            <input
              type="text"
              placeholder="Search filenames…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{
                background: "var(--color-bg-raised)",
                border: "1px solid var(--color-border)",
                borderRadius: "0.375rem",
                paddingLeft: "2rem",
                paddingRight: "0.75rem",
                paddingTop: "0.375rem",
                paddingBottom: "0.375rem",
                fontSize: "0.8125rem",
                color: "var(--color-text-primary)",
                width: "13rem",
                outline: "none",
              }}
            />
          </div>
        </div>

        {/* Table */}
        {isLoading ? (
          <div
            style={{
              padding: "1.5rem 1.25rem",
              display: "flex",
              flexDirection: "column",
              gap: "0.75rem",
            }}
          >
            {(["sk1", "sk2", "sk3", "sk4"] as const).map((sk) => (
              <div
                key={sk}
                style={{
                  height: "2.5rem",
                  background: "var(--color-bg-raised)",
                  borderRadius: "0.375rem",
                  animation: "pulse 1.5s ease-in-out infinite",
                }}
              />
            ))}
            <style>{"@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}"}</style>
          </div>
        ) : docs.length === 0 ? (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: "0.75rem",
              padding: "4rem 1.5rem",
              textAlign: "center",
            }}
          >
            <div
              style={{
                width: 48,
                height: 48,
                borderRadius: "50%",
                background: "var(--color-bg-raised)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              {search.trim() ? (
                <Search style={{ width: 20, height: 20, color: "var(--color-text-muted)" }} />
              ) : (
                <Upload style={{ width: 20, height: 20, color: "var(--color-text-muted)" }} />
              )}
            </div>
            <p
              style={{
                fontSize: "0.875rem",
                fontWeight: 600,
                color: "var(--color-text-secondary)",
              }}
            >
              {search.trim() ? "No matching documents" : "No documents yet"}
            </p>
            <p style={{ fontSize: "0.8125rem", color: "var(--color-text-muted)" }}>
              {search.trim()
                ? `No filenames match "${search}"`
                : "Drop a file above to get started"}
            </p>
          </div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th className="table-header" style={{ textAlign: "left", paddingLeft: "1.25rem" }}>
                  Filename
                </th>
                <th className="table-header" style={{ textAlign: "left" }}>
                  Type
                </th>
                <th className="table-header" style={{ textAlign: "left" }}>
                  Doc Type
                </th>
                <th className="table-header" style={{ textAlign: "left" }}>
                  Status
                </th>
                <th className="table-header" style={{ textAlign: "left" }}>
                  Created
                </th>
                <th
                  className="table-header"
                  style={{ textAlign: "right", paddingRight: "1.25rem" }}
                >
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {docs.map((doc) => {
                const FileIcon = fileIcon(doc.file_type);
                const isHovered = hoveredRow === doc.id;
                return (
                  // biome-ignore lint/a11y/useKeyWithClickEvents: tr click opens detail; delete button is keyboard-focusable
                  <tr
                    key={doc.id}
                    className="table-row"
                    onClick={() => setSelectedDoc(doc)}
                    onMouseEnter={() => setHoveredRow(doc.id)}
                    onMouseLeave={() => setHoveredRow(null)}
                    style={{ cursor: "pointer" }}
                  >
                    <td style={{ paddingLeft: "1.25rem", paddingRight: "0.75rem" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.625rem" }}>
                        <div
                          style={{
                            width: 28,
                            height: 28,
                            background: "var(--color-bg-raised)",
                            border: "1px solid var(--color-border)",
                            borderRadius: "0.375rem",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            flexShrink: 0,
                          }}
                        >
                          <FileIcon
                            style={{ width: 13, height: 13, color: "var(--color-text-muted)" }}
                          />
                        </div>
                        <span
                          className="mono"
                          style={{
                            color: "var(--color-text-primary)",
                            fontSize: "0.8125rem",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                            maxWidth: "18rem",
                          }}
                        >
                          {doc.filename}
                        </span>
                      </div>
                    </td>
                    <td style={{ paddingRight: "0.75rem" }}>
                      <span className="badge-gray">{doc.file_type.toUpperCase()}</span>
                    </td>
                    <td style={{ paddingRight: "0.75rem" }}>
                      <span className={DOC_TYPE_BADGE[doc.doc_type] ?? "badge-gray"}>
                        {doc.doc_type === "api_spec"
                          ? "API Spec"
                          : doc.doc_type === "brd"
                            ? "BRD"
                            : doc.doc_type}
                      </span>
                    </td>
                    <td style={{ paddingRight: "0.75rem" }}>
                      <StatusDot status={doc.status} />
                    </td>
                    <td
                      style={{
                        paddingRight: "0.75rem",
                        fontSize: "0.75rem",
                        color: "var(--color-text-muted)",
                      }}
                    >
                      {formatDate(doc.created_at)}
                    </td>
                    <td style={{ paddingRight: "1.25rem", textAlign: "right" }}>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setConfirmDelete(doc);
                        }}
                        aria-label={`Delete ${doc.filename}`}
                        style={{
                          background: "none",
                          border: "none",
                          cursor: "pointer",
                          padding: "0.25rem",
                          borderRadius: "0.25rem",
                          color: isHovered ? "var(--color-error-text)" : "transparent",
                          transition: "color 120ms",
                        }}
                      >
                        <Trash2 style={{ width: 14, height: 14 }} />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Detail modal */}
      {selectedDoc && <DetailModal doc={selectedDoc} onClose={() => setSelectedDoc(null)} />}

      {/* Delete confirmation */}
      {confirmDelete && (
        // biome-ignore lint/a11y/useKeyWithClickEvents: backdrop dismiss, keyboard handled by Cancel button
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: "rgba(0,0,0,0.65)" }}
          onClick={(e) => {
            if (e.target === e.currentTarget) setConfirmDelete(null);
          }}
        >
          <div
            className="animate-fade-in"
            style={{
              background: "var(--color-bg-elevated)",
              border: "1px solid var(--color-border-strong)",
              borderRadius: "0.75rem",
              padding: "1.5rem",
              width: "100%",
              maxWidth: "24rem",
              boxShadow: "0 20px 60px rgba(0,0,0,0.5)",
            }}
          >
            <h3
              style={{
                fontSize: "0.9375rem",
                fontWeight: 700,
                color: "var(--color-text-primary)",
                marginBottom: "0.5rem",
              }}
            >
              Delete document?
            </h3>
            <p
              style={{
                fontSize: "0.8125rem",
                color: "var(--color-text-secondary)",
                marginBottom: "1.25rem",
                lineHeight: 1.5,
              }}
            >
              <span className="mono" style={{ color: "var(--color-text-primary)" }}>
                {confirmDelete.filename}
              </span>{" "}
              will be permanently deleted. This cannot be undone.
            </p>
            <div style={{ display: "flex", gap: "0.75rem", justifyContent: "flex-end" }}>
              <button
                type="button"
                className="btn-secondary"
                onClick={() => setConfirmDelete(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn-danger"
                style={{
                  background: deleteMutation.isPending ? undefined : "rgba(220,38,38,0.12)",
                  borderColor: "rgba(220,38,38,0.3)",
                  color: "var(--color-error-text)",
                }}
                disabled={deleteMutation.isPending}
                onClick={() => deleteMutation.mutate(confirmDelete.id)}
              >
                {deleteMutation.isPending ? (
                  <>
                    <Loader2
                      style={{ width: 13, height: 13, animation: "spin 1s linear infinite" }}
                    />{" "}
                    Deleting…
                  </>
                ) : (
                  <>
                    <Trash2 style={{ width: 13, height: 13 }} /> Delete
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
