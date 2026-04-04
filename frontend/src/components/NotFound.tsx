import { AlertCircle, Home } from "lucide-react";
import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 py-24 text-center">
      <div
        className="flex h-16 w-16 items-center justify-center rounded-xl"
        style={{
          backgroundColor: "var(--color-bg-elevated)",
          border: "1px solid var(--color-border)",
        }}
      >
        <AlertCircle className="h-8 w-8" style={{ color: "var(--color-text-muted)" }} />
      </div>
      <div className="space-y-2">
        <h1 className="text-5xl font-bold" style={{ color: "var(--color-text-primary)" }}>
          404
        </h1>
        <p className="text-lg font-medium" style={{ color: "var(--color-text-secondary)" }}>
          Page not found
        </p>
        <p className="text-[13px] max-w-xs" style={{ color: "var(--color-text-muted)" }}>
          The page you&apos;re looking for doesn&apos;t exist or has been moved.
        </p>
      </div>
      <Link to="/" className="btn-primary">
        <Home className="h-4 w-4" />
        Back to Dashboard
      </Link>
    </div>
  );
}
