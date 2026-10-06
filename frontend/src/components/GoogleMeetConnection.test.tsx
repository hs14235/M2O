import { render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import * as client from "../api";
import type { User, Workspace } from "../types";
import GoogleMeetConnection from "./GoogleMeetConnection";

const workspace: Workspace = { id: "scope", name: "Synthetic", role: "owner", department: "hr" };
const user: User = { id: "user", name: "Synthetic", email: "synthetic@example.test", capabilities: { demo_mode: false, linkedin_configured: false, ollama_model: null, embedding_provider: "hash", allowed_repos: [] }, linkedin: { connected: false, profile: null } };
afterEach(() => vi.restoreAllMocks());
it.each(["visitor", "viewer", "demo"])("does not request private Google access for %s", condition => {
  const request = vi.spyOn(client, "api");
  render(<GoogleMeetConnection workspace={{ ...workspace, role: condition === "viewer" ? "viewer" : "owner" }} user={{ ...user, is_visitor: condition === "visitor", capabilities: { ...user.capabilities, demo_mode: condition === "demo" } }} />);
  expect(request).not.toHaveBeenCalled(); expect(screen.getByText(/requires an invited private contributor/)).toBeInTheDocument();
});
it("requires actual configuration before presenting authorization", async () => {
  vi.spyOn(client, "api").mockResolvedValue({ configured: false, can_import: false, setup_required: true, state: "setup_required" });
  render(<GoogleMeetConnection workspace={workspace} user={user} />);
  expect(await screen.findByText("Google Meet setup is required.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Connect my Google Meet account" })).not.toBeInTheDocument();
});
