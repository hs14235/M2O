import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import * as client from "../api";
import DailyPlanner from "./DailyPlanner";
import type { DailyPlan, Workspace } from "../types";

const workspace: Workspace = { id: "space", name: "People", department: "hr", role: "owner" };
const plan: DailyPlan = { entries: [{ id: "plan", item_id: "action", title: "Prepare checklist", meeting_id: "weekly", meeting_title: "Onboarding", kind: "action", item_version: 2, review_status: "approved", due_date: null, due_hint: "next week", planned_on: "2026-10-03", state: "planned", priority: 2, version: 1, reviewed_version: 2, stale: false, can_reconfirm: true }], candidates: [], entries_truncated: false, candidates_truncated: false };
afterEach(() => vi.restoreAllMocks());

it("updates execution progress with expected versions without changing review status", async () => {
  const request = vi.spyOn(client, "api").mockResolvedValue(plan);
  render(<DailyPlanner workspace={workspace} navigate={vi.fn()} />);
  await userEvent.selectOptions(await screen.findByLabelText("Progress for Prepare checklist"), "done");
  await waitFor(() => expect(request).toHaveBeenCalledWith(expect.stringContaining("/outcomes/action/plan"), expect.objectContaining({ method: "PATCH", body: expect.any(String) })));
  const patch = request.mock.calls.find(([, options]) => options?.method === "PATCH")!;
  expect(JSON.parse(patch[1]!.body as string)).toEqual({ expected_item_version: 2, expected_version: 1, planned_on: "2026-10-03", state: "done", priority: 2 });
});

it("blocks stale execution and sends the reader back to the source", async () => {
  vi.spyOn(client, "api").mockResolvedValue({ ...plan, entries: [{ ...plan.entries[0], stale: true, can_reconfirm: false }] });
  const navigate = vi.fn(); render(<DailyPlanner workspace={workspace} navigate={navigate} />);
  expect(await screen.findByLabelText("Progress for Prepare checklist")).toBeDisabled();
  expect(screen.queryByRole("button", { name: "Reconfirm current version" })).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "Review source" }));
  expect(navigate).toHaveBeenCalledWith("/workspaces/space/meetings/weekly/review");
});

it("bounds candidate rows and searches the fetched approved sources", async () => {
  vi.spyOn(client, "api").mockResolvedValue({ ...plan, candidates: Array.from({ length: 12 }, (_, i) => ({ ...plan.entries[0], item_id: "candidate-" + i, title: "Reviewed action " + i })) });
  render(<DailyPlanner workspace={workspace} navigate={vi.fn()} />);
  await screen.findByLabelText("Find reviewed work");
  expect(screen.getAllByRole("button", { name: "Add to this day" })).toHaveLength(8);
  await userEvent.click(screen.getByRole("button", { name: "Next reviewed items" }));
  expect(screen.getAllByRole("button", { name: "Add to this day" })).toHaveLength(4);
  await userEvent.type(screen.getByLabelText("Find reviewed work"), "action 11");
  expect(screen.getAllByRole("button", { name: "Add to this day" })).toHaveLength(1);
  expect(screen.getByText("Reviewed action 11")).toBeInTheDocument();
});
it("offers a read-only retry instead of claiming to load forever after a failed read", async () => {
  const request = vi.spyOn(client, "api").mockRejectedValueOnce(new client.ApiError(503, "Temporarily unavailable")).mockResolvedValue(plan);
  render(<DailyPlanner workspace={workspace} navigate={vi.fn()} />);
  await userEvent.click(await screen.findByRole("button", { name: "Try loading plan again" }));
  await screen.findByLabelText("Progress for Prepare checklist");
  expect(request).toHaveBeenCalledTimes(2);
  expect(request.mock.calls.every(([, options]) => !options?.method)).toBe(true);
});

it("recovers an accepted progress change with a read instead of sending it again", async () => {
  let reads = 0;
  const request = vi.spyOn(client, "api").mockImplementation(async (_path, options) => {
    if (options?.method) return {} as never;
    reads += 1;
    if (reads === 2) throw new client.ApiError(503, "Temporarily unavailable");
    return (reads === 1 ? plan : { ...plan, entries: [{ ...plan.entries[0], state: "done", version: 2 }] }) as never;
  });
  render(<DailyPlanner workspace={workspace} navigate={vi.fn()} />);
  await userEvent.selectOptions(await screen.findByLabelText("Progress for Prepare checklist"), "done");
  expect(await screen.findByText(/Your plan change was accepted/)).toBeInTheDocument();
  expect(screen.getByLabelText("Progress for Prepare checklist")).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "Load current plan" }));
  expect(await screen.findByText("Room to breathe.")).toBeInTheDocument();
  expect(request.mock.calls.filter(([, options]) => options?.method === "PATCH")).toHaveLength(1);
});

it("does not refresh or replace a new workspace after an earlier change finishes", async () => {
  let finish!: (value: never) => void;
  const request = vi.spyOn(client, "api").mockImplementation((path, options) => {
    if (options?.method) return new Promise(resolve => { finish = resolve; });
    return Promise.resolve((path.includes("/another/") ? { ...plan, entries: [{ ...plan.entries[0], title: "Other workspace action" }] } : plan) as never);
  });
  const view = render(<DailyPlanner workspace={workspace} navigate={vi.fn()} />);
  await userEvent.selectOptions(await screen.findByLabelText("Progress for Prepare checklist"), "done");
  view.rerender(<DailyPlanner workspace={{ ...workspace, id: "another" }} navigate={vi.fn()} />);
  await screen.findByLabelText("Progress for Other workspace action");
  await act(async () => finish({} as never));
  expect(screen.getByLabelText("Progress for Other workspace action")).toBeEnabled();
  expect(request.mock.calls.filter(([path, options]) => path.includes("/space/") && !options?.method)).toHaveLength(1);
});
