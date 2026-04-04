import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import Pagination from "../Pagination";

function renderPagination(page: number, pageSize: number, total: number, onPageChange = vi.fn()) {
  return { onPageChange, ...render(<Pagination page={page} pageSize={pageSize} total={total} onPageChange={onPageChange} />) };
}

describe("Pagination", () => {
  it("returns null when total is 0", () => {
    const { container } = renderPagination(1, 10, 0);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows correct range on first page", () => {
    renderPagination(1, 10, 35);
    expect(screen.getByText("1–10")).toBeInTheDocument();
    expect(screen.getByText("35")).toBeInTheDocument();
  });

  it("shows correct range on middle page", () => {
    renderPagination(2, 10, 35);
    expect(screen.getByText("11–20")).toBeInTheDocument();
  });

  it("shows correct range on last page (partial)", () => {
    renderPagination(4, 10, 35);
    expect(screen.getByText("31–35")).toBeInTheDocument();
  });

  it("shows correct page indicator", () => {
    renderPagination(2, 10, 35);
    expect(screen.getByText("2 / 4")).toBeInTheDocument();
  });

  it("disables Prev button on first page", () => {
    renderPagination(1, 10, 30);
    expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled();
  });

  it("disables Next button on last page", () => {
    renderPagination(3, 10, 30);
    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
  });

  it("enables both buttons on a middle page", () => {
    renderPagination(2, 10, 30);
    expect(screen.getByRole("button", { name: "Previous page" })).not.toBeDisabled();
    expect(screen.getByRole("button", { name: "Next page" })).not.toBeDisabled();
  });

  it("calls onPageChange with page - 1 when Prev is clicked", async () => {
    const { onPageChange } = renderPagination(3, 10, 30);
    await userEvent.click(screen.getByRole("button", { name: "Previous page" }));
    expect(onPageChange).toHaveBeenCalledWith(2);
  });

  it("calls onPageChange with page + 1 when Next is clicked", async () => {
    const { onPageChange } = renderPagination(1, 10, 30);
    await userEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(onPageChange).toHaveBeenCalledWith(2);
  });

  it("does not call onPageChange when Prev is clicked on first page", async () => {
    const { onPageChange } = renderPagination(1, 10, 30);
    await userEvent.click(screen.getByRole("button", { name: "Previous page" }));
    expect(onPageChange).not.toHaveBeenCalled();
  });

  it("does not call onPageChange when Next is clicked on last page", async () => {
    const { onPageChange } = renderPagination(3, 10, 30);
    await userEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(onPageChange).not.toHaveBeenCalled();
  });
});
