import { useCallback, useEffect, useRef, useState } from "react";
import { api, scoped } from "../api";
import { examples } from "../demo";
import { routePath, settingsPath, sharePath, type Route, type Step } from "../navigation";
import type { CalendarEntry, Job, Meeting, User, Workspace } from "../types";
import { ErrorNotice } from "./Feedback";
import { TranscriptStep, PeopleStep, ReviewStep, MeetingHistory } from "./MeetingSteps";
import { ShareStep } from "./ShareStep";
import { ContextBubble } from "./ContextBubble";
import DemoScenarios from "./DemoScenarios";
import OutcomeCalendar from "./OutcomeCalendar";
import type { ImportedMeeting } from "./GoogleMeetImport";
import MeetingList from "./MeetingList";
import { JobStatus } from "./workbench/JobStatus";
import { MeetingHeader, stepNames } from "./workbench/MeetingHeader";
import { WorkbenchNotices } from "./workbench/WorkbenchNotices";
import { useDirtyTracking } from "./workbench/useDirtyTracking";
import { useJobPolling } from "./workbench/useJobPolling";
import { useMeetingSearch } from "./workbench/useMeetingSearch";
import { usePeople } from "./workbench/usePeople";
import { stagger, useStepReveal } from "../motion";
import { useRouteFence } from "./workbench/useRouteFence";
import { reviewOutcomePath } from "./workbench/links";

const stepHints: Record<Step, string> = {
  transcript: "Next: confirm the people and extract outcomes.",
  people: "Next: review each outcome against its evidence.",
  review: "Next: choose a handoff after approving the source.",
  share: "Delivery and your personal progress stay separate.",
  calendar: "Reviewed dates and your personal plan keep their own meaning.",
};

type AcceptedSave = { meetingId: string; jobId: string | null };

/**
 * One meeting's guided workflow: Transcript → People → Review & Deliver → Calendar.
 *
 * Loading, saving and extraction stay together here because they share the route
 * fence: every write records the route generation it started in and ignores its
 * result if the user has since navigated (see useRouteFence).
 */
export default function Workbench({
  workspace,
  user,
  onDirty,
  route,
  navigate,
}: {
  workspace: Workspace;
  user: User;
  onDirty: (dirty: boolean) => void;
  route: Route;
  navigate: (path: string) => void;
}) {
  const [active, setActive] = useState(""),
    [meeting, setMeeting] = useState<Meeting | null>(null);
  const [error, setError] = useState<unknown>(null),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true);
  const [slug, setSlug] = useState(""),
    [title, setTitle] = useState(""),
    [text, setText] = useState(""),
    [visibility, setVisibility] = useState<"workspace" | "restricted">(
      workspace.department === "hr" ? "restricted" : "workspace",
    ),
    [occurred, setOccurred] = useState("");
  const [jobId, setJobId] = useState<string | null>(null),
    [selected, setSelected] = useState<string[]>([]);
  const [acceptedSave, setAcceptedSave] = useState<AcceptedSave | null>(null),
    [meetingReadFailed, setMeetingReadFailed] = useState(false);
  const mutation = useRef(false),
    detailRequest = useRef<AbortController | null>(null);
  // The signature moment on People (see PeopleStep): the extraction started here, and
  // once that job finished with outcomes, its id and the revision it produced. People
  // reports when it played the moment, which consumes it.
  const [extractJob, setExtractJob] = useState<string | null>(null),
    [moment, setMoment] = useState<{ job: string; revision: number } | null>(null);
  const momentDone = useCallback(
    (job: string) => setMoment((current) => (current?.job === job ? null : current)),
    [],
  );

  const { meetings, nextOffset, search, setSearch, list, reset: resetList } = useMeetingSearch(workspace.id);
  const example = examples[workspace.department],
    editable = workspace.role !== "viewer";
  const isDirty =
    !acceptedSave &&
    Boolean(meeting ? text !== meeting.raw_text || title !== meeting.title : text || title || occurred);
  const { dirtyItems, transcriptDirty, notifyDirty, hasDirtyItems } = useDirtyTracking(onDirty, isDirty);
  useEffect(
    () => () => {
      onDirty(false);
      detailRequest.current?.abort();
    },
    [onDirty],
  );
  const { generation: routeGeneration, mounted } = useRouteFence(
    JSON.stringify([workspace.id, route.meeting, route.step]),
  );

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    resetList();
    list(0, controller.signal)
      .catch((e) => {
        if (!controller.signal.aborted) setError(e);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [list, resetList]);
  const { people, loadPeople } = usePeople(workspace.id, setError);

  const loadMeeting = useCallback(
    async (id: string, preserveTranscript = false) => {
      detailRequest.current?.abort();
      const controller = new AbortController();
      detailRequest.current = controller;
      setLoading(true);
      setError(null);
      try {
        const row = await api<Meeting>(scoped(workspace.id, "/meetings/" + encodeURIComponent(id)), {
          signal: controller.signal,
        });
        if (controller.signal.aborted) return;
        if (hasDirtyItems()) {
          setError(new Error("Save or discard your outcome edit before refreshing this meeting."));
          return;
        }
        setMeeting(row);
        setActive(id);
        setSlug(row.id);
        setMeetingReadFailed(false);
        if (!preserveTranscript) {
          setText(row.raw_text);
          setTitle(row.title);
          setOccurred(row.occurred_on || "");
          setVisibility(row.visibility);
        }
        setSelected((previous) =>
          previous.filter((id) => row.tasks.some((item) => item.id === id && item.status === "approved")),
        );
        try {
          await list(0, controller.signal);
        } catch (e) {
          if (!controller.signal.aborted) setError(e);
        }
        return controller.signal.aborted ? undefined : row;
      } catch (e) {
        if (!controller.signal.aborted) {
          setError(e);
          setMeetingReadFailed(true);
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    },
    [workspace.id, list, hasDirtyItems],
  );

  useEffect(() => {
    if (route.meeting === active) return;
    detailRequest.current?.abort();
    dirtyItems.current.clear();
    setSelected([]);
    setJobId(null);
    setJob(null);
    setJobReadError(null);
    setExtractJob(null);
    setMoment(null);
    setAcceptedSave(null);
    setMeetingReadFailed(false);
    setMeeting(null);
    setError(null);
    if (route.meeting && route.meeting !== "new") {
      void loadMeeting(route.meeting);
    } else {
      setActive(route.meeting || "");
      setSlug("meeting-" + crypto.randomUUID());
      setTitle("");
      setText("");
      setOccurred("");
      setVisibility(workspace.department === "hr" ? "restricted" : "workspace");
    }
  }, [route.meeting, loadMeeting, workspace.department]);

  function go(step: Step, id = active) {
    navigate(routePath(workspace.id, "meetings", id || "new", step));
  }
  function reviewCalendar(entry: CalendarEntry) {
    navigate(reviewOutcomePath(workspace.id, entry.meeting_id, entry.item_id));
  }
  async function openDemo(result: { meeting_id: string; job_id: string | null }) {
    const saved = await loadMeeting(result.meeting_id);
    if (!saved) return;
    setJobId(result.job_id);
    setJob(null);
    go("people", saved.id);
  }
  async function imported(result: ImportedMeeting) {
    const saved = await loadMeeting(result.meeting_id);
    if (!saved) return;
    transcriptDirty.current = false;
    onDirty(false);
    setJobId(result.job_id);
    setJob(null);
    go("people", saved.id);
  }
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (mutation.current || acceptedSave) return;
    mutation.current = true;
    const generation = routeGeneration.current;
    setBusy(true);
    setError(null);
    try {
      const result = await api<{ job_id: string | null }>(scoped(workspace.id, "/index"), {
        method: "POST",
        body: JSON.stringify({
          meeting_id: slug,
          title,
          transcript: text,
          visibility,
          occurred_on: occurred || null,
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
          ...(meeting ? { expected_version: meeting.version } : {}),
        }),
      });
      if (!mounted.current || routeGeneration.current !== generation) return;
      const accepted = { meetingId: slug, jobId: result.job_id };
      setAcceptedSave(accepted);
      setJobId(result.job_id);
      setJob(null);
      await completeSave(accepted, generation);
    } catch (e) {
      if (mounted.current && routeGeneration.current === generation) setError(e);
    } finally {
      mutation.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  async function completeSave(accepted: AcceptedSave, generation: number) {
    const saved = await loadMeeting(accepted.meetingId);
    if (!saved || !mounted.current || routeGeneration.current !== generation) return;
    setAcceptedSave(null);
    transcriptDirty.current = false;
    onDirty(false);
    go("people", saved.id);
  }
  async function recoverSave() {
    if (!acceptedSave || mutation.current) return;
    mutation.current = true;
    setBusy(true);
    try {
      await completeSave(acceptedSave, routeGeneration.current);
    } finally {
      mutation.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  async function upload(file?: File) {
    if (!file) return;
    try {
      if (!/\.(txt|md)$/i.test(file.name) || file.size > 1_000_000)
        throw new Error("Choose a UTF-8 .txt or .md file smaller than 1 MB.");
      const value = new TextDecoder("utf-8", { fatal: true }).decode(await file.arrayBuffer());
      setText(value);
      if (!meeting && !title) setTitle(file.name.replace(/\.[^.]+$/, ""));
    } catch (e) {
      setError(e);
    }
  }
  async function transcribeRecording(file?: File) {
    if (!file || mutation.current) return;
    if (
      text.trim() &&
      !window.confirm(
        "Transcribe this recording into a new meeting and discard the unsaved text in the editor?",
      )
    )
      return;
    mutation.current = true;
    const generation = routeGeneration.current;
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("meeting_id", slug);
      form.append("title", title || file.name.replace(/\.[^.]+$/, ""));
      form.append("visibility", visibility);
      if (occurred) form.append("occurred_on", occurred);
      form.append("timezone", Intl.DateTimeFormat().resolvedOptions().timeZone);
      const result = await api<{ job_id: string; meeting_id: string }>(scoped(workspace.id, "/transcribe"), {
        method: "POST",
        body: form,
      });
      if (!mounted.current || routeGeneration.current !== generation) return;
      // The recording becomes its own meeting; the editor's draft is no longer pending work.
      setText("");
      setTitle("");
      transcriptDirty.current = false;
      onDirty(false);
      setJobId(result.job_id);
      setJob(null);
    } catch (e) {
      if (mounted.current && routeGeneration.current === generation) setError(e);
    } finally {
      mutation.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  async function extract() {
    if (mutation.current) return;
    mutation.current = true;
    const generation = routeGeneration.current;
    setError(null);
    setBusy(true);
    try {
      const result = await api<{ job_id: string }>(scoped(workspace.id, "/meetings/" + active + "/extract"), {
        method: "POST",
      });
      if (mounted.current && routeGeneration.current === generation) {
        setJobId(result.job_id);
        setJob(null);
        setExtractJob(result.job_id);
      }
    } catch (e) {
      if (mounted.current && routeGeneration.current === generation) setError(e);
    } finally {
      mutation.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  const { job, setJob, reloaded, jobReadError, setJobReadError, jobReading, readAgain } = useJobPolling({
    workspaceId: workspace.id,
    jobId,
    active,
    loadMeeting,
  });
  // A finished transcription created a new meeting: open it once (its index job runs next).
  const openedTranscription = useRef<string | null>(null);
  useEffect(() => {
    if (job?.kind !== "transcribe" || job.state !== "completed" || !job.result?.meeting_id) return;
    if (openedTranscription.current === job.id) return;
    openedTranscription.current = job.id;
    navigate(routePath(workspace.id, "meetings", job.result.meeting_id, "transcript"));
  }, [job, navigate, workspace.id]);
  // Decide the moment once per extraction. "Job completed" shows before the meeting
  // reloads, so wait for the reload of this job: only its meeting carries the new
  // outcomes. A refused or failed reload shows the result without the moment. The ref
  // keeps late polls and StrictMode's repeated effects from deciding twice.
  const momentJob = useRef<string | null>(null);
  useEffect(() => {
    if (!extractJob || job?.id !== extractJob || ["queued", "running"].includes(job.state)) return;
    const live = job.state === "completed" && route.step === "people";
    if (live && reloaded?.job !== job.id) return;
    setExtractJob(null);
    if (live && reloaded?.ok && meeting?.tasks.length && momentJob.current !== job.id) {
      momentJob.current = job.id;
      setMoment({ job: job.id, revision: meeting.current_revision });
    }
  }, [extractJob, job, reloaded, meeting, route.step]);
  useEffect(() => {
    if (!meeting || meeting.index_status !== "queued" || jobId) return;
    const timer = setTimeout(() => {
      void loadMeeting(meeting.id, true);
    }, 1500);
    return () => clearTimeout(timer);
  }, [meeting, jobId, loadMeeting]);
  async function confirm(mentionId: string, participantId: string) {
    setBusy(true);
    setError(null);
    try {
      await api(scoped(workspace.id, "/meetings/" + active + "/mentions/" + mentionId + "/confirm"), {
        method: "POST",
        body: JSON.stringify({ participant_id: participantId }),
      });
      await loadMeeting(active, true);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  async function archive() {
    if (
      !meeting ||
      !window.confirm("Archive this meeting? Its transcript and review history will be retained.")
    )
      return;
    try {
      await api(scoped(workspace.id, "/meetings/" + active), { method: "DELETE" });
      navigate(routePath(workspace.id));
      await list();
    } catch (e) {
      setError(e);
    }
  }
  async function reconcile() {
    if (!job?.result?.operation_id) return;
    try {
      const result = await api<NonNullable<Job["result"]>>(
        scoped(workspace.id, "/operations/" + job.result.operation_id + "/reconcile"),
        { method: "POST" },
      );
      setJob((previous) => (previous ? { ...previous, result } : previous));
    } catch (e) {
      setError(e);
    }
  }
  function changeReview(action: () => void) {
    if (hasDirtyItems() && !window.confirm("Discard unsaved outcome edits?")) return;
    dirtyItems.current.clear();
    onDirty(transcriptDirty.current);
    action();
  }
  const pending =
    busy ||
    loading ||
    meetingReadFailed ||
    Boolean(acceptedSave) ||
    Boolean(jobId && (!job || ["queued", "running"].includes(job.state)));
  const ready = Boolean(meeting && meeting.index_status === "ready" && !pending);
  const step = meeting || route.meeting === "new" ? route.step : "transcript";
  return (
    <div className={"workbench guided step-" + step}>
      {route.meeting && (
        <ContextBubble
          label={stepNames[step] + " tools"}
          hint={stepHints[step]}
          actions={[
            {
              id: "meetings",
              label: "All meetings",
              detail: "Return to your saved conversations",
              run: () => navigate(routePath(workspace.id)),
            },
            {
              id: "plan",
              label: "My day",
              detail: "Plan approved work and track personal progress",
              run: () => navigate(routePath(workspace.id, "plan")),
            },
            ...(step === "people"
              ? [
                  {
                    id: "directory",
                    label: "People directory",
                    detail: "Review participant context",
                    run: () => navigate(settingsPath(workspace.id, "people")),
                  },
                ]
              : []),
            ...(step === "share"
              ? [
                  {
                    id: "connections",
                    label: "Connections",
                    detail: "Check provider access and destinations",
                    run: () => navigate(settingsPath(workspace.id, "connections")),
                  },
                ]
              : []),
          ]}
        />
      )}
      {!route.meeting ? (
        <>
          <section className="intro">
            <div className="reveal-seq">
              <h1>Meetings</h1>
              <p className="page-hint">{example.purpose}</p>
            </div>
            {editable && !user.is_visitor && (
              <button className="primary reveal" style={stagger(3)} onClick={() => go("transcript", "new")}>
                New meeting
              </button>
            )}
          </section>
          <ErrorNotice error={error} />
          {loading && <p role="status">Loading meetings…</p>}
          {user.is_visitor && <DemoScenarios workspace={workspace} disabled={pending} onLoaded={openDemo} />}
          <MeetingList
            meetings={meetings}
            query={search}
            onQuery={setSearch}
            loading={loading}
            hasMore={nextOffset !== null}
            onMore={() => {
              setLoading(true);
              void list(nextOffset!)
                .catch(setError)
                .finally(() => setLoading(false));
            }}
            onOpen={(id) => go("transcript", id)}
            visitor={Boolean(user.is_visitor)}
          />
        </>
      ) : (
        <>
          <MeetingHeader
            meeting={meeting}
            step={step}
            ready={ready}
            onAllMeetings={() => navigate(routePath(workspace.id))}
            onStep={(value) => go(value)}
          />
          <ErrorNotice error={error} />
          {loading && <p role="status">Loading meeting…</p>}
          <WorkbenchNotices
            acceptedSave={Boolean(acceptedSave)}
            meetingReadFailed={meetingReadFailed}
            jobReadError={jobReadError}
            job={job}
            busy={busy}
            loading={loading}
            jobReading={jobReading}
            onLoadSaved={recoverSave}
            onReloadMeeting={() => route.meeting && void loadMeeting(route.meeting, true)}
            onReadJobAgain={readAgain}
          />
          {meeting && (step === "review" || step === "share") && (
            <nav className="review-deliver-tabs" aria-label="Review and delivery">
              <button aria-pressed={step === "review"} onClick={() => go("review")}>
                Review outcomes
              </button>
              <button aria-pressed={step === "share"} onClick={() => go("share")}>
                Prepare delivery
              </button>
              <button className="quiet" onClick={() => go("calendar")}>
                View outcome calendar
              </button>
            </nav>
          )}
          {job && <JobStatus job={job} role={workspace.role} onReconcile={reconcile} />}
          {user.is_visitor &&
            step === "transcript" &&
            (meeting ? (
              <SyntheticSource text={meeting.raw_text} onContinue={() => go("people")} />
            ) : (
              <DemoScenarios workspace={workspace} disabled={pending} onLoaded={openDemo} />
            ))}
          {!user.is_visitor && (meeting || route.meeting === "new") && step === "transcript" && (
            <TranscriptStep
              workspace={workspace}
              onImported={imported}
              meeting={meeting}
              title={title}
              setTitle={setTitle}
              text={text}
              setText={setText}
              slug={slug}
              setSlug={setSlug}
              occurred={occurred}
              setOccurred={setOccurred}
              visibility={visibility}
              setVisibility={setVisibility}
              editable={editable}
              pending={pending}
              dirty={isDirty}
              onSubmit={save}
              onUpload={upload}
              onAudio={user.capabilities.can_transcribe_audio ? transcribeRecording : undefined}
              onExample={() => {
                setTitle(example.title);
                setText(example.text);
              }}
              onContinue={() => go("people")}
              department={workspace.department}
            />
          )}
          {meeting && step === "people" && (
            <PeopleStep
              directoryEditable={!user.is_visitor}
              meeting={meeting}
              people={people}
              workspace={workspace}
              pending={pending}
              ready={ready}
              onExtract={extract}
              onConfirm={confirm}
              onParticipantAdded={loadPeople}
              onDirty={notifyDirty}
              onBack={() => go("transcript")}
              onContinue={() => go("review")}
              extracting={Boolean(extractJob)}
              moment={moment}
              onMomentDone={momentDone}
              onOpenOutcome={(id) => navigate(reviewOutcomePath(workspace.id, meeting.id, id))}
            />
          )}
          {meeting && step === "review" && (
            <ReviewStep
              focusItem={route.outcome}
              meeting={meeting}
              people={people}
              workspace={workspace}
              pending={pending}
              onDirty={notifyDirty}
              onSaved={() => loadMeeting(active, true)}
              changeReview={changeReview}
              onBack={() => go("people")}
              onContinue={() => go("share")}
            />
          )}
          {meeting && step === "share" && (
            <ShareStep
              key={meeting.id}
              meeting={meeting}
              workspace={workspace}
              user={user}
              selected={selected}
              onSelect={(id, checked) =>
                setSelected((previous) =>
                  checked ? [...new Set([...previous, id])] : previous.filter((value) => value !== id),
                )
              }
              onJob={(id) => {
                setJobId(id);
                setJob(null);
              }}
              onBack={() => go("review")}
              onConnections={() => navigate(settingsPath(workspace.id, "connections"))}
              stage={route.handoff || "choose"}
              provider={route.provider}
              onStage={(stage, provider) => navigate(sharePath(workspace.id, meeting.id, stage, provider))}
              onPlan={() => navigate(routePath(workspace.id, "plan"))}
              onCalendar={() => go("calendar")}
            />
          )}
          {meeting && step === "calendar" && (
            <OutcomeCalendar
              workspace={workspace}
              meetingId={meeting.id}
              meetingTitle={meeting.title}
              onReview={reviewCalendar}
              onBack={() => go("review")}
            />
          )}
          {meeting && step === "transcript" && (
            <MeetingHistory meeting={meeting} workspace={workspace} onArchive={archive} />
          )}
        </>
      )}
    </div>
  );
}

/** The visitor's read-only demo transcript, revealed like the other steps. */
function SyntheticSource({ text, onContinue }: { text: string; onContinue: () => void }) {
  const reveal = useStepReveal();
  return (
    <section className={"panel step-panel " + reveal}>
      <h1>Transcript</h1>
      <p>
        This is an approved, immutable demo transcript. Your outcome reviews and personal plan are editable;
        real uploads belong in invited private workspaces.
      </p>
      <pre className="payload-text">{text}</pre>
      <button className="primary" onClick={onContinue}>
        Continue to people
      </button>
    </section>
  );
}
