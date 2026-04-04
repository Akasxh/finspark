import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider, useToast } from "../Toast";

function Trigger({ message, variant }: { message: string; variant?: "success" | "error" | "warning" }) {
  const { toast } = useToast();
  return (
    <button type="button" onClick={() => toast(message, variant)}>
      show toast
    </button>
  );
}

function renderWithProvider(message: string, variant?: "success" | "error" | "warning") {
  return render(
    <ToastProvider>
      <Trigger message={message} variant={variant} />
    </ToastProvider>
  );
}

describe("ToastProvider", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    // Flush pending timers inside act so React can process state updates cleanly
    act(() => {
      vi.runOnlyPendingTimers();
    });
    vi.useRealTimers();
  });

  it("renders toast message when triggered", () => {
    renderWithProvider("Hello world");
    act(() => {
      fireEvent.click(screen.getByRole("button", { name: "show toast" }));
    });
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("Hello world")).toBeInTheDocument();
  });

  it("auto-dismisses after 4 seconds", () => {
    renderWithProvider("Bye soon");
    act(() => {
      fireEvent.click(screen.getByRole("button", { name: "show toast" }));
    });
    expect(screen.getByRole("alert")).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(4000);
    });

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("dismisses immediately when close button is clicked", () => {
    renderWithProvider("Dismiss me");
    act(() => {
      fireEvent.click(screen.getByRole("button", { name: "show toast" }));
    });
    expect(screen.getByRole("alert")).toBeInTheDocument();

    act(() => {
      fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("applies success variant styles", () => {
    renderWithProvider("All good", "success");
    act(() => {
      fireEvent.click(screen.getByRole("button", { name: "show toast" }));
    });
    expect(screen.getByRole("alert")).toHaveStyle({ color: "#34d399" });
  });

  it("applies error variant styles", () => {
    renderWithProvider("Something failed", "error");
    act(() => {
      fireEvent.click(screen.getByRole("button", { name: "show toast" }));
    });
    expect(screen.getByRole("alert")).toHaveStyle({ color: "#f87171" });
  });

  it("applies warning variant styles", () => {
    renderWithProvider("Watch out", "warning");
    act(() => {
      fireEvent.click(screen.getByRole("button", { name: "show toast" }));
    });
    expect(screen.getByRole("alert")).toHaveStyle({ color: "#fbbf24" });
  });

  it("defaults to success variant when no variant provided", () => {
    renderWithProvider("Default variant");
    act(() => {
      fireEvent.click(screen.getByRole("button", { name: "show toast" }));
    });
    expect(screen.getByRole("alert")).toHaveStyle({ color: "#34d399" });
  });
});

describe("useToast", () => {
  it("throws when used outside ToastProvider", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    function BadConsumer() {
      useToast();
      return null;
    }
    expect(() => render(<BadConsumer />)).toThrow("useToast must be used within a ToastProvider");
    consoleError.mockRestore();
  });
});
