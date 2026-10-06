import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import * as client from "../api";
import type { GoogleMeetPreview, GoogleMeetStatus, Workspace } from "../types";
import GoogleMeetImport from "./GoogleMeetImport";

const workspace: Workspace = { id: "scope", name: "Synthetic", role: "owner", department: "hr" };
const ready: GoogleMeetStatus = { configured: true, state: "connected", can_import: true, setup_required: false, source_format: "meet_api_entries", transcription_required: true };
const preview: GoogleMeetPreview = { preview_id: "preview", payload_hash: "exact-hash", transcript: "Alex: Prepare the checklist.", expires_at: new Date(Date.now() + 15 * 60 * 1000).toISOString(), source: { provider: "google_meet", format: "meet_api_entries", conference_record: "conferenceRecords/latest", start_time: "2026-10-05T11:00:00Z", end_time: "2026-10-05T12:00:00Z", transcript_names: ["conferenceRecords/latest/transcripts/one"] }, participants: [{ resource: "participants/one", name: "Alex", confirmed: false }] };
const props = { workspace, meetingId: "target", title: "Onboarding", visibility: "restricted" as const, disabled: false, beforeSave: () => true, onImported: vi.fn(async () => {}) };
afterEach(() => vi.restoreAllMocks());
async function open() { fireEvent.click(screen.getByRole("button", { name: "Import latest Google Meet transcript" })); }
async function read() { fireEvent.click(await screen.findByRole("button", { name: "Preview latest accessible Google Meet transcript" })); }
it("shows absent configuration honestly and performs no transcript read", async () => {
  const request = vi.spyOn(client, "api").mockResolvedValue({ ...ready, configured: false, can_import: false, setup_required: true, state: "setup_required" });
  render(<GoogleMeetImport {...props} />); await open();
  expect(await screen.findByText("Google Meet setup is required.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Preview latest/ })).not.toBeInTheDocument();
  expect(request).toHaveBeenCalledTimes(1);
});
it("saves the exact preview and restricted target, then follows the actual reused meeting", async () => {
  const result = { meeting_id: "existing", job_id: null, reused: true, import_id: "import" };
  const request = vi.spyOn(client, "api").mockResolvedValueOnce(ready).mockResolvedValueOnce(preview).mockResolvedValueOnce(result);
  const imported = vi.fn(async () => {}); render(<GoogleMeetImport {...props} onImported={imported} />); await open(); await read();
  expect(await screen.findByText(preview.transcript)).toBeInTheDocument();
  expect(screen.getByText(/Participant labels are unconfirmed/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Save this transcript and continue" }));
  await waitFor(() => expect(imported).toHaveBeenCalledWith(result));
  expect(request.mock.calls[1][1]).toMatchObject({ method: "POST", body: "{}" });
  expect(request.mock.calls[2][1]).toMatchObject({ method: "POST", body: JSON.stringify({ payload_hash: "exact-hash", title: "Onboarding", meeting_id: "target", visibility: "restricted" }) });
});
it.each(["Latest meeting has no transcript", "Latest transcript is still processing"])("keeps unavailable reads explicit: %s", async message => {
  const request = vi.spyOn(client, "api").mockResolvedValueOnce(ready).mockRejectedValueOnce(new Error(message));
  render(<GoogleMeetImport {...props} />); await open(); await read();
  expect(await screen.findByRole("alert")).toHaveTextContent(message);
  expect(screen.queryByRole("button", { name: "Save this transcript and continue" })).not.toBeInTheDocument();
  expect(request).toHaveBeenCalledTimes(2);
});
it("discards a canceled late preview and restores focus to the trigger", async () => {
  let resolve!: (value: unknown) => void;
  vi.spyOn(client, "api").mockResolvedValueOnce(ready).mockImplementationOnce(() => new Promise(value => { resolve = value; }));
  render(<GoogleMeetImport {...props} />); await open(); await read();
  fireEvent.click(screen.getByRole("button", { name: "Close import" }));
  await act(async () => resolve(preview));
  expect(screen.queryByText(preview.transcript)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Import latest Google Meet transcript" })).toHaveFocus();
});
it("invalidates a preview when target visibility changes", async () => {
  vi.spyOn(client, "api").mockResolvedValueOnce(ready).mockResolvedValueOnce(preview).mockResolvedValueOnce(ready);
  const view = render(<GoogleMeetImport {...props} />); await open(); await read();
  expect(await screen.findByText(preview.transcript)).toBeInTheDocument();
  view.rerender(<GoogleMeetImport {...props} visibility="workspace" />);
  expect(screen.queryByText(preview.transcript)).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Save this transcript and continue" })).not.toBeInTheDocument();
  await screen.findByRole("button", { name: "Preview latest accessible Google Meet transcript" });
});
it("retains the exact preview and shows a rejected save without claiming import", async () => {
  const imported = vi.fn(async () => {});
  vi.spyOn(client, "api").mockResolvedValueOnce(ready).mockResolvedValueOnce(preview).mockRejectedValueOnce(new Error("Source changed; preview again"));
  render(<GoogleMeetImport {...props} onImported={imported} />); await open(); await read();
  fireEvent.click(await screen.findByRole("button", { name: "Save this transcript and continue" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Source changed"); expect(imported).not.toHaveBeenCalled();
});
