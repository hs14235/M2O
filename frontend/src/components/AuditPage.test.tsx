import { render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import * as client from "../api";
import AuditPage from "./AuditPage";
import type { Workspace } from "../types";

const workspace: Workspace = { id: "scope", name: "Synthetic", role: "owner", department: "engineering" };
afterEach(() => vi.restoreAllMocks());
it("does not request audit data for a role without authority", () => {
  const request = vi.spyOn(client, "api"); render(<AuditPage workspace={{ ...workspace, role: "editor" }} />);
  expect(screen.getByRole("alert")).toHaveTextContent("owner or reviewer"); expect(request).not.toHaveBeenCalled();
});
it("shows the scoped recorded event and its actual context", async () => {
  const request = vi.spyOn(client, "api").mockResolvedValue([{ action: "review.approved", target_id: "outcome", actor_id: "actor", created_at: "2026-10-05T12:00:00Z" }]);
  render(<AuditPage workspace={workspace} />);
  expect(await screen.findByText("review · approved")).toBeInTheDocument();
  expect(request).toHaveBeenCalledWith("/workspaces/scope/audit?limit=100", expect.anything());
  expect(screen.getByText("outcome")).toBeInTheDocument();
});
