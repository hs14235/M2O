import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api";
import type { Meeting, Outcome, Workspace } from "../types";
import { PeopleStep, ReviewStep, TranscriptStep } from "./MeetingSteps";

const workspace: Workspace = { id: "workspace", name: "People", role: "owner", department: "hr" };
const action: Outcome = {
  id: "action",
  kind: "action",
  title: "Review onboarding",
  body: "Prepare the checklist",
  labels: [],
  status: "draft",
  version: 1,
  owner_id: null,
  assignee_hint: null,
  due_hint: null,
  due_date: null,
  confidence: 0.6,
  evidence: [],
};
const decision: Outcome = { ...action, id: "decision", kind: "decision", title: "Use the checklist" };
const meeting = { id: "weekly", current_revision: 1, tasks: [action, decision] } as Meeting;
const props = {
  meeting,
  workspace,
  people: [],
  pending: false,
  onDirty: vi.fn(),
  onSaved: vi.fn(),
  changeReview: (change: () => void) => change(),
  onBack: vi.fn(),
  onContinue: vi.fn(),
};

it("lets a viewer continue through a saved transcript without permitting edits", async () => {
  const onContinue = vi.fn();
  render(
    <TranscriptStep
      meeting={meeting}
      title="Onboarding"
      setTitle={vi.fn()}
      text="Synthetic transcript"
      setText={vi.fn()}
      slug="weekly"
      setSlug={vi.fn()}
      occurred=""
      setOccurred={vi.fn()}
      visibility="workspace"
      setVisibility={vi.fn()}
      editable={false}
      pending={false}
      dirty={false}
      onSubmit={vi.fn()}
      onUpload={vi.fn()}
      onExample={vi.fn()}
      onContinue={onContinue}
      department="hr"
    />,
  );
  expect(screen.getByRole("textbox", { name: "Meeting title" })).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "Continue to people" }));
  expect(onContinue).toHaveBeenCalledOnce();
});

it("keeps the reviewed outcome visible when its saved version changes the server order", async () => {
  const view = render(<ReviewStep {...props} />);
  expect(screen.getByRole("heading", { name: "Review onboarding" })).toBeInTheDocument();
  view.rerender(
    <ReviewStep
      {...props}
      meeting={{ ...meeting, tasks: [decision, { ...action, status: "approved", version: 2 }] }}
    />,
  );
  expect(screen.getByRole("heading", { name: "Review onboarding" })).toBeInTheDocument();
  expect(screen.getByText("approved · v2")).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Use the checklist" })).toBeNull();
});
it("keeps demo participant confirmation usable without offering custom directory creation", async () => {
  const onConfirm = vi.fn();
  render(
    <PeopleStep
      meeting={{
        ...meeting,
        index_status: "ready",
        mentions: [{ id: "mention", name: "Alex", participant_id: null, confirmed: false, candidates: [] }],
      }}
      people={[
        {
          id: "person",
          name: "Alex",
          role: "Synthetic engineer",
          aliases: [],
          github_login: null,
          linkedin_url: null,
          linked_user_id: null,
          provenance: "synthetic",
        },
      ]}
      workspace={workspace}
      pending={false}
      ready
      directoryEditable={false}
      onExtract={vi.fn()}
      onConfirm={onConfirm}
      onParticipantAdded={vi.fn()}
      onDirty={vi.fn()}
      onBack={vi.fn()}
      onContinue={vi.fn()}
    />,
  );
  expect(screen.queryByText("Add a person to this workspace")).toBeNull();
  await userEvent.selectOptions(screen.getByLabelText("Directory match for Alex"), "person");
  await userEvent.click(screen.getByRole("button", { name: "Confirm person" }));
  expect(onConfirm).toHaveBeenCalledWith("mention", "person");
});
it("asks about people only after extraction, with the single suggestion preselected", async () => {
  const onConfirm = vi.fn();
  const morgan = { id: "morgan", name: "Morgan", role: "Reviewer" };
  const step = (extracted: boolean) => (
    <PeopleStep
      meeting={{
        ...meeting,
        tasks: [],
        extracted,
        index_status: "ready",
        mentions: [
          { id: "mention", name: "Morgan", participant_id: null, confirmed: false, candidates: [morgan] },
        ],
      }}
      people={[
        {
          ...morgan,
          aliases: [],
          github_login: null,
          linkedin_url: null,
          linked_user_id: null,
          provenance: "synthetic",
        },
      ]}
      workspace={workspace}
      pending={false}
      ready
      onExtract={vi.fn()}
      onConfirm={onConfirm}
      onParticipantAdded={vi.fn()}
      onDirty={vi.fn()}
      onBack={vi.fn()}
      onContinue={vi.fn()}
    />
  );
  const view = render(step(false));
  expect(screen.getByText(/Extract outcomes first/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Confirm person" })).toBeNull();
  view.rerender(step(true));
  expect(screen.getByRole("button", { name: "Morgan · Reviewer" })).toHaveAttribute("aria-pressed", "true");
  await userEvent.click(screen.getByRole("button", { name: "Confirm person" }));
  expect(onConfirm).toHaveBeenCalledWith("mention", "morgan");
});
it("opens the calendar-selected outcome even when tasks arrive after the initial view", () => {
  const view = render(<ReviewStep {...props} meeting={{ ...meeting, tasks: [] }} focusItem="decision" />);
  view.rerender(<ReviewStep {...props} focusItem="decision" />);
  expect(screen.getByRole("heading", { name: "Use the checklist" })).toBeInTheDocument();
});
it("shows finite save feedback only after the review request is acknowledged", async () => {
  const request = vi
    .spyOn(client, "api")
    .mockRejectedValueOnce(new Error("Revision changed"))
    .mockResolvedValueOnce({});
  render(<ReviewStep {...props} />);
  await userEvent.click(screen.getByRole("button", { name: "Approve outcome" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Revision changed");
  expect(screen.queryByText("Review saved.")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Approve outcome" }));
  expect(await screen.findByText("Review saved.")).toBeInTheDocument();
  request.mockRestore();
});

describe("the transcript-to-outcome moment on People", () => {
  const evidence = (start_line: number, text: string, speaker: string) => ({
    id: "e" + start_line,
    i: 0,
    text,
    speaker,
    start_line,
  });
  const extracted = {
    ...meeting,
    index_status: "ready",
    mentions: [],
    raw_text: "Alex: Review onboarding\n\nSam: Use the checklist",
    tasks: [
      { ...action, evidence: [evidence(1, "Alex: Review onboarding", "Alex")] },
      { ...decision, evidence: [evidence(3, "Sam: Use the checklist", "Sam")] },
    ],
  } as Meeting;
  const people = {
    people: [],
    workspace,
    pending: false,
    ready: true,
    onExtract: vi.fn(),
    onConfirm: vi.fn(),
    onParticipantAdded: vi.fn(),
    onDirty: vi.fn(),
    onBack: vi.fn(),
    onContinue: vi.fn(),
  };
  afterEach(() => {
    localStorage.clear();
    delete document.documentElement.dataset.motion;
    Reflect.deleteProperty(document, "startViewTransition");
  });

  it("shows the numbered transcript lines before extraction, the first 60 at first", async () => {
    const raw = Array.from({ length: 75 }, (_, n) => "Alex: Synthetic line " + (n + 1)).join("\n\n");
    render(<PeopleStep {...people} meeting={{ ...extracted, raw_text: raw, tasks: [] }} />);
    const region = screen.getByRole("region", { name: "Transcript lines" });
    expect(region).toHaveAttribute("tabindex", "0");
    expect(within(region).getAllByRole("listitem")).toHaveLength(60);
    // Blank lines keep their numbers, so the 60th shown line is transcript line 119.
    expect(within(region).getByText("119")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Show all 75 lines" }));
    expect(within(region).getAllByRole("listitem")).toHaveLength(75);
  });

  it("goes straight to the draft cards when the browser has no view transitions", () => {
    const view = render(<PeopleStep {...people} meeting={extracted} extracting />);
    expect(screen.getByRole("region", { name: "Transcript lines" })).toBeInTheDocument();
    expect(screen.queryByText(/draft outcomes found/)).toBeNull();
    view.rerender(<PeopleStep {...people} meeting={extracted} moment={{ job: "job", revision: 1 }} />);
    expect(screen.getByRole("status")).toHaveTextContent("2 draft outcomes found");
    const card = screen.getByRole("link", { name: /Review onboarding/ });
    expect(card).toHaveAttribute("href", "/workspaces/workspace/meetings/weekly/review?outcome=action");
    expect(card).toHaveTextContent("line 1 · Alex");
    expect(screen.getByRole("link", { name: /Use the checklist/ })).toHaveTextContent("line 3 · Sam");
    expect(screen.getByText("Transcript lines").closest("details")).not.toHaveAttribute("open");
    expect(JSON.parse(localStorage.getItem("m2o-moment")!)).toEqual(["weekly:1"]);
  });

  it("skips the animation in calm mode even when view transitions exist", () => {
    const start = vi.fn();
    Object.defineProperty(document, "startViewTransition", { value: start, configurable: true });
    document.documentElement.dataset.motion = "calm";
    const view = render(<PeopleStep {...people} meeting={extracted} extracting />);
    view.rerender(<PeopleStep {...people} meeting={extracted} moment={{ job: "job", revision: 1 }} />);
    expect(screen.getByRole("status")).toHaveTextContent("2 draft outcomes found");
    // The only line view left is the collapsed one below the cards.
    expect(screen.getByRole("region", { name: "Transcript lines" }).closest("details")).not.toHaveAttribute(
      "open",
    );
    expect(start).not.toHaveBeenCalled();
  });

  it("shows the end state for a revision that already played the moment", () => {
    localStorage.setItem("m2o-moment", JSON.stringify(["weekly:1"]));
    const start = vi.fn();
    Object.defineProperty(document, "startViewTransition", { value: start, configurable: true });
    const view = render(<PeopleStep {...people} meeting={extracted} extracting />);
    // Re-extracting a revision that already played keeps the cards instead of the lines.
    expect(screen.getByText("2 draft outcomes found")).toBeInTheDocument();
    view.rerender(<PeopleStep {...people} meeting={extracted} moment={{ job: "job", revision: 1 }} />);
    expect(screen.getByText("2 draft outcomes found")).toBeInTheDocument();
    // The only line view left is the collapsed one below the cards.
    expect(screen.getByRole("region", { name: "Transcript lines" }).closest("details")).not.toHaveAttribute(
      "open",
    );
    expect(start).not.toHaveBeenCalled();
  });

  it("opens a draft card's review inside the app", async () => {
    const onOpenOutcome = vi.fn();
    render(<PeopleStep {...people} meeting={extracted} onOpenOutcome={onOpenOutcome} />);
    await userEvent.click(screen.getByRole("link", { name: /Use the checklist/ }));
    expect(onOpenOutcome).toHaveBeenCalledWith("decision");
  });

  it("consumes a moment once and never spends it on another revision", () => {
    const onMomentDone = vi.fn();
    const moment = { job: "job", revision: 1 };
    const view = render(
      <PeopleStep {...people} meeting={extracted} moment={moment} onMomentDone={onMomentDone} />,
    );
    expect(onMomentDone).toHaveBeenCalledWith("job");
    expect(JSON.parse(localStorage.getItem("m2o-moment")!)).toEqual(["weekly:1"]);
    // A new revision opened while the old moment is still around: it is consumed, not
    // played, so the extraction of revision 2 can still play its own moment later.
    view.unmount();
    render(
      <PeopleStep
        {...people}
        meeting={{ ...extracted, current_revision: 2 }}
        moment={moment}
        onMomentDone={onMomentDone}
      />,
    );
    expect(onMomentDone).toHaveBeenCalledTimes(2);
    expect(JSON.parse(localStorage.getItem("m2o-moment")!)).toEqual(["weekly:1"]);
  });

  it("labels each card by its own evidence and keeps morph names only for an animated moment", async () => {
    // Both outcomes cite line 1; the decision's evidence continues on line 3.
    const shared = {
      ...extracted,
      tasks: [
        { ...action, evidence: [evidence(1, "Alex: Review onboarding", "Alex")] },
        { ...decision, evidence: [evidence(1, "Alex: Review onboarding\nSam: Use the checklist", "Alex")] },
      ],
    } as Meeting;
    // Just enough of the View Transitions API and layout for React's transition to run in jsdom.
    Object.defineProperty(document, "startViewTransition", {
      configurable: true,
      value: (options: StartViewTransitionOptions) => {
        const done = Promise.resolve().then(() => options.update?.());
        return {
          ready: done,
          finished: done,
          updateCallbackDone: done,
          skipTransition() {},
          types: new Set(),
        };
      },
    });
    Object.defineProperty(document, "fonts", { configurable: true, value: { status: "loaded" } });
    Object.defineProperty(document.documentElement, "getAnimations", { configurable: true, value: () => [] });
    Object.defineProperty(Element.prototype, "animate", { configurable: true, value: vi.fn() });
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue(new DOMRect(0, 0, 300, 20));
    try {
      const view = render(<PeopleStep {...people} meeting={shared} extracting />);
      view.rerender(<PeopleStep {...people} meeting={shared} moment={{ job: "first", revision: 1 }} />);
      const decisionCard = await screen.findByRole("link", { name: /Use the checklist/ });
      // Paired with line 3 for the morph, but labelled by where its evidence starts.
      expect(decisionCard).toHaveTextContent("line 1 · Alex");
      expect(decisionCard.closest("li")).toHaveClass("animate-none");
      // A later moment that does not animate (already played) clears the morph names.
      view.rerender(<PeopleStep {...people} meeting={shared} moment={{ job: "second", revision: 1 }} />);
      expect(screen.getByRole("link", { name: /Use the checklist/ }).closest("li")).not.toHaveClass(
        "animate-none",
      );
    } finally {
      Reflect.deleteProperty(document, "fonts");
      Reflect.deleteProperty(document.documentElement, "getAnimations");
      Reflect.deleteProperty(Element.prototype, "animate");
      vi.restoreAllMocks();
    }
  });
});
