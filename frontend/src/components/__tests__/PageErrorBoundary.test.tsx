import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import PageErrorBoundary from "../PageErrorBoundary";

function ThrowingChild({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) {
    throw new Error("test page crash");
  }
  return <div data-testid="child-content">Page loaded</div>;
}

describe("PageErrorBoundary", () => {
  it("renders children when no error occurs", () => {
    render(
      <PageErrorBoundary>
        <ThrowingChild shouldThrow={false} />
      </PageErrorBoundary>,
    );
    expect(screen.getByTestId("child-content")).toBeInTheDocument();
  });

  it("shows error UI when child throws", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});

    render(
      <PageErrorBoundary>
        <ThrowingChild shouldThrow={true} />
      </PageErrorBoundary>,
    );

    expect(screen.getByText("This page encountered an error")).toBeInTheDocument();
    expect(screen.getByText("test page crash")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
    expect(screen.queryByTestId("child-content")).not.toBeInTheDocument();

    vi.restoreAllMocks();
  });

  it("resets error state when Try Again is clicked without reloading the page", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const reloadSpy = vi.fn();
    Object.defineProperty(window, "location", {
      value: { ...window.location, reload: reloadSpy },
      writable: true,
    });

    let shouldThrow = true;
    function ConditionalThrow() {
      if (shouldThrow) {
        throw new Error("recoverable error");
      }
      return <div data-testid="recovered">Recovered</div>;
    }

    render(
      <PageErrorBoundary>
        <ConditionalThrow />
      </PageErrorBoundary>,
    );

    expect(screen.getByText("This page encountered an error")).toBeInTheDocument();

    // Fix the error condition before clicking Try Again
    shouldThrow = false;

    await userEvent.click(screen.getByRole("button", { name: /try again/i }));

    // Should re-render children, not reload the page
    expect(screen.getByTestId("recovered")).toBeInTheDocument();
    expect(reloadSpy).not.toHaveBeenCalled();

    vi.restoreAllMocks();
  });

  it("does not render a full-screen layout", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});

    const { container } = render(
      <PageErrorBoundary>
        <ThrowingChild shouldThrow={true} />
      </PageErrorBoundary>,
    );

    // PageErrorBoundary should NOT use h-screen (that's for the root ErrorBoundary)
    const wrapper = container.firstElementChild;
    expect(wrapper?.className).not.toContain("h-screen");

    vi.restoreAllMocks();
  });
});
