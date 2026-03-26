import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { documentsApi } from "@/lib/api";
import type { Document } from "@/types";
import { useDropzone } from "react-dropzone";
import { useCallback, useState } from "react";
import {
  Upload,
  FileText,
  FileSpreadsheet,
  FileCode,
  CheckCircle2,
  Clock,
  AlertCircle,
  Loader2,
  X,
} from "lucide-react";
import clsx from "clsx";

const fallbackDocs: Document[] = [
  { id: "1", filename: "trade_report_q1.xlsx", content_type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", size: 245760, status: "completed", uploaded_at: "2026-03-27T08:00:00Z", processed_at: "2026-03-27T08:01:23Z" },
  { id: "2", filename: "compliance_policy.pdf", content_type: "application/pdf", size: 1048576, status: "completed", uploaded_at: "2026-03-26T14:30:00Z", processed_at: "2026-03-26T14:32:00Z" },
  { id: "3", filename: "swift_messages.xml", content_type: "application/xml", size: 32768, status: "processing", uploaded_at: "2026-03-27T10:15:00Z" },
  { id: "4", filename: "market_data_feed.json", content_type: "application/json", size: 524288, status: "completed", uploaded_at: "2026-03-27T09:00:00Z", processed_at: "2026-03-27T09:00:45Z" },
  { id: "5", filename: "risk_assessment.csv", content_type: "text/csv", size: 163840, status: "failed", uploaded_at: "2026-03-25T16:00:00Z" },
];

const statusConfig = {
  pending: { label: "Pending", icon: Clock, cls: "badge-yellow" },
  processing: { label: "Processing", icon: Loader2, cls: "badge-blue" },
  completed: { label: "Completed", icon: CheckCircle2, cls: "badge-green" },
  failed: { label: "Failed", icon: AlertCircle, cls: "badge-red" },
} as const;

function fileIcon(contentType: string) {
  if (contentType.includes("spreadsheet") || contentType.includes("csv"))
    return FileSpreadsheet;
  if (contentType.includes("xml") || contentType.includes("json"))
    return FileCode;
  return FileText;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function Documents() {
  const queryClient = useQueryClient();
  const [uploadQueue, setUploadQueue] = useState<string[]>([]);

  const { data, error } = useQuery({
    queryKey: ["documents"],
    queryFn: documentsApi.list,
  });

  const uploadMutation = useMutation({
    mutationFn: documentsApi.upload,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      for (const file of acceptedFiles) {
        setUploadQueue((q) => [...q, file.name]);
        uploadMutation.mutate(file, {
          onSettled: () => {
            setUploadQueue((q) => q.filter((n) => n !== file.name));
          },
        });
      }
    },
    [uploadMutation],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/pdf": [".pdf"],
      "application/json": [".json"],
      "application/xml": [".xml"],
      "text/csv": [".csv"],
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
    },
  });

  const documents = data ?? fallbackDocs;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Documents</h1>
        <p className="mt-1 text-sm text-gray-400">
          Upload and manage integration documents
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-4 text-sm text-amber-400">
          Backend unavailable. Showing sample data. Uploads disabled.
        </div>
      )}

      {/* Drop zone */}
      <div
        {...getRootProps()}
        className={clsx(
          "card group cursor-pointer border-2 border-dashed p-10 text-center transition-all",
          isDragActive
            ? "border-indigo-500 bg-indigo-500/5"
            : "border-gray-700 hover:border-gray-500",
        )}
      >
        <input {...getInputProps()} />
        <div className="flex flex-col items-center gap-3">
          <div
            className={clsx(
              "rounded-full p-3 transition-colors",
              isDragActive
                ? "bg-indigo-500/20 text-indigo-400"
                : "bg-gray-800 text-gray-400 group-hover:text-gray-300",
            )}
          >
            <Upload className="h-6 w-6" />
          </div>
          <div>
            <p className="font-medium text-gray-300">
              {isDragActive
                ? "Drop files here..."
                : "Drag & drop files, or click to browse"}
            </p>
            <p className="mt-1 text-xs text-gray-500">
              PDF, JSON, XML, CSV, XLSX supported
            </p>
          </div>
        </div>
      </div>

      {/* Upload queue */}
      {uploadQueue.length > 0 && (
        <div className="space-y-2">
          {uploadQueue.map((name) => (
            <div
              key={name}
              className="flex items-center gap-3 rounded-lg border border-indigo-500/20 bg-indigo-500/5 px-4 py-3"
            >
              <Loader2 className="h-4 w-4 animate-spin text-indigo-400" />
              <span className="text-sm text-indigo-300">{name}</span>
              <span className="text-xs text-indigo-400/60">Uploading...</span>
            </div>
          ))}
        </div>
      )}

      {/* Document list */}
      <div className="card overflow-hidden">
        <div className="border-b border-gray-800 px-6 py-4">
          <h3 className="font-semibold text-white">
            Recent Documents{" "}
            <span className="text-sm font-normal text-gray-500">
              ({documents.length})
            </span>
          </h3>
        </div>
        <div className="divide-y divide-gray-800/60">
          {documents.map((doc) => {
            const st = statusConfig[doc.status];
            const IconFile = fileIcon(doc.content_type);
            const StatusIcon = st.icon;

            return (
              <div
                key={doc.id}
                className="flex items-center gap-4 px-6 py-4 transition-colors hover:bg-gray-800/30"
              >
                <div className="rounded-lg bg-gray-800 p-2">
                  <IconFile className="h-4 w-4 text-gray-400" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium text-gray-200">
                    {doc.filename}
                  </p>
                  <p className="text-xs text-gray-500">
                    {formatSize(doc.size)} &middot; {formatDate(doc.uploaded_at)}
                  </p>
                </div>
                <span className={st.cls}>
                  <StatusIcon
                    className={clsx(
                      "mr-1 h-3 w-3",
                      doc.status === "processing" && "animate-spin",
                    )}
                  />
                  {st.label}
                </span>
                <button type="button" className="text-gray-600 hover:text-gray-400 transition-colors">
                  <X className="h-4 w-4" />
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
