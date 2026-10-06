import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, afterEach } from "vitest";
import { OutcomeCard } from "./OutcomeCard";
import type { Outcome, Workspace } from "../types";
import * as client from "../api";

const item: Outcome = { id: "synthetic-item", kind: "action", title: "Review close controls", body: "Review controls by Friday", labels: ["meeting-action"], status: "draft", owner_id: null, assignee_hint: "Alex", due_hint: "by Friday", due_date: null, confidence: .6, version: 1, evidence: [{ id: "source", i: 0, text: "Alex: Action: Review controls by Friday.", speaker: "Alex", start_line: 2 }] };
const workspace: Workspace = { id: "workspace", name: "Finance", department: "finance", role: "owner" };
function show(role: Workspace["role"] = "owner", onSaved = vi.fn()) { render(<OutcomeCard item={item} participants={[]} workspace={{ ...workspace, role }} meetingId="meeting" selected={false} onSelect={vi.fn()} onDirty={vi.fn()} onSaved={onSaved} />); return onSaved; }
afterEach(() => vi.restoreAllMocks());
describe("outcome review", () => {
  it("keeps approved review separate from personal execution completion", () => {
    render(<OutcomeCard item={{ ...item, status: "approved" }} participants={[]} workspace={workspace} meetingId="meeting" selected={false} onSelect={vi.fn()} onDirty={vi.fn()} onSaved={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Mark done" })).toBeNull();
    expect(screen.getByText(/Track your own progress in My day/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Return to draft" })).toBeEnabled();
  });
  it("keeps owner and relative date suggestions distinct from confirmed fields", () => {
    show(); expect(screen.getByText(/Suggested owner: Alex/)).toBeInTheDocument(); expect(screen.getByText(/Date needs review/)).toBeInTheDocument();
    expect(screen.getByText("Alex: Action: Review controls by Friday.")).toBeInTheDocument();
    expect(screen.queryByText(/60%|confidence/i)).toBeNull();
  });
  it("sends the current version when a reviewer approves", async () => {
    const request = vi.spyOn(client, "api").mockResolvedValue({}); const saved = show();
    await userEvent.click(screen.getByRole("button", { name: "Approve outcome" }));
    await waitFor(() => expect(saved).toHaveBeenCalled());
    expect(JSON.parse(String(request.mock.calls[0][1]?.body))).toEqual({ expected_version: 1, status: "approved" });
  });
  it("retains edits and displays a stale version failure", async () => {
    vi.spyOn(client, "api").mockRejectedValue(new client.ApiError(409, "Outcome changed; reload before saving"));
    show(); await userEvent.click(screen.getByText("Review fields")); const title = screen.getByLabelText("Title");
    await userEvent.clear(title); await userEvent.type(title, "Keep my human edit"); await userEvent.click(screen.getByRole("button", { name: "Save review" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Outcome changed");
    expect(title).toHaveValue("Keep my human edit");
  });
  it("does not offer approval to an editor or editing to a viewer", () => {
    show("viewer"); expect(screen.queryByRole("button", { name: "Approve outcome" })).toBeNull();
    expect(screen.getByLabelText("Title")).toBeDisabled();
  });
});
