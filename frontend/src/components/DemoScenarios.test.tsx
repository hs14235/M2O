import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import * as client from "../api";
import DemoScenarios from "./DemoScenarios";
import type { DemoCatalog, Workspace } from "../types";

const workspace: Workspace = { id: "visitor-space", name: "People Operations demo", department: "hr", role: "owner", is_demo: true };
const catalog: DemoCatalog = { enabled: true, scenarios: [{ id: "hr", department: "hr", title: "Onboarding coordination", transcript: "Synthetic source", synthetic: true }, { id: "engineering", department: "engineering", title: "Release readiness", transcript: "Synthetic source", synthetic: true }, { id: "no-outcomes", department: null, title: "A quiet check-in", transcript: "Good morning", synthetic: true }] };
afterEach(() => vi.restoreAllMocks());
it("shows department and no-action fixtures and submits their identifier without a transcript upload", async () => {
  const loaded = { meeting_id: "demo-hr", job_id: "index-job" }, onLoaded = vi.fn();
  const request = vi.spyOn(client, "api").mockResolvedValueOnce(catalog).mockResolvedValueOnce(loaded);
  render(<DemoScenarios workspace={workspace} disabled={false} onLoaded={onLoaded} />);
  await screen.findByRole("button", { name: "Open Onboarding coordination" });
  expect(screen.getByRole("button", { name: "Open A quiet check-in" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Open Release readiness" })).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "Open Onboarding coordination" }));
  await waitFor(() => expect(onLoaded).toHaveBeenCalledWith(loaded));
  expect(request).toHaveBeenCalledWith("/workspaces/visitor-space/demo/load", expect.objectContaining({ method: "POST", body: JSON.stringify({ fixture_id: "hr" }) }));
});
it("does not navigate after the fixture loader rejects a request", async () => {
  vi.spyOn(client, "api").mockResolvedValueOnce(catalog).mockRejectedValueOnce(new client.ApiError(409, "Example archived"));
  const onLoaded = vi.fn(); render(<DemoScenarios workspace={workspace} disabled={false} onLoaded={onLoaded} />);
  await userEvent.click(await screen.findByRole("button", { name: "Open A quiet check-in" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Example archived");
  expect(onLoaded).not.toHaveBeenCalled();
});
