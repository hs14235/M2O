import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import * as client from "../api";
import type { Outcome, Workspace } from "../types";
import { JiraPublisher } from "./JiraPublisher";

const workspace: Workspace = { id: "workspace", name: "Engineering", role: "owner", department: "engineering" };
const item = { id: "item", title: "Reviewed task", version: 2, status: "approved" } as Outcome;
const destination = { project_key: "M2O", project_name: "Synthetic project", resource_url: "https://synthetic.atlassian.net", version: 2 };
const metadata = { destination, issue: null, issue_types: [{ id: "10001", name: "Task" }], fields: [{ id: "summary", name: "Summary", control: "text", required: true, has_default: false, options: [] }, { id: "description", name: "Description", control: "textarea", required: false, has_default: false, options: [] }] };
const preview = { id: "proposal", action: "create", destination, payload_hash: "a".repeat(64), payload: { fields: { summary: "Reviewed task", description: { type: "doc" } } }, expires_at: new Date(Date.now() + 100000).toISOString() };
afterEach(() => vi.restoreAllMocks());

function mock(extraFields = metadata.fields) {
  return vi.spyOn(client, "api").mockImplementation(async (path, options) => {
    if (path.endsWith("/jira/deliveries")) return [];
    if (path.includes("/metadata")) return { ...metadata, fields: path.includes("issue_type_id") ? extraFields : [] };
    if (path.endsWith("/jira/preview")) return preview;
    if (path.endsWith("/approve")) { expect(JSON.parse(options!.body as string)).toEqual({ payload_hash: preview.payload_hash, retry_rejected: false }); return { job_id: "job" }; }
    throw new Error("Unexpected request: " + path);
  });
}
async function fields() {
  await userEvent.click(screen.getByRole("button", { name: "Find available issue types" }));
  await userEvent.selectOptions(await screen.findByLabelText("Issue type"), "10001");
  await userEvent.click(screen.getByRole("button", { name: "Load issue fields" }));
  await screen.findByRole("button", { name: "Generate exact Jira preview" });
}

it("discovers fields, displays an exact preview and approves only its hash", async () => {
  const request = mock(), onJob = vi.fn();
  render(<JiraPublisher workspace={workspace} meetingId="meeting" selected={[item.id]} items={[item]} onJob={onJob} />);
  await fields(); await userEvent.click(screen.getByRole("button", { name: "Generate exact Jira preview" }));
  expect(await screen.findByText(/Snapshot hash/)).toBeInTheDocument();
  expect(screen.getByText(/daily-plan progress remains separate/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Approve exact preview and create Jira issue" }));
  await waitFor(() => expect(onJob).toHaveBeenCalledWith("job"));
  expect(screen.queryByText(/Snapshot hash/)).toBeNull();
  expect(screen.getByRole("button", { name: "Generate exact Jira preview" })).toBeEnabled();
  const call = request.mock.calls.find(([path]) => path.endsWith("/jira/preview"))!;
  expect(JSON.parse(call[1]!.body as string)).toMatchObject({ expected_item_version: 2, expected_destination_version: 2, include_evidence: false, action: "create" });
});

it("blocks a required unsupported field and explains the missing mapping", async () => {
  mock([...metadata.fields, { id: "assignee", name: "Assignee", required: true, has_default: false, control: "unsupported", options: [] }]);
  render(<JiraPublisher workspace={workspace} meetingId="meeting" selected={[item.id]} items={[item]} onJob={vi.fn()} />);
  await fields(); expect(screen.getByText(/cannot safely map yet: Assignee/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Generate exact Jira preview" })).toBeDisabled();
});

it("hides a stored preview when its reviewed outcome changes", async () => {
  mock(); const view = render(<JiraPublisher workspace={workspace} meetingId="meeting" selected={[item.id]} items={[item]} onJob={vi.fn()} />);
  await fields(); await userEvent.click(screen.getByRole("button", { name: "Generate exact Jira preview" })); await screen.findByText(/Snapshot hash/);
  view.rerender(<JiraPublisher workspace={workspace} meetingId="meeting" selected={[item.id]} items={[{ ...item, version: 3 }]} onJob={vi.fn()} />);
  expect(screen.queryByText(/Snapshot hash/)).toBeNull();
});

it("discards a late preview response after selection changes", async () => {
  const request = mock(); let finish!: (value: unknown) => void;
  const view = render(<JiraPublisher workspace={workspace} meetingId="meeting" selected={[item.id]} items={[item]} onJob={vi.fn()} />);
  await fields(); const normal = request.getMockImplementation()!;
  request.mockImplementation((path, options) => path.endsWith("/jira/preview") ? new Promise(resolve => { finish = resolve; }) : normal(path, options));
  await userEvent.click(screen.getByRole("button", { name: "Generate exact Jira preview" }));
  view.rerender(<JiraPublisher workspace={workspace} meetingId="meeting" selected={[]} items={[item]} onJob={vi.fn()} />);
  await act(async () => finish(preview));
  expect(screen.queryByText(/Snapshot hash/)).toBeNull();
});
it("does not accept a pending preview after leaving and returning to preparation", async () => {
  const request = mock(); let finish!: (value: unknown) => void;
  const onStage = vi.fn(), props = { workspace, meetingId: "meeting", selected: [item.id], items: [item], onJob: vi.fn(), onStage };
  const view = render(<JiraPublisher {...props} stage="configure" />);
  await fields(); const normal = request.getMockImplementation()!;
  request.mockImplementation((path, options) => path.endsWith("/jira/preview") ? new Promise(resolve => { finish = resolve; }) : normal(path, options));
  await userEvent.click(screen.getByRole("button", { name: "Generate exact Jira preview" }));
  view.rerender(<JiraPublisher {...props} stage="choose" />);
  view.rerender(<JiraPublisher {...props} stage="configure" />);
  await act(async () => finish(preview));
  expect(onStage).not.toHaveBeenCalled();
  view.rerender(<JiraPublisher {...props} stage="preview" />);
  expect(screen.queryByRole("button", { name: /Approve exact preview/ })).toBeNull();
});
it("does not report empty delivery history when its read failed", async () => {
  const request = mock(), normal = request.getMockImplementation()!; let reads = 0;
  request.mockImplementation((path, options) => path.endsWith("/jira/deliveries") && ++reads === 1 ? Promise.reject(new client.ApiError(503, "History unavailable")) : normal(path, options));
  render(<JiraPublisher workspace={workspace} meetingId="meeting" selected={[]} items={[item]} onJob={vi.fn()} stage="receipt" />);
  const refresh = await screen.findByRole("button", { name: "Refresh Jira receipts" });
  expect(screen.queryByText("No recorded Jira deliveries are available for this meeting.")).toBeNull();
  await userEvent.click(refresh);
  await screen.findByText("No recorded Jira deliveries are available for this meeting.");
  expect(request.mock.calls.every(([, options]) => !options?.method)).toBe(true);
});
