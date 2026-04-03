import { documentsApi } from "@/lib/api";
import type { Document } from "@/types";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  FileCode,
  FileSpreadsheet,
  FileText,
  Loader2,
  Upload,
  X,
} from "lucide-react";
import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import type { FileRejection } from "react-dropzone";

const statusConfig: Record<
  string,
  { label: string; icon: React.ComponentType<{ className?: string }>; cls: string }
> = {
  pending: { label: "Pending", icon: Clock, cls: "badge-yellow" },
  processing: { label: "Processing", icon: Loader2, cls: "badge-blue" },
  parsing: { label: "Parsing", icon: Loader2, cls: "badge-blue" },
  completed: { label: "Completed", icon: CheckCircle2, cls: "badge-green" },
  done: { label: "Done", icon: CheckCircle2, cls: "badge-green" },
  parsed: { label: "Parsed", icon: CheckCircle2, cls: "badge-green" },
  failed: { label: "Failed", icon: AlertCircle, cls: "badge-red" },
};

function fileIcon(fileType: string) {
  if (fileType === "json" || fileType === "yaml") return FileCode;
  if (fileType === "xlsx" || fileType === "csv") return FileSpreadsheet;
  return FileText;
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
  const [uploadError, setUploadError] = useState<string | null>(null);

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
      const message = err instanceof Error ? err.message : "Upload failed. Please try again.";
      setUploadError(message);
    },
  });

  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      setUploadError(null);
      for (const file of acceptedFiles) {
        setUploadQueue((q) => [...q, file.name]);
        uploadMutation.mutate(file, {
          onSettled: () => {
            setUploadQueue((q) => q.filter((n) => n !== file.name));
          },
        });
      }
    },
    [uploadMutation]
  );

  const onDropRejected = useCallback((rejectedFiles: FileRejection[]) => {
    const messages = rejectedFiles.flatMap((r) =>
      r.errors.map((e) =>
        e.code === "file-too-large" ? `${r.file.name} exceeds the 50 MB size limit` : e.message
      )
    );
    setUploadError(messages.join("; "));
  }, []);

  const isBackendDown = !!error;

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    onDropRejected,
    noClick: isBackendDown,
    noDrag: isBackendDown,
    disabled: isBackendDown,
    maxSize: 50 * 1024 * 1024,
    accept: {
      "application/pdf": [".pdf"],
      "application/json": [".json"],
      "application/xml": [".xml"],
      "text/csv": [".csv"],
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
    },
  });

  const handleDelete = useCallback((doc: Document) => {
    if (window.confirm(`Delete "${doc.filename}"? This action cannot be undone.`)) {
      alert("Delete not yet implemented — backend endpoint pending.");
    }
  }, []);

  const documents: Document[] = data?.data ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Documents</h1>
        <p className="mt-1 text-sm text-gray-400">Upload and manage integration documents</p>
      </div>

      {error && (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-4 text-sm text-amber-400">
          Backend unavailable. Uploads disabled.
        </div>
      )}

      {uploadError && (
        <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-4 text-sm text-red-400">
          {uploadError}
        </div>
      )}

      {/* Drop zone */}
      <div
        {...getRootProps()}
        className={clsx(
          "card border-2 border-dashed p-10 text-center transition-all",
          isBackendDown
            ? "cursor-not-allowed opacity-50 border-gray-700"
            : isDragActive
              ? "cursor-pointer border-indigo-500 bg-indigo-500/5"
              : "group cursor-pointer border-gray-700 hover:border-gray-500"
        )}
      >
        <input {...getInputProps()} />
        <div className="flex flex-col items-center gap-3">
          <div
            className={clsx(
              "rounded-full p-3 transition-colors",
              isDragActive
                ? "bg-indigo-500/20 text-indigo-400"
                : "bg-gray-800 text-gray-400 group-hover:text-gray-300"
            )}
          >
            <Upload className="h-6 w-6" />
          </div>
          <div>
            <p className="font-medium text-gray-300">
              {isBackendDown
                ? "Upload unavailable — backend offline"
                : isDragActive
                  ? "Drop files here..."
                  : "Drag & drop files, or click to browse"}
            </p>
            <p className="mt-1 text-xs text-gray-500">
              PDF, JSON, XML, CSV, XLSX supported &middot; max 50 MB
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
            {!isLoading && (
              <span className="text-sm font-normal text-gray-500">({documents.length})</span>
            )}
          </h3>
        </div>

        {isLoading ? (
          <div className="divide-y divide-gray-800/60">
            {Array.from({ length: 4 }).map((_, i) => (
              <div
                // biome-ignore lint/suspicious/noArrayIndexKey: skeleton rows have no stable id
                key={i}
                className="flex items-center gap-4 px-6 py-4"
              >
                <div className="h-8 w-8 animate-pulse rounded-lg bg-gray-800" />
                <div className="flex-1 space-y-2">
                  <div className="h-4 w-48 animate-pulse rounded bg-gray-800" />
                  <div className="h-3 w-32 animate-pulse rounded bg-gray-800" />
                </div>
                <div className="h-5 w-20 animate-pulse rounded-full bg-gray-800" />
              </div>
            ))}
          </div>
        ) : documents.length === 0 ? (
          <div className="flex flex-col items-center gap-3 px-6 py-16 text-center">
            <div className="rounded-full bg-gray-800 p-4">
              <Upload className="h-6 w-6 text-gray-500" />
            </div>
            <p className="font-medium text-gray-400">No documents yet.</p>
            <p className="text-sm text-gray-500">
              Upload your first document using the drop zone above.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-gray-800/60">
            {documents.map((doc) => {
              const st = statusConfig[doc.status] ?? {
                label: doc.status,
                icon: Clock,
                cls: "badge-gray",
              };
              const IconFile = fileIcon(doc.file_type);
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
                    <p className="truncate font-medium text-gray-200">{doc.filename}</p>
                    <p className="text-xs text-gray-500">
                      {doc.file_type.toUpperCase()} &middot; {formatDate(doc.created_at)}
                    </p>
                  </div>
                  <span className={st.cls}>
                    <StatusIcon
                      className={clsx(
                        "mr-1 h-3 w-3",
                        doc.status === "processing" && "animate-spin"
                      )}
                    />
                    {st.label}
                  </span>
                  <button
                    type="button"
                    onClick={() => handleDelete(doc)}
                    className="text-gray-600 hover:text-gray-400 transition-colors"
                    aria-label={`Delete ${doc.filename}`}
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
