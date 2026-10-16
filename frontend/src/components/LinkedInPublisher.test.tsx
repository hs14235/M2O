import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import * as client from "../api";
import { LinkedInPublisher, defaultPostText, postUrl } from "./LinkedInPublisher";
import type { Meeting, Workspace } from "../types";

const workspace: Workspace = { id: "space", name: "Synthetic", role: "owner", department: "engineering" };
const meeting = {
  id: "weekly",
  title: "Weekly sync",
  current_revision: 2,
  visibility: "workspace",
  tasks: [
    { id: "item", title: "Ship the beta", version: 3, status: "approved" },
    { id: "other", title: "Draft notes", version: 1, status: "draft" },
  ],
} as Meeting;
const status = {
  configured: true,
  state: "connected",
  can_connect: true,
  can_publish: true,
  can_draft: true,
};
const preview = {
  id: "proposal",
  audience: "CONNECTIONS",
  payload: { commentary: "Exact reviewed post", visibility: "CONNECTIONS" },
  payload_hash: "b".repeat(64),
  expires_at: new Date(Date.now() + 100000).toISOString(),
};
const props = {
  workspace,
  meeting,
  selected: ["item"],
  onStage: vi.fn(),
  onJob: vi.fn(),
  onConnections: vi.fn(),
};
afterEach(() => vi.restoreAllMocks());
function requests(overrides: Record<string, unknown> = {}) {
  return vi.spyOn(client, "api").mockImplementation(async (path) => {
    if (path.endsWith("/integrations/linkedin/publishing")) return overrides.status ?? status;
    if (path.endsWith("/deliveries/linkedin")) return overrides.receipts ?? [];
    if (path.endsWith("/linkedin/drafts")) return { id: "draft", version: 1 };
    if (path.endsWith("/linkedin/preview")) return preview;
    return { job_id: "job" };
  });
}

it("starts from the selected outcomes, requires disclosure, and approves only the stored hash", async () => {
  const request = requests();
  const onStage = vi.fn(),
    onJob = vi.fn();
  const view = render(<LinkedInPublisher {...props} onStage={onStage} onJob={onJob} stage="configure" />);
  const text = screen.getByRole("textbox", { name: "Post text" });
  expect(text).toHaveValue('Next steps from "Weekly sync":\n\n• Ship the beta');
  const generate = screen.getByRole("button", { name: "Generate exact LinkedIn preview" });
  await waitFor(() => expect(text).toBeEnabled());
  expect(generate).toBeDisabled();
  await userEvent.click(screen.getByRole("checkbox", { name: /approve sharing it on LinkedIn/ }));
  await userEvent.click(generate);
  await waitFor(() => expect(onStage).toHaveBeenCalledWith("preview"));
  const body = (suffix: string) =>
    JSON.parse(String(request.mock.calls.find(([path]) => path.endsWith(suffix))![1]!.body));
  expect(body("/linkedin/drafts")).toEqual({
    kind: "post",
    text: 'Next steps from "Weekly sync":\n\n• Ship the beta',
    versions: { item: 3 },
  });
  expect(body("/linkedin/preview")).toEqual({
    draft_id: "draft",
    expected_draft_version: 1,
    disclosure_confirmed: true,
  });
  view.rerender(<LinkedInPublisher {...props} onStage={onStage} onJob={onJob} stage="preview" />);
  expect(screen.getByText("Exact reviewed post")).toBeInTheDocument();
  expect(screen.getByText("Your connections only")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Approve exact preview and post to LinkedIn" }));
  await waitFor(() => expect(onStage).toHaveBeenCalledWith("receipt"));
  expect(body("/approve")).toEqual({ payload_hash: "b".repeat(64) });
  expect(onJob).toHaveBeenCalledWith("job");
});

it("sends people to Connections when posting is not connected", async () => {
  requests({ status: { ...status, state: "not_connected", can_publish: false } });
  const onConnections = vi.fn();
  render(<LinkedInPublisher {...props} onConnections={onConnections} stage="configure" />);
  await userEvent.click(await screen.findByRole("button", { name: "Open connections" }));
  expect(onConnections).toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Generate exact LinkedIn preview" })).toBeDisabled();
});

it("links a confirmed post and warns about an unconfirmed one", async () => {
  requests({
    receipts: [
      {
        operation_id: "one",
        state: "completed",
        created_at: "2026-10-15T12:00:00Z",
        result: { status: "created", post_id: "urn:li:share:123" },
      },
      { operation_id: "two", state: "uncertain", created_at: "2026-10-15T12:05:00Z", result: null },
    ],
  });
  render(<LinkedInPublisher {...props} stage="receipt" />);
  expect(await screen.findByRole("link", { name: "Open the post on LinkedIn" })).toHaveAttribute(
    "href",
    "https://www.linkedin.com/feed/update/urn%3Ali%3Ashare%3A123/",
  );
  expect(screen.getByText(/never resends it automatically/)).toBeInTheDocument();
});

it("keeps the reviewer's own text when the selection changes", async () => {
  requests();
  const view = render(<LinkedInPublisher {...props} stage="configure" />);
  const text = screen.getByRole("textbox", { name: "Post text" });
  await waitFor(() => expect(text).toBeEnabled());
  await userEvent.clear(text);
  await userEvent.type(text, "My own words");
  view.rerender(<LinkedInPublisher {...props} selected={[]} stage="configure" />);
  expect(text).toHaveValue("My own words");
});

it("builds the suggested text and post links", () => {
  expect(defaultPostText(meeting, ["item", "other"])).toContain("• Draft notes");
  expect(postUrl("urn:li:ugcPost:9")).toBe("https://www.linkedin.com/feed/update/urn%3Ali%3AugcPost%3A9/");
});
