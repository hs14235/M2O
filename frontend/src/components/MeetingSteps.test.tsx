import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import * as client from "../api";
import type { Meeting, Outcome, Workspace } from "../types";
import { PeopleStep, ReviewStep, TranscriptStep } from "./MeetingSteps";

const workspace: Workspace = { id: "workspace", name: "People", role: "owner", department: "hr" };
const action: Outcome = { id: "action", kind: "action", title: "Review onboarding", body: "Prepare the checklist", labels: [], status: "draft", version: 1, owner_id: null, assignee_hint: null, due_hint: null, due_date: null, confidence: .6, evidence: [] };
const decision: Outcome = { ...action, id: "decision", kind: "decision", title: "Use the checklist" };
const meeting = { id: "weekly", current_revision: 1, tasks: [action, decision] } as Meeting;
const props = { meeting, workspace, people: [], pending: false, onDirty: vi.fn(), onSaved: vi.fn(), changeReview: (change: () => void) => change(), onBack: vi.fn(), onContinue: vi.fn() };

it("lets a viewer continue through a saved transcript without permitting edits", async () => {
  const onContinue = vi.fn();
  render(<TranscriptStep meeting={meeting} title="Onboarding" setTitle={vi.fn()} text="Synthetic transcript" setText={vi.fn()} slug="weekly" setSlug={vi.fn()} occurred="" setOccurred={vi.fn()} visibility="workspace" setVisibility={vi.fn()} editable={false} pending={false} dirty={false} onSubmit={vi.fn()} onUpload={vi.fn()} onExample={vi.fn()} onContinue={onContinue} department="hr" />);
  expect(screen.getByRole("textbox", { name: "Meeting title" })).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "Continue to people" }));
  expect(onContinue).toHaveBeenCalledOnce();
});

it("keeps the reviewed outcome visible when its saved version changes the server order", async () => {
  const view = render(<ReviewStep {...props} />);
  expect(screen.getByRole("heading", { name: "Review onboarding" })).toBeInTheDocument();
  view.rerender(<ReviewStep {...props} meeting={{ ...meeting, tasks: [decision, { ...action, status: "approved", version: 2 }] }} />);
  expect(screen.getByRole("heading", { name: "Review onboarding" })).toBeInTheDocument();
  expect(screen.getByText("approved · v2")).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Use the checklist" })).toBeNull();
});
it("keeps demo participant confirmation usable without offering custom directory creation", async () => {
  const onConfirm = vi.fn();
  render(<PeopleStep meeting={{ ...meeting, index_status: "ready", mentions: [{ id: "mention", name: "Alex", participant_id: null, confirmed: false, candidates: [] }] }} people={[{ id: "person", name: "Alex", role: "Synthetic engineer", aliases: [], github_login: null, linkedin_url: null, linked_user_id: null, provenance: "synthetic" }]} workspace={workspace} pending={false} ready directoryEditable={false} onExtract={vi.fn()} onConfirm={onConfirm} onParticipantAdded={vi.fn()} onDirty={vi.fn()} onBack={vi.fn()} onContinue={vi.fn()} />);
  expect(screen.queryByText("Add a person to this workspace")).toBeNull();
  await userEvent.selectOptions(screen.getByLabelText("Directory match for Alex"), "person");
  await userEvent.click(screen.getByRole("button", { name: "Confirm person" }));
  expect(onConfirm).toHaveBeenCalledWith("mention", "person");
});
it("opens the calendar-selected outcome even when tasks arrive after the initial view", () => {
  const view = render(<ReviewStep {...props} meeting={{ ...meeting, tasks: [] }} focusItem="decision" />);
  view.rerender(<ReviewStep {...props} focusItem="decision" />);
  expect(screen.getByRole("heading", { name: "Use the checklist" })).toBeInTheDocument();
});
it("shows finite save feedback only after the review request is acknowledged", async () => {
  const request = vi.spyOn(client, "api").mockRejectedValueOnce(new Error("Revision changed")).mockResolvedValueOnce({});
  render(<ReviewStep {...props} />);
  await userEvent.click(screen.getByRole("button", { name: "Approve outcome" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Revision changed");
  expect(screen.queryByText("Review saved.")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Approve outcome" }));
  expect(await screen.findByText("Review saved.")).toBeInTheDocument();
  request.mockRestore();
});
