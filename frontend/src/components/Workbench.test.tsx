import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import * as client from "../api";
import type { Meeting, User, Workspace } from "../types";
import type { Route } from "../navigation";
import Workbench from "./Workbench";

const workspace: Workspace = { id: "space", name: "Synthetic engineering", department: "engineering", role: "owner" };
const user: User = { id: "user", name: "Synthetic", email: "synthetic@example.test", capabilities: { demo_mode: true, linkedin_configured: false, ollama_model: null, embedding_provider: "hash", allowed_repos: [] }, linkedin: { connected: false, profile: null } };
const meeting = { id: "weekly", record_id: "record", title: "Synthetic meeting", visibility: "workspace", version: 1, current_revision: 1, occurred_on: null, timezone: "America/New_York", raw_text: "Synthetic source", index_status: "ready", embedding_provider: "hash", chunk_count: 1, tasks: [], mentions: [], revisions: [] } as Meeting;
const route: Route = { workspace: "space", page: "meetings", meeting: "weekly", step: "people", valid: true };
afterEach(() => vi.restoreAllMocks());

it("retries a failed job read without issuing a second extraction", async () => {
  let jobReads = 0;
  const request = vi.spyOn(client, "api").mockImplementation(async (path, options) => {
    if (path.endsWith("/extract")) return { job_id: "job" } as never;
    if (path.endsWith("/jobs/job")) {
      jobReads += 1;
      if (jobReads === 1) throw new client.ApiError(503, "Temporarily unavailable");
      return { id: "job", kind: "extract", state: "completed", error_code: null, result: { mode: "rules", created: 0 } } as never;
    }
    if (path.endsWith("/participants")) return [] as never;
    if (path.includes("/meetings?")) return { meetings: [meeting], next_offset: null } as never;
    if (path.endsWith("/meetings/weekly") && !options?.method) return meeting as never;
    throw new Error("Unexpected synthetic request: " + path);
  });
  render(<Workbench workspace={workspace} user={user} onDirty={vi.fn()} route={route} navigate={vi.fn()} />);
  await waitFor(() => expect(screen.getByRole("button", { name: "Extract outcomes" })).toBeEnabled());
  await userEvent.click(screen.getByRole("button", { name: "Extract outcomes" }));
  await userEvent.click(await screen.findByRole("button", { name: "Read job status again" }));
  expect(await screen.findByText(/Job completed/)).toBeInTheDocument();
  expect(jobReads).toBe(2);
  expect(request.mock.calls.filter(([, options]) => options?.method === "POST")).toHaveLength(1);
});

it("retains an accepted transcript save and recovers only its saved resource", async () => {
  let acceptedId = "";
  let failDetail = true;
  const request = vi.spyOn(client, "api").mockImplementation(async (path, options) => {
    if (path.endsWith("/index")) { acceptedId = JSON.parse(String(options?.body)).meeting_id; return { job_id: null } as never; }
    if (path.endsWith("/participants")) return [] as never;
    if (path.includes("/meetings?")) return { meetings: [], next_offset: null } as never;
    if (acceptedId && path.endsWith("/meetings/" + acceptedId)) {
      if (failDetail) { failDetail = false; throw new client.ApiError(503, "Temporarily unavailable"); }
      return { ...meeting, id: acceptedId, title: "Saved synthetic meeting", raw_text: "Saved synthetic source" } as never;
    }
    throw new Error("Unexpected synthetic request: " + path);
  });
  const navigate = vi.fn();
  render(<Workbench workspace={workspace} user={user} onDirty={vi.fn()} route={{ ...route, meeting: "new", step: "transcript" }} navigate={navigate} />);
  await waitFor(() => expect(screen.getByLabelText("Meeting title")).toBeEnabled());
  await userEvent.type(screen.getByLabelText("Meeting title"), "Saved synthetic meeting");
  await userEvent.type(screen.getByLabelText("Transcript text"), "Saved synthetic source");
  await userEvent.click(screen.getByRole("button", { name: "Save transcript and continue" }));
  expect(await screen.findByText(/Your transcript save was accepted/)).toBeInTheDocument();
  expect(screen.getByLabelText("Transcript text")).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "Load saved transcript" }));
  await waitFor(() => expect(navigate).toHaveBeenCalledWith("/workspaces/space/meetings/" + acceptedId + "/people"));
  expect(request.mock.calls.filter(([path]) => path.endsWith("/index"))).toHaveLength(1);
});

it("does not display a late job result in another meeting", async () => {
  let finish!: (value: never) => void;
  vi.spyOn(client, "api").mockImplementation((path) => {
    if (path.endsWith("/extract")) return Promise.resolve({ job_id: "job" } as never);
    if (path.endsWith("/jobs/job")) return new Promise(resolve => { finish = resolve; });
    if (path.endsWith("/participants")) return Promise.resolve([] as never);
    if (path.includes("/meetings?")) return Promise.resolve({ meetings: [meeting], next_offset: null } as never);
    if (path.includes("/meetings/")) return Promise.resolve({ ...meeting, id: path.split("/").at(-1) } as never);
    return Promise.reject(new Error("Unexpected synthetic request: " + path));
  });
  const props = { workspace, user, onDirty: vi.fn(), navigate: vi.fn() };
  const view = render(<Workbench {...props} route={route} />);
  await waitFor(() => expect(screen.getByRole("button", { name: "Extract outcomes" })).toBeEnabled());
  await userEvent.click(screen.getByRole("button", { name: "Extract outcomes" }));
  view.rerender(<Workbench {...props} route={{ ...route, meeting: "another" }} />);
  await act(async () => finish({ id: "job", kind: "extract", state: "completed", result: { mode: "rules", created: 99 } } as never));
  expect(screen.queryByText(/99 new outcomes/)).toBeNull();
});
