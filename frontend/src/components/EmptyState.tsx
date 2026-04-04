import clsx from "clsx";
import type { LucideIcon } from "lucide-react";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
  };
  className?: string;
}

export default function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={clsx(
        "flex flex-col items-center justify-center gap-4 py-16 text-center",
        className
      )}
    >
      <div
        className="flex h-14 w-14 items-center justify-center rounded-xl"
        style={{
          backgroundColor: "var(--color-bg-elevated)",
          border: "1px solid var(--color-border)",
        }}
      >
        <Icon className="h-6 w-6" style={{ color: "var(--color-text-muted)" }} />
      </div>
      <div className="space-y-1">
        <p className="text-[13px] font-medium" style={{ color: "var(--color-text-secondary)" }}>
          {title}
        </p>
        {description && (
          <p className="text-xs max-w-xs" style={{ color: "var(--color-text-muted)" }}>
            {description}
          </p>
        )}
      </div>
      {action && (
        <button type="button" onClick={action.onClick} className="btn-primary">
          {action.label}
        </button>
      )}
    </div>
  );
}
