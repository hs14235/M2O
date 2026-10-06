import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import * as client from "../api";
import JiraConnection from "./JiraConnection";
import type { Workspace } from "../types";

const workspace: Workspace = { id: "workspace", name: "Engineering", department: "engineering", role: "owner" };
const status = { configured: true, can_manage: true, state: "connected", version: 3, destination: null };
afterEach(() => vi.restoreAllMocks());

it("requires an explicit site and verifies a versioned destination without issuing a task", async () => {
  const request = vi.spyOn(client, "api").mockImplementation(async path => path.endsWith("/sites") ? [{ id: "site", name: "Synthetic site", url: "https://synthetic.atlassian.net" }] : status);
  render(<JiraConnection workspace={workspace} />);
  await userEvent.click(await screen.findByRole("button", { name: "Find authorized Jira sites" }));
  await userEvent.type(await screen.findByLabelText("Space key"), "m2o");
  await userEvent.click(screen.getByRole("button", { name: "Verify and save destination" }));
  await screen.findByText("Destination verified and saved. No issue was created.");
  const post = request.mock.calls.find(([path]) => path.endsWith("/destination"))!;
  expect(JSON.parse(post[1]!.body as string)).toEqual({ resource_id: "site", project_key: "M2O", expected_version: 3 });
  expect(request.mock.calls.some(([path]) => path.includes("/issue"))).toBe(false);
});

it("disables connection and discovery in demo mode", async () => {
  vi.spyOn(client, "api").mockResolvedValue({ ...status, can_manage: false, state: "disconnected" });
  render(<JiraConnection workspace={workspace} />);
  expect(await screen.findByRole("button", { name: "Connect Jira" })).toBeDisabled();
  expect(screen.queryByRole("button", { name: "Find authorized Jira sites" })).toBeNull();
});

it("disconnects the workspace and displays request errors without success", async () => {
  const request = vi.spyOn(client, "api").mockResolvedValue(status);
  render(<JiraConnection workspace={workspace} />);
  const button = await screen.findByRole("button", { name: "Disconnect from this workspace" });
  request.mockRejectedValueOnce(new client.ApiError(503, "Credential storage unavailable"));
  await userEvent.click(button);
  await screen.findByText("Credential storage unavailable");
  expect(screen.queryByText(/Disconnected from this workspace/)).toBeNull();
  request.mockResolvedValueOnce({ ok: true }).mockResolvedValueOnce({ ...status, state: "disconnected" });
  await userEvent.click(button);
  await waitFor(() => expect(screen.getByRole("button", { name: "Connect Jira" })).toBeEnabled());
  expect(request).toHaveBeenCalledWith("/workspaces/workspace/integrations/jira", expect.objectContaining({ method: "DELETE" }));
});
