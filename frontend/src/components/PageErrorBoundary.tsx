import { AlertTriangle, RotateCcw } from "lucide-react";
import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export default class PageErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[PageErrorBoundary]", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-1 items-center justify-center p-8">
          <div className="max-w-md text-center">
            <div
              className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full"
              style={{ backgroundColor: "rgba(220, 38, 38, 0.1)" }}
            >
              <AlertTriangle className="h-7 w-7" style={{ color: "var(--color-error-text)" }} />
            </div>
            <h2 className="text-lg font-semibold" style={{ color: "var(--color-text-primary)" }}>
              This page encountered an error
            </h2>
            <p className="mt-2 text-[13px]" style={{ color: "var(--color-text-secondary)" }}>
              {this.state.error?.message ?? "An unexpected error occurred."}
            </p>
            <button
              type="button"
              className="btn-primary mt-5"
              onClick={() => this.setState({ hasError: false, error: null })}
            >
              <RotateCcw className="h-4 w-4" />
              Try Again
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
