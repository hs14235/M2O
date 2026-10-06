import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import * as client from "../api";
import type { Integration, Meeting, User, Workspace } from "../types";
import { ShareStep } from "./ShareStep";

const workspace: Workspace = { id: "workspace", name: "People operations", role: "owner", department: "hr" };
const user: User = { id: "user", name: "Synthetic", email: "synthetic@example.test", capabilities: { demo_mode: true, linkedin_configured: false, ollama_model: null, embedding_provider: "hash", allowed_repos: [] }, linkedin: { connected: false, profile: null } };
const meeting = { id: "weekly", current_revision: 2, tasks: [{ id: "item", title: "Reviewed outcome", status: "approved", version: 3 }] } as Meeting;
const catalog = [{ id: "local", name: "Local handoff", purpose: "delivery", status: "ready", can_preview: true }, { id: "github", name: "GitHub", purpose: "delivery", status: "preview_only", can_preview: true }, { id: "jira", name: "Jira", purpose: "delivery", status: "unavailable", can_preview: false }] as Integration[];
const artifact = { filename: "weekly.md", content: "Reviewed local handoff", media_type: "text/markdown", snapshot_hash: "synthetic" };
const props = { meeting, workspace, user, selected: ["item"], onSelect: vi.fn(), onJob: vi.fn(), onBack: vi.fn(), onConnections: vi.fn() };
afterEach(() => vi.restoreAllMocks());
it("defaults to a local handoff, hides repository configuration, and sends reviewed versions", async () => {
  const request = vi.spyOn(client, "api").mockImplementation(async path => (path.endsWith("/integrations") ? catalog : artifact) as never);
  render(<ShareStep {...props} />);
  expect(await screen.findByRole("radio", { name: /Local handoff/ })).toBeChecked();
  expect(screen.getByRole("radio", { name: /Jira/ })).toBeDisabled();
  expect(screen.queryByLabelText("GitHub repository")).toBeNull();
  expect(screen.queryByRole("button", { name: "Prepare handoff" })).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "Continue to preparation" }));
  await userEvent.click(screen.getByRole("button", { name: "Prepare handoff" }));
  expect(await screen.findByRole("button", { name: "Download handoff" })).toBeEnabled();
  const body = JSON.parse(String(request.mock.calls.find(call => call[0].endsWith("/export"))?.[1]?.body));
  expect(body).toEqual({ format: "markdown", expected_revision: 2, versions: { item: 3 }, include_evidence: false });
});
it("drops an in-flight export when the approved selection changes", async () => {
  let finish!: (value: never) => void;
  vi.spyOn(client, "api").mockImplementation(path => path.endsWith("/integrations") ? Promise.resolve(catalog as never) : new Promise(resolve => { finish = resolve; }));
  const view = render(<ShareStep {...props} />);
  await screen.findByRole("radio", { name: /Local handoff/ });
  await userEvent.click(screen.getByRole("button", { name: "Continue to preparation" }));
  await userEvent.click(screen.getByRole("button", { name: "Prepare handoff" }));
  view.rerender(<ShareStep {...props} selected={[]} />);
  finish(artifact as never);
  await waitFor(() => expect(screen.getByRole("button", { name: "Prepare handoff" })).toBeDisabled());
  expect(screen.queryByRole("button", { name: "Download handoff" })).toBeNull();
});

it("does not claim a restored local receipt proves that a download succeeded", async () => {
  vi.spyOn(client, "api").mockResolvedValue(catalog);
  render(<ShareStep {...props} stage="receipt" provider="local" />);
  expect(screen.getByText(/A refresh does not prove that a file was saved/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Download again" })).toBeNull();
});
