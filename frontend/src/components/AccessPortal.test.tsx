import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import * as client from "../api";
import type { User } from "../types";
import AccessPortal from "./AccessPortal";

const token = "a".repeat(43), email = "synthetic@example.test";
const info = { workspace_name: "Synthetic workspace", email, role: "editor", expires_at: new Date(Date.now() + 60000).toISOString(), requires_sign_in: false };
const user: User = { id: "person", name: "Synthetic", email, capabilities: { demo_mode: false, linkedin_configured: false, ollama_model: null, embedding_provider: "hash", allowed_repos: [] }, linkedin: { connected: false, profile: null } };
const props = { path: "/invite" as const, initialToken: token, user: null, onAuthenticated: vi.fn().mockResolvedValue(undefined), onSignOut: vi.fn().mockResolvedValue(undefined), onAccountReset: vi.fn(), onTokenUsed: vi.fn(), onContinue: vi.fn() };
afterEach(() => { vi.restoreAllMocks(); vi.clearAllMocks(); });
it("lets a new recipient choose their own password and requires sign-in after acceptance", async () => {
  const request = vi.spyOn(client, "api").mockResolvedValueOnce(info).mockResolvedValueOnce({ workspace_id: "workspace", sign_in_required: true });
  render(<AccessPortal {...props} />);
  await userEvent.click(screen.getByRole("button", { name: "Review invitation" }));
  await userEvent.type(await screen.findByLabelText("Your name"), "Synthetic recipient");
  await userEvent.type(screen.getByLabelText("New password"), "Synthetic-password-123");
  await userEvent.type(screen.getByLabelText("Confirm new password"), "Synthetic-password-123");
  await userEvent.click(screen.getByRole("button", { name: "Accept workspace invitation" }));
  await screen.findByRole("heading", { name: "Invitation accepted." });
  expect(JSON.parse(String(request.mock.calls[1][1]!.body))).toEqual({ token, email, name: "Synthetic recipient", password: "Synthetic-password-123" });
  expect(props.onAuthenticated).not.toHaveBeenCalled();
  expect(props.onTokenUsed).toHaveBeenCalledOnce();
  expect(screen.getByRole("button", { name: "Go to sign in" })).toBeInTheDocument();
});
it("accepts an existing authenticated recipient without supplying a new password", async () => {
  const request = vi.spyOn(client, "api").mockResolvedValueOnce({ ...info, requires_sign_in: true }).mockResolvedValueOnce({ workspace_id: "workspace", sign_in_required: false });
  render(<AccessPortal {...props} user={user} />);
  await userEvent.click(screen.getByRole("button", { name: "Review invitation" }));
  await userEvent.click(await screen.findByRole("button", { name: "Accept workspace invitation" }));
  expect(JSON.parse(String(request.mock.calls[1][1]!.body))).toEqual({ token, email });
  await waitFor(() => expect(props.onAuthenticated).toHaveBeenCalledOnce());
  expect(screen.queryByLabelText("New password")).toBeNull();
});
it("requires a mismatched or demo account to sign out before accepting", async () => {
  const request = vi.spyOn(client, "api").mockResolvedValue(info);
  render(<AccessPortal {...props} user={{ ...user, is_visitor: true }} />);
  await userEvent.click(screen.getByRole("button", { name: "Review invitation" }));
  await screen.findByRole("button", { name: "Sign out of current account" });
  expect(screen.queryByRole("button", { name: "Accept workspace invitation" })).toBeNull();
  expect(request).toHaveBeenCalledTimes(1);
});
it("keeps recovery instructions neutral and does not claim an email was sent", async () => {
  const request = vi.spyOn(client, "api").mockResolvedValue({ message: "Contact the operator. This form does not send email." });
  render(<AccessPortal {...props} path="/recover" initialToken="" />);
  await userEvent.type(screen.getByLabelText("Account email", { exact: true }), email);
  await userEvent.click(screen.getByRole("button", { name: "Get recovery instructions" }));
  expect(await screen.findByRole("status")).toHaveTextContent("does not send email");
  expect(request).toHaveBeenCalledWith("/auth/recovery/request", expect.objectContaining({ body: JSON.stringify({ email }) }));
});
it("clears the recovery token after reset and returns to explicit sign-in", async () => {
  const request = vi.spyOn(client, "api").mockResolvedValue({ ok: true, sign_in_required: true, sessions_revoked: true });
  render(<AccessPortal {...props} path="/recover" />);
  await userEvent.type(screen.getByLabelText("Recovery account email"), email);
  await userEvent.type(screen.getByLabelText("New password"), "Synthetic-new-password");
  await userEvent.type(screen.getByLabelText("Confirm new password"), "Synthetic-new-password");
  await userEvent.click(screen.getByRole("button", { name: "Reset password and revoke previous access" }));
  await screen.findByRole("heading", { name: "Password reset." });
  expect(JSON.parse(String(request.mock.calls[0][1]!.body))).toEqual({ token, email, password: "Synthetic-new-password" });
  expect(props.onAccountReset).toHaveBeenCalledOnce(); expect(props.onTokenUsed).toHaveBeenCalledOnce();
  expect(screen.getByRole("button", { name: "Go to sign in" })).toBeInTheDocument();
});
it("preserves accepted membership feedback if the subsequent account refresh fails", async () => {
  vi.spyOn(client, "api").mockResolvedValueOnce({ ...info, requires_sign_in: true }).mockResolvedValueOnce({ workspace_id: "workspace", sign_in_required: false });
  render(<AccessPortal {...props} user={user} onAuthenticated={vi.fn().mockRejectedValue(new Error("Account refresh unavailable"))} />);
  await userEvent.click(screen.getByRole("button", { name: "Review invitation" }));
  await userEvent.click(await screen.findByRole("button", { name: "Accept workspace invitation" }));
  await screen.findByRole("heading", { name: "Invitation accepted." });
  expect(await screen.findByRole("alert")).toHaveTextContent("Account refresh unavailable");
  expect(screen.getByRole("button", { name: "Open workspace" })).toBeInTheDocument();
});
