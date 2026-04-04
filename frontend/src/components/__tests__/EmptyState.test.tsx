import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FileText } from "lucide-react";
import { describe, expect, it, vi } from "vitest";
import EmptyState from "../EmptyState";

describe("EmptyState", () => {
  it("renders the title", () => {
    render(<EmptyState icon={FileText} title="No documents found" />);
    expect(screen.getByText("No documents found")).toBeInTheDocument();
  });

  it("renders the description when provided", () => {
    render(
      <EmptyState
        icon={FileText}
        title="No documents"
        description="Upload your first document to get started."
      />
    );
    expect(screen.getByText("Upload your first document to get started.")).toBeInTheDocument();
  });

  it("does not render description when omitted", () => {
    render(<EmptyState icon={FileText} title="No documents" />);
    expect(screen.queryByText(/upload/i)).not.toBeInTheDocument();
  });

  it("renders the icon as an SVG element", () => {
    const { container } = render(<EmptyState icon={FileText} title="No documents" />);
    expect(container.querySelector("svg")).toBeInTheDocument();
  });

  it("renders action button with correct label when action is provided", () => {
    render(
      <EmptyState
        icon={FileText}
        title="No documents"
        action={{ label: "Upload Document", onClick: vi.fn() }}
      />
    );
    expect(screen.getByRole("button", { name: "Upload Document" })).toBeInTheDocument();
  });

  it("calls action.onClick when action button is clicked", async () => {
    const onClick = vi.fn();
    render(
      <EmptyState
        icon={FileText}
        title="No documents"
        action={{ label: "Upload Document", onClick }}
      />
    );
    await userEvent.click(screen.getByRole("button", { name: "Upload Document" }));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("does not render action button when action prop is not provided", () => {
    render(<EmptyState icon={FileText} title="No documents" />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("applies custom className", () => {
    const { container } = render(
      <EmptyState icon={FileText} title="No documents" className="custom-class" />
    );
    expect(container.firstChild).toHaveClass("custom-class");
  });
});
