import { ChevronLeft, ChevronRight } from "lucide-react";

interface PaginationProps {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
}

export default function Pagination({ page, pageSize, total, onPageChange }: PaginationProps) {
  const start = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);
  const totalPages = Math.ceil(total / pageSize);
  const hasPrev = page > 1;
  const hasNext = page < totalPages;

  if (total === 0) return null;

  return (
    <div
      className="flex items-center justify-between px-4 py-3"
      style={{ borderTop: "1px solid var(--color-border)" }}
    >
      <p className="text-[13px]" style={{ color: "var(--color-text-muted)" }}>
        Showing{" "}
        <span className="font-medium" style={{ color: "var(--color-text-secondary)" }}>
          {start}–{end}
        </span>{" "}
        of{" "}
        <span className="font-medium" style={{ color: "var(--color-text-secondary)" }}>
          {total}
        </span>
      </p>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => onPageChange(page - 1)}
          disabled={!hasPrev}
          aria-label="Previous page"
          className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[13px] font-medium transition-colors"
          style={{
            border: `1px solid ${hasPrev ? "var(--color-border-strong)" : "var(--color-border)"}`,
            color: hasPrev ? "var(--color-text-secondary)" : "var(--color-text-muted)",
            opacity: hasPrev ? 1 : 0.5,
            cursor: hasPrev ? "pointer" : "not-allowed",
          }}
        >
          <ChevronLeft className="h-3.5 w-3.5" />
          Prev
        </button>

        <span
          className="min-w-[60px] text-center text-[13px] tabular-nums"
          style={{ color: "var(--color-text-muted)" }}
        >
          {page} / {totalPages}
        </span>

        <button
          type="button"
          onClick={() => onPageChange(page + 1)}
          disabled={!hasNext}
          aria-label="Next page"
          className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[13px] font-medium transition-colors"
          style={{
            border: `1px solid ${hasNext ? "var(--color-border-strong)" : "var(--color-border)"}`,
            color: hasNext ? "var(--color-text-secondary)" : "var(--color-text-muted)",
            opacity: hasNext ? 1 : 0.5,
            cursor: hasNext ? "pointer" : "not-allowed",
          }}
        >
          Next
          <ChevronRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}
