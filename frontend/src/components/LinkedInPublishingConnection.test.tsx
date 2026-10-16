import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import * as client from "../api";
import LinkedInPublishingConnection from "./LinkedInPublishingConnection";
import type { Workspace } from "../types";

const workspace: Workspace = { id: "space", name: "Synthetic", role: "owner", department: "engineering" };
const base = { configured: true, author: null, expires_at: null, can_connect: true, can_publish: false };
afterEach(() => vi.restoreAllMocks());

it("starts consent at the URL the server returns", async () => {
  const assign = vi.fn();
  vi.spyOn(window, "location", "get").mockReturnValue({ ...window.location, assign });
  const request = vi
    .spyOn(client, "api")
    .mockImplementation(async (path, init) =>
      init?.method === "POST"
        ? { url: "https://www.linkedin.com/oauth/v2/authorization?x=1" }
        : { ...base, state: "not_connected" },
    );
  render(<LinkedInPublishingConnection workspace={workspace} />);
  await userEvent.click(await screen.findByRole("button", { name: "Connect LinkedIn posting" }));
  await waitFor(() =>
    expect(assign).toHaveBeenCalledWith("https://www.linkedin.com/oauth/v2/authorization?x=1"),
  );
  expect(request).toHaveBeenCalledWith(
    "/workspaces/space/integrations/linkedin/publishing/connect",
    expect.objectContaining({ method: "POST" }),
  );
});

it("disconnects and rereads status", async () => {
  let connected = true;
  const request = vi.spyOn(client, "api").mockImplementation(async (_path, init) => {
    if (init?.method === "DELETE") {
      connected = false;
      return { connected: false };
    }
    return connected
      ? { ...base, state: "connected", expires_at: "2026-12-14T00:00:00Z", can_publish: true }
      : { ...base, state: "not_connected" };
  });
  render(<LinkedInPublishingConnection workspace={workspace} />);
  await userEvent.click(await screen.findByRole("button", { name: /Disconnect posting/ }));
  expect(await screen.findByRole("button", { name: "Connect LinkedIn posting" })).toBeInTheDocument();
  expect(request).toHaveBeenCalledWith(
    "/workspaces/space/integrations/linkedin/publishing",
    expect.objectContaining({ method: "DELETE" }),
  );
});

it("explains when the operator has not configured an app", async () => {
  vi.spyOn(client, "api").mockResolvedValue({
    ...base,
    configured: false,
    can_connect: false,
    state: "not_connected",
  });
  render(<LinkedInPublishingConnection workspace={workspace} />);
  expect(await screen.findByText(/must be configured by the application operator/)).toBeInTheDocument();
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});
