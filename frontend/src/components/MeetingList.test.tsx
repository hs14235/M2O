import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import MeetingList from "./MeetingList";
import type { MeetingSummary } from "../types";

it("preserves matching titles as distinct records and opens the selected identifier", () => {
  const meetings: MeetingSummary[] = ["first", "second"].map(id => ({ id, record_id: id, title: "Release readiness", visibility: "restricted", version: 1, current_revision: 1, occurred_on: null, timezone: "UTC", created_at: "2026-10-05T12:00:00Z" }));
  const open = vi.fn(), query = vi.fn();
  render(<MeetingList meetings={meetings} query="" onQuery={query} loading={false} hasMore onMore={vi.fn()} onOpen={open} visitor={false} />);
  expect(screen.getAllByText("Release readiness")).toHaveLength(2);
  fireEvent.click(screen.getByText("second")); expect(open).toHaveBeenCalledWith("second");
  fireEvent.click(screen.getByRole("button", { name: "Group matching titles" }));
  expect(screen.getByText("Release readiness · 2 loaded records")).toBeInTheDocument();
  expect(screen.getByText("first")).toBeInTheDocument(); expect(screen.getByText("second")).toBeInTheDocument();
  fireEvent.change(screen.getByRole("searchbox"), { target: { value: "Release" } }); expect(query).toHaveBeenCalledWith("Release");
  expect(screen.getByRole("status")).toHaveTextContent("more records available");
});
