import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import * as client from "../api";
import { SlackPublisher } from "./SlackPublisher";
import type { Meeting, Workspace } from "../types";

const workspace: Workspace = { id: "space", name: "Synthetic", role: "owner", department: "hr" };
const meeting = { id: "weekly", current_revision: 2, visibility: "restricted", tasks: [{ id: "item", version: 3, status: "approved" }] } as Meeting;
const status = { can_create: true, can_update: true, version: 4, account: { team_name: "Synthetic team" }, destination: { channel_id: "C12345678", channel_name: "synthetic" } };
const proposal = { id: "proposal", action: "create", destination: { version: 4, team_name: "Synthetic team", channel_id: "C12345678", channel_name: "synthetic" }, payload: { text: "Exact fallback", blocks: [{ type: "section", text: { type: "plain_text", text: "Exact reviewed message" } }] }, payload_hash: "a".repeat(64), expires_at: new Date(Date.now() + 100000).toISOString(), target: null };
const props = { workspace, meeting, selected: ["item"], onStage: vi.fn(), onJob: vi.fn() };
afterEach(() => vi.restoreAllMocks());
function requests() {
  return vi.spyOn(client, "api").mockImplementation(async path => {
    if (path.endsWith("/integrations/slack")) return status;
    if (path.endsWith("/slack/deliveries")) return [];
    if (path.endsWith("/slack/preview")) return proposal;
    return { job_id: "job" };
  });
}
it("requires restricted disclosure, snapshots current versions, and approves only the stored hash", async () => {
  const request = requests(); const onStage = vi.fn();
  const view = render(<SlackPublisher {...props} onStage={onStage} stage="configure" />);
  const generate = await screen.findByRole("button", { name: "Generate exact Slack preview" });
  await waitFor(() => expect(screen.getByRole("combobox", { name: "Slack action" })).toBeEnabled());
  expect(generate).toBeDisabled();
  await userEvent.click(screen.getByRole("checkbox", { name: /I approve sharing/ })); await userEvent.click(generate);
  await waitFor(() => expect(onStage).toHaveBeenCalledWith("preview"));
  const body = request.mock.calls.find(([path]) => path.endsWith("/slack/preview"))![1]!.body;
  expect(JSON.parse(String(body))).toEqual({ action: "create", expected_revision: 2, versions: { item: 3 }, expected_destination_version: 4, include_evidence: false, confirm_restricted_share: true, target_operation_id: null });
  view.rerender(<SlackPublisher {...props} onStage={onStage} stage="preview" />);
  expect(screen.getByText("Exact reviewed message")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Approve exact preview and send Slack message" }));
  await waitFor(() => expect(onStage).toHaveBeenCalledWith("receipt"));
  expect(JSON.parse(String(request.mock.calls.find(([path]) => path.endsWith("/approve"))![1]!.body))).toEqual({ payload_hash: "a".repeat(64), retry_rejected: false });
});
it("ignores a late preview when source versions change", async () => {
  const request = requests(); let finish!: (value: unknown) => void;
  request.mockImplementation(path => path.endsWith("/integrations/slack") ? Promise.resolve(status) : path.endsWith("/slack/deliveries") ? Promise.resolve([]) : new Promise(resolve => { finish = resolve; }));
  const onStage = vi.fn(), view = render(<SlackPublisher {...props} meeting={{ ...meeting, visibility: "workspace" }} onStage={onStage} stage="configure" />);
  await waitFor(() => expect(screen.getByRole("combobox", { name: "Slack action" })).toBeEnabled());
  await userEvent.click(screen.getByRole("button", { name: "Generate exact Slack preview" }));
  view.rerender(<SlackPublisher {...props} meeting={{ ...meeting, current_revision: 3 }} onStage={onStage} stage="configure" />);
  await act(async () => finish(proposal)); expect(onStage).not.toHaveBeenCalled();
});
it("does not accept a pending preview after leaving and returning to preparation", async () => {
  const request = requests(); let finish!: (value: unknown) => void;
  request.mockImplementation(path => path.endsWith("/integrations/slack") ? Promise.resolve(status) : path.endsWith("/slack/deliveries") ? Promise.resolve([]) : new Promise(resolve => { finish = resolve; }));
  const onStage = vi.fn(), current = { ...props, meeting: { ...meeting, visibility: "workspace" as const }, onStage };
  const view = render(<SlackPublisher {...current} stage="configure" />);
  await waitFor(() => expect(screen.getByRole("button", { name: "Generate exact Slack preview" })).toBeEnabled());
  await userEvent.click(screen.getByRole("button", { name: "Generate exact Slack preview" }));
  view.rerender(<SlackPublisher {...current} stage="choose" />);
  view.rerender(<SlackPublisher {...current} stage="configure" />);
  await act(async () => finish(proposal));
  expect(onStage).not.toHaveBeenCalled();
  view.rerender(<SlackPublisher {...current} stage="preview" />);
  expect(screen.queryByRole("button", { name: /Approve exact preview/ })).toBeNull();
});
it("does not turn a failed receipt read into a resend or an empty-history claim", async () => {
  const request = requests(), normal = request.getMockImplementation()!; let reads = 0;
  request.mockImplementation((path, options) => path.endsWith("/slack/deliveries") && ++reads === 1 ? Promise.reject(new client.ApiError(503, "History unavailable")) : normal(path, options));
  render(<SlackPublisher {...props} stage="receipt" />);
  const refresh = await screen.findByRole("button", { name: "Refresh Slack receipts" });
  expect(screen.queryByText("No recorded Slack delivery is available for this meeting.")).toBeNull();
  await userEvent.click(refresh);
  await screen.findByText("No recorded Slack delivery is available for this meeting.");
  expect(request.mock.calls.every(([, options]) => !options?.method)).toBe(true);
});
it("invalidates a preview when the meeting becomes restricted without changing source versions", async () => {
  requests(); const onStage = vi.fn();
  const view = render(<SlackPublisher {...props} onStage={onStage} meeting={{ ...meeting, visibility: "workspace" }} stage="configure" />);
  const generate = await screen.findByRole("button", { name: "Generate exact Slack preview" });
  await waitFor(() => expect(generate).toBeEnabled()); await userEvent.click(generate);
  await waitFor(() => expect(onStage).toHaveBeenCalledWith("preview"));
  view.rerender(<SlackPublisher {...props} onStage={onStage} meeting={{ ...meeting, visibility: "workspace" }} stage="preview" />);
  expect(screen.getByText("Exact reviewed message")).toBeInTheDocument();
  view.rerender(<SlackPublisher {...props} onStage={onStage} meeting={meeting} stage="preview" />);
  expect(screen.queryByRole("button", { name: /Approve exact preview/ })).toBeNull();
});
