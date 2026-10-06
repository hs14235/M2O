import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import * as client from "../api";
import Invitations from "./Invitations";
import type { Workspace } from "../types";

const workspace: Workspace = { id: "workspace", name: "Synthetic", role: "owner", department: "engineering" };
afterEach(() => vi.restoreAllMocks());
it("issues only email/role and keeps the private link out of persistent storage", async () => {
  const link = window.location.origin + "/invite#token=" + "a".repeat(43);
  const request = vi.spyOn(client, "api").mockImplementation(async (_path, options) => options?.method === "POST" ? { id: "invite", email: "synthetic@example.test", role: "editor", state: "pending", expires_at: new Date(Date.now() + 60000).toISOString(), accept_url: link } : { invitations: [] });
  render(<Invitations workspace={workspace} />);
  await userEvent.type(screen.getByLabelText("Invitation email"), "synthetic@example.test");
  await userEvent.click(screen.getByRole("button", { name: "Create private invitation link" }));
  expect(await screen.findByLabelText("One-time invitation link")).toHaveValue(link);
  const create = request.mock.calls.find(([, options]) => options?.method === "POST")!;
  expect(JSON.parse(String(create[1]!.body))).toEqual({ email: "synthetic@example.test", role: "editor" });
  expect(screen.queryByLabelText(/password/i)).toBeNull();
  expect(Object.values(localStorage).some(value => String(value).includes(link))).toBe(false);
  await userEvent.click(screen.getByRole("button", { name: "Hide private link" }));
  expect(screen.queryByLabelText("One-time invitation link")).toBeNull();
});
it("does not call a failed history read an empty invitation list", async () => {
  const request = vi.spyOn(client, "api").mockRejectedValueOnce(new client.ApiError(503, "Unavailable")).mockResolvedValue({ invitations: [] });
  render(<Invitations workspace={workspace} />);
  await userEvent.click(await screen.findByRole("button", { name: "Refresh invitation history" }));
  await waitFor(() => expect(screen.getByText("No invitations have been recorded.")).toBeInTheDocument());
  expect(request.mock.calls.every(([, options]) => !options?.method)).toBe(true);
});
