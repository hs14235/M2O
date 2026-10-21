import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import * as client from "../api";
import type { User, Workspace } from "../types";
import SidebarTools from "./SidebarTools";

const workspace: Workspace = { id: "space", name: "Synthetic", role: "owner", department: "engineering" };
const user: User = {
  id: "u",
  name: "Owner",
  email: "owner@example.test",
  capabilities: {
    demo_mode: false,
    linkedin_configured: true,
    ollama_model: null,
    embedding_provider: "hash",
    allowed_repos: ["synthetic/repo"],
  },
  linkedin: { connected: false, profile: null },
};
const statuses: Record<string, unknown> = {
  "/workspaces/space/integrations/github": {
    configured: true,
    destination: null,
    can_manage: true,
    can_publish: false,
  },
  "/workspaces/space/integrations/jira": {
    configured: true,
    can_manage: true,
    state: "disconnected",
    destination: null,
  },
  "/workspaces/space/integrations/slack": {
    configured: true,
    can_manage: true,
    state: "connected",
    destination: { channel_id: "C1", channel_name: "m2o" },
  },
  "/workspaces/space/integrations/linkedin/publishing": {
    configured: false,
    state: "not_connected",
    can_connect: false,
  },
};
afterEach(() => vi.restoreAllMocks());

it("shows each tool's state and starts Jira consent from the sidebar", async () => {
  const assign = vi.fn();
  vi.spyOn(window, "location", "get").mockReturnValue({ ...window.location, assign });
  const request = vi
    .spyOn(client, "api")
    .mockImplementation(async (path, init) =>
      init?.method === "POST" ? { url: "https://auth.atlassian.com/authorize?x=1" } : statuses[path],
    );
  render(<SidebarTools workspace={workspace} user={user} onManage={vi.fn()} />);
  const list = await screen.findByRole("list");
  const row = (name: string) => within(list).getByText(name).closest("li") as HTMLElement;
  expect(row("Local")).toHaveTextContent("Ready");
  expect(row("GitHub")).toHaveTextContent("Pick repo");
  expect(row("Slack")).toHaveTextContent("Connected");
  expect(row("LinkedIn")).toHaveTextContent("Not set up");
  expect(within(row("LinkedIn")).queryByRole("button")).toBeNull();
  expect(screen.getByText("2/5 live")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Connect Jira from the sidebar" }));
  await waitFor(() => expect(assign).toHaveBeenCalledWith("https://auth.atlassian.com/authorize?x=1"));
  expect(request).toHaveBeenCalledWith("/workspaces/space/integrations/jira/connect", { method: "POST" });
});

it("asks visitors for nothing and offers no connect buttons", () => {
  const request = vi.spyOn(client, "api");
  render(<SidebarTools workspace={workspace} user={{ ...user, is_visitor: true }} onManage={vi.fn()} />);
  expect(request).not.toHaveBeenCalled();
  expect(screen.getAllByText("Private use")).toHaveLength(4);
  expect(screen.queryByRole("button", { name: /from the sidebar/ })).toBeNull();
});
