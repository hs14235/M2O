// Synthetic records for the style guide. None of them belongs to a real
// workspace, so nothing on the page loads data.
import { ApiError } from "../api";
import type { Job, MeetingSummary, Outcome, Participant, Workspace } from "../types";

export const workspace: Workspace = {
  id: "styleguide",
  name: "Style guide",
  department: "engineering",
  role: "owner",
};
export const viewer: Workspace = { ...workspace, role: "viewer" };
export const participants: Participant[] = [
  {
    id: "participant-priya",
    name: "Priya",
    role: "Release manager",
    aliases: [],
    github_login: null,
    linkedin_url: null,
    linked_user_id: null,
    provenance: "synthetic",
  },
];

const base: Outcome = {
  id: "styleguide-draft",
  kind: "action",
  title: "Publish the release checklist",
  body: "Share the checklist with the release channel before Thursday's freeze.",
  labels: ["release"],
  status: "draft",
  owner_id: null,
  assignee_hint: "Priya",
  due_hint: "before Thursday",
  due_date: null,
  confidence: 0.82,
  version: 1,
  evidence: [
    {
      id: "styleguide-evidence",
      i: 0,
      text: "Priya: I'll publish the release checklist before Thursday's freeze.",
      speaker: "Priya",
      start_line: 4,
    },
  ],
};

export const outcomes: { label: string; item: Outcome; workspace: Workspace }[] = [
  { label: "Draft", item: base, workspace },
  {
    label: "Approved",
    item: {
      ...base,
      id: "styleguide-approved",
      kind: "decision",
      title: "Keep the freeze on Thursday",
      status: "approved",
      owner_id: "participant-priya",
      due_hint: null,
      due_date: "2026-10-22",
      version: 2,
    },
    workspace,
  },
  {
    label: "Done",
    item: {
      ...base,
      id: "styleguide-done",
      kind: "follow_up",
      title: "Send the freeze reminder",
      status: "done",
      due_hint: null,
      version: 3,
    },
    workspace,
  },
  {
    label: "Dismissed",
    item: {
      ...base,
      id: "styleguide-dismissed",
      kind: "risk",
      title: "Vendor sign-off may slip",
      status: "dismissed",
      due_hint: null,
      version: 2,
    },
    workspace,
  },
  {
    label: "Viewer role (read only)",
    item: { ...base, id: "styleguide-viewer", kind: "blocker", title: "Staging database is full" },
    workspace: viewer,
  },
];

export const jobs: Job[] = [
  { id: "styleguide-queued", kind: "extract", state: "queued", error_code: null, result: null },
  { id: "styleguide-running", kind: "transcribe", state: "running", error_code: null, result: null },
  {
    id: "styleguide-completed",
    kind: "extract",
    state: "completed",
    error_code: null,
    result: { mode: "rules", created: 4 },
  },
  { id: "styleguide-failed", kind: "extract", state: "failed", error_code: "worker_error", result: null },
];

export const meetings: MeetingSummary[] = [
  {
    id: "styleguide-meeting-1",
    record_id: "styleguide-record-1",
    title: "Release readiness",
    visibility: "workspace",
    version: 1,
    current_revision: 2,
    occurred_on: "2026-10-15",
    timezone: "UTC",
  },
  {
    id: "styleguide-meeting-2",
    record_id: "styleguide-record-2",
    title: "Quarter close review",
    visibility: "restricted",
    version: 1,
    current_revision: 1,
    occurred_on: "2026-10-14",
    timezone: "UTC",
  },
];

export const apiError = new ApiError(503, "The service is temporarily unavailable.", "req_123");
