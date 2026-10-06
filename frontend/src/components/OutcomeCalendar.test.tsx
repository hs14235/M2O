import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import * as client from "../api";
import type { CalendarEntry, Workspace } from "../types";
import OutcomeCalendar, { calendarDay } from "./OutcomeCalendar";

const workspace: Workspace = { id: "scope", name: "Synthetic", role: "owner", department: "engineering" };
function entry(id: string, changes: Partial<CalendarEntry> = {}): CalendarEntry {
  return { item_id: id, meeting_id: "meeting", meeting_title: "Planning", title: id, kind: "action", item_version: 2, meeting_version: 3, revision_number: 2, review_status: "approved", due_date: "2026-10-06", due_hint: null, scheduled: true, owner_name: "Morgan", owner_confirmed: true, personal_plan: null, ...changes };
}
afterEach(() => vi.restoreAllMocks());
it("keeps all outcome kinds, reviewed dates, ownership and personal execution distinct", async () => {
  const request = vi.spyOn(client, "api").mockResolvedValue({ entries: [entry("action"), entry("decision", { kind: "decision" }), entry("risk", { kind: "risk" }), entry("blocker", { kind: "blocker" }), entry("followup", { kind: "follow_up", due_date: null, scheduled: false, due_hint: "next Friday", owner_confirmed: false, owner_name: "Alex", personal_plan: { id: "plan", state: "done", planned_on: "2026-10-05", version: 1, reviewed_version: 2, stale: false } })], next_offset: null });
  const review = vi.fn(); render(<OutcomeCalendar workspace={workspace} meetingId="meeting" onReview={review} onBack={vi.fn()} />);
  expect(await screen.findByText(/5 approved outcomes loaded/)).toBeInTheDocument();
  for (const name of ["action", "decision", "risk", "blocker"]) expect(screen.getByRole("heading", { name, level: 3 })).toBeInTheDocument();
  expect(request.mock.calls[0][0]).toContain("meeting_id=meeting");
  fireEvent.click(screen.getByRole("button", { name: "Undated · 1" }));
  expect(screen.getByText("Date needs review: next Friday")).toBeInTheDocument();
  expect(screen.getByText("Unassigned")).toBeInTheDocument();
  expect(screen.getByText(/Your personal plan: Done/)).toHaveTextContent("separate from the shared deadline");
  fireEvent.click(screen.getByRole("button", { name: "Review outcome and date" }));
  expect(review).toHaveBeenCalledWith(expect.objectContaining({ item_id: "followup", due_date: null }));
});
it("discards a late meeting response when scope changes", async () => {
  let resolve!: (value: unknown) => void;
  vi.spyOn(client, "api").mockImplementationOnce(() => new Promise(value => { resolve = value; })).mockResolvedValueOnce({ entries: [entry("current")], next_offset: null });
  const props = { workspace, onReview: vi.fn(), onBack: vi.fn() };
  const view = render(<OutcomeCalendar {...props} meetingId="first" />);
  view.rerender(<OutcomeCalendar {...props} meetingId="second" />);
  expect(await screen.findByRole("heading", { name: "current" })).toBeInTheDocument();
  await act(async () => resolve({ entries: [entry("private stale")], next_offset: null }));
  expect(screen.queryByText("private stale")).not.toBeInTheDocument();
});
it("rejects an inconsistent snapshot rather than drawing draft outcomes", async () => {
  vi.spyOn(client, "api").mockResolvedValue({ entries: [entry("unapproved", { review_status: "draft" })], next_offset: null });
  render(<OutcomeCalendar workspace={workspace} onReview={vi.fn()} onBack={vi.fn()} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("inconsistent snapshot");
  expect(screen.queryByRole("heading", { name: "unapproved" })).not.toBeInTheDocument();
});
it("loads additional records by identifier and shows incomplete feed status", async () => {
  const request = vi.spyOn(client, "api").mockResolvedValueOnce({ entries: [entry("first")], next_offset: 100 }).mockResolvedValueOnce({ entries: [entry("first"), entry("second")], next_offset: null });
  render(<OutcomeCalendar workspace={workspace} onReview={vi.fn()} onBack={vi.fn()} />);
  fireEvent.click(await screen.findByRole("button", { name: "Load more approved outcomes" }));
  expect(await screen.findByText(/2 approved outcomes loaded/)).not.toHaveTextContent("more outcomes available");
  expect(request.mock.calls[1][0]).toContain("offset=100");
});
it("interprets reviewed date-only values as local noon without a UTC day shift", () => {
  const date = calendarDay("2026-10-06");
  expect([date.getFullYear(), date.getMonth(), date.getDate(), date.getHours()]).toEqual([2026, 9, 6, 12]);
});
