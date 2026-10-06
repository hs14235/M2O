import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { Publisher } from "./Publisher";
import * as client from "../api";
import type { Outcome, User, Workspace } from "../types";

const user: User = { id: "user", name: "Synthetic", email: "synthetic@example.test", capabilities: { demo_mode: true, linkedin_configured: false, ollama_model: null, embedding_provider: "hash", allowed_repos: [] }, linkedin: { connected: false, profile: null } };
const workspace: Workspace = { id: "workspace", name: "Engineering", role: "owner", department: "engineering" };
const item = { id: "item", title: "Reviewed task", version: 2, status: "approved" } as Outcome;
const preview = { id: "proposal", repo: "demo/example", payload_hash: "a".repeat(64), expires_at: new Date(Date.now() + 100000).toISOString(), would_create: [{ title: "Reviewed task", body: "Exact body\n<!-- marker -->", labels: ["meeting-action"] }], approved: false };
afterEach(() => vi.restoreAllMocks());

it("labels an unconfigured destination as preview only even outside demo mode", () => {
  render(<Publisher workspace={workspace} user={{ ...user, capabilities: { ...user.capabilities, demo_mode: false, allowed_repos: ["demo/example"] } }} meetingId="meeting" selected={["item"]} items={[item]} onJob={vi.fn()} publicationEnabled={false} />);
  expect(screen.getByText("Preview only")).toBeInTheDocument();
  expect(screen.queryByText("Publication enabled")).toBeNull();
});

it("shows the exact payload and blocks external publication in demo mode", async () => {
  const request = vi.spyOn(client, "api").mockResolvedValue(preview);
  render(<Publisher workspace={workspace} user={user} meetingId="meeting" selected={["item"]} items={[item]} onJob={vi.fn()} />);
  await userEvent.click(screen.getByRole("button", { name: "Generate exact preview" }));
  await waitFor(() => expect(screen.getByText(/Exact body/, { selector: "pre.payload-text" })).toHaveTextContent("<!-- marker -->"));
  expect(screen.getByRole("button", { name: /Approve exact preview/ })).toBeDisabled();
  expect(request).toHaveBeenCalledTimes(1);
});

it("invalidates a preview when selection or an outcome version changes", async () => {
  vi.spyOn(client, "api").mockResolvedValue(preview);
  const view = render(<Publisher workspace={workspace} user={user} meetingId="meeting" selected={["item"]} items={[item]} onJob={vi.fn()} />);
  await userEvent.click(screen.getByRole("button", { name: "Generate exact preview" })); await screen.findByText(/Snapshot hash/);
  view.rerender(<Publisher workspace={workspace} user={user} meetingId="meeting" selected={[]} items={[{ ...item, version: 3 }]} onJob={vi.fn()} />);
  await waitFor(() => expect(screen.queryByText(/Snapshot hash/)).toBeNull());
});

it("ignores a late preview response for a previous selection", async () => {
  let finish!: (value: unknown) => void;
  vi.spyOn(client, "api").mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  const view = render(<Publisher workspace={workspace} user={user} meetingId="meeting" selected={["item"]} items={[item]} onJob={vi.fn()} />);
  await userEvent.click(screen.getByRole("button", { name: "Generate exact preview" }));
  view.rerender(<Publisher workspace={workspace} user={user} meetingId="meeting" selected={[]} items={[item]} onJob={vi.fn()} />);
  finish(preview);
  await waitFor(() => expect(screen.getByRole("button", { name: "Generate exact preview" })).toBeDisabled());
  expect(screen.queryByText(/Snapshot hash/)).toBeNull();
});
it("does not navigate on a late preview after Back and return to preparation", async () => {
  let finish!: (value: unknown) => void;
  vi.spyOn(client, "api").mockImplementation(path => path.endsWith("/integrations/github") ? Promise.resolve({ can_publish: false, destination: null }) : path.endsWith("/deliveries/github") ? Promise.resolve([]) : new Promise(resolve => { finish = resolve; }));
  const onStage = vi.fn(), props = { workspace, user, meetingId: "meeting", selected: ["item"], items: [item], onJob: vi.fn(), onStage };
  const view = render(<Publisher {...props} stage="configure" />);
  await waitFor(() => expect(screen.getByRole("button", { name: "Generate exact preview" })).toBeEnabled());
  await userEvent.click(screen.getByRole("button", { name: "Generate exact preview" }));
  view.rerender(<Publisher {...props} stage="choose" />);
  view.rerender(<Publisher {...props} stage="configure" />);
  await act(async () => finish(preview));
  expect(onStage).not.toHaveBeenCalled();
  view.rerender(<Publisher {...props} stage="preview" />);
  expect(screen.getByText(/There is no current preview/)).toBeInTheDocument();
});
it("shows a content conflict with the verified issue link and allows only a read-only check", async () => {
  const receipt = { operation_id: "operation", proposal_id: "proposal", state: "failed", repo: "demo/example", can_reconcile: true, can_retry_rejected: false, results: [{ item_id: "item", version: 2, status: "conflict", provider_effect: "created", number: 12, url: "https://github.com/demo/example/issues/12", error: "Content differs" }] };
  const request = vi.spyOn(client, "api").mockImplementation(async path => path.endsWith("/integrations/github") ? { can_publish: false, destination: null } : path.endsWith("/deliveries/github") ? [receipt] : {});
  render(<Publisher workspace={workspace} user={user} meetingId="meeting" selected={[]} items={[item]} onJob={vi.fn()} stage="receipt" />);
  expect(await screen.findByText(/An issue exists, but its content differs/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Open issue 12 in GitHub" })).toHaveAttribute("href", receipt.results[0].url);
  expect(screen.queryByRole("button", { name: /retry|publish|overwrite/i })).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "Check existing GitHub delivery" }));
  expect(request.mock.calls.filter(([, options]) => options?.method === "POST").map(([path]) => path)).toEqual(["/workspaces/workspace/operations/operation/reconcile"]);
});
it("recovers a failed receipt read without sending an issue", async () => {
  let reads = 0;
  const request = vi.spyOn(client, "api").mockImplementation(async path => {
    if (path.endsWith("/integrations/github")) return { can_publish: false, destination: null };
    if (++reads === 1) throw new client.ApiError(503, "History unavailable");
    return [];
  });
  render(<Publisher workspace={workspace} user={user} meetingId="meeting" selected={[]} items={[item]} onJob={vi.fn()} stage="receipt" />);
  await userEvent.click(await screen.findByRole("button", { name: "Refresh GitHub receipts" }));
  await screen.findByText("No GitHub delivery has been recorded for this meeting.");
  expect(request.mock.calls.every(([, options]) => !options?.method)).toBe(true);
});
it("invalidates an offline preview when meeting visibility changes without changing outcome versions", async () => {
  vi.spyOn(client, "api").mockResolvedValue(preview);
  const props = { workspace, user, meetingId: "meeting", selected: ["item"], items: [item], onJob: vi.fn() };
  const view = render(<Publisher {...props} visibility="workspace" />);
  await userEvent.click(screen.getByRole("button", { name: "Generate exact preview" }));
  await screen.findByText(/Snapshot hash/);
  view.rerender(<Publisher {...props} visibility="restricted" />);
  expect(screen.queryByRole("button", { name: /Approve exact preview/ })).toBeNull();
  expect(screen.getByRole("checkbox", { name: /I approve sharing/ })).not.toBeChecked();
});
