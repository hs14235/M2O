import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import * as client from "../api";
import SlackActions from "./SlackActions";
import type { Workspace } from "../types";

const workspace: Workspace = { id: "space", name: "Synthetic", department: "hr", role: "editor" };
afterEach(() => vi.restoreAllMocks());
it("requires command submission and explicit member confirmation before mapping a Slack identity", async () => {
  const request = vi.spyOn(client, "api").mockImplementation(async path => {
    if (path.endsWith("/actions")) return { enabled: true, can_link: true, installations: [{ connection_id: "connection", team_name: "Synthetic team", linked: false }] };
    if (path.endsWith("/link")) return { challenge_id: "challenge", command: "/m2o link SYNTHETIC", team_name: "Synthetic team", expires_at: new Date(Date.now() + 100000).toISOString() };
    if (path.endsWith("/link/challenge")) return { challenge_id: "challenge", slack_user_id: "U12345678", team_name: "Synthetic team" };
    return {};
  });
  render(<SlackActions workspace={workspace} />);
  await userEvent.click(await screen.findByRole("button", { name: "Link my member in Synthetic team" }));
  expect(screen.queryByRole("button", { name: "Confirm my Slack member" })).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "Check the member that submitted my code" }));
  const confirm = await screen.findByRole("button", { name: "Confirm my Slack member" });
  expect(confirm).toBeDisabled(); await userEvent.click(screen.getByRole("checkbox", { name: /This is my Slack Member ID/ })); await userEvent.click(confirm);
  await waitFor(() => expect(request).toHaveBeenCalledWith(expect.stringContaining("/link/confirm"), expect.objectContaining({ method: "POST", body: JSON.stringify({ challenge_id: "challenge", slack_user_id: "U12345678" }) })));
});
it("does not offer interactive linking when the callback feature is disabled", async () => {
  vi.spyOn(client, "api").mockResolvedValue({ enabled: false, can_link: false, installations: [] });
  render(<SlackActions workspace={workspace} />);
  await screen.findByText(/Interactive Slack actions need an enabled installation/);
  expect(screen.queryByRole("button", { name: /Link my member/ })).toBeNull();
});
