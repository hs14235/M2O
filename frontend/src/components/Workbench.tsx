import { useCallback, useEffect, useRef, useState } from "react";
import { api, scoped } from "../api";
import { examples } from "../demo";
import { meetingStages, routePath, settingsPath, sharePath, type Route, type Step } from "../navigation";
import type { CalendarEntry, Job, Meeting, MeetingSummary, Participant, User, Workspace } from "../types";
import { Empty, ErrorNotice } from "./Feedback";
import { TranscriptStep, PeopleStep, ReviewStep, MeetingHistory } from "./MeetingSteps";
import { ShareStep } from "./ShareStep";
import { ContextBubble } from "./ContextBubble";
import DemoScenarios from "./DemoScenarios";
import OutcomeCalendar from "./OutcomeCalendar";
import type { ImportedMeeting } from "./GoogleMeetImport";
import MeetingList from "./MeetingList";

const stepNames: Record<Step, string> = { transcript: "Transcript", people: "People", review: "Review & Deliver", share: "Review & Deliver", calendar: "Calendar" };

export default function Workbench({ workspace, user, onDirty, route, navigate }: { workspace: Workspace; user: User; onDirty: (dirty: boolean) => void; route: Route; navigate: (path: string) => void }) {
  const [meetings, setMeetings] = useState<MeetingSummary[]>([]), [nextOffset, setNextOffset] = useState<number | null>(null), [active, setActive] = useState(""), [meeting, setMeeting] = useState<Meeting | null>(null), [people, setPeople] = useState<Participant[]>([]);
  const [error, setError] = useState<unknown>(null), [busy, setBusy] = useState(false), [loading, setLoading] = useState(true);
  const [slug, setSlug] = useState(""), [title, setTitle] = useState(""), [text, setText] = useState(""), [visibility, setVisibility] = useState<"workspace" | "restricted">(workspace.department === "hr" ? "restricted" : "workspace"), [occurred, setOccurred] = useState("");
  const [jobId, setJobId] = useState<string | null>(null), [job, setJob] = useState<Job | null>(null), [selected, setSelected] = useState<string[]>([]);
  const dirtyItems = useRef(new Map<string, boolean>()), transcriptDirty = useRef(false), detailRequest = useRef<AbortController | null>(null);
  const [search, setSearch] = useState(""), [query, setQuery] = useState("");
  const currentQuery = useRef(query); currentQuery.current = query;
  useEffect(() => { const timer = setTimeout(() => setQuery(search.trim()), 220); return () => clearTimeout(timer); }, [search]);
  const example = examples[workspace.department], editable = workspace.role !== "viewer";
  const isDirty = Boolean(meeting ? text !== meeting.raw_text || title !== meeting.title : text || title || occurred);
  const notifyDirty = useCallback((id: string, dirty: boolean) => { dirtyItems.current.set(id, dirty); onDirty(transcriptDirty.current || [...dirtyItems.current.values()].some(Boolean)); }, [onDirty]);
  useEffect(() => { transcriptDirty.current = isDirty; onDirty(isDirty || [...dirtyItems.current.values()].some(Boolean)); }, [isDirty, onDirty]);
  useEffect(() => () => { onDirty(false); detailRequest.current?.abort(); }, [onDirty]);

  const list = useCallback(async (offset = 0, signal?: AbortSignal) => {
    const snapshot = query;
    const params = new URLSearchParams({ offset: String(offset), limit: "20", ...(query ? { q: query } : {}) });
    const result = await api<{ meetings: MeetingSummary[]; next_offset: number | null }>(scoped(workspace.id, "/meetings?" + params), { signal });
    if (signal?.aborted || currentQuery.current !== snapshot) return;
    setMeetings(previous => offset ? [...new Map([...previous, ...result.meetings].map(row => [row.id, row])).values()] : result.meetings); setNextOffset(result.next_offset);
  }, [workspace.id, query]);
  const loadPeople = useCallback(async (signal?: AbortSignal) => { const result = await api<Participant[]>(scoped(workspace.id, "/participants"), { signal }); if (!signal?.aborted) setPeople(result); }, [workspace.id]);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setMeetings([]); setNextOffset(null);
    list(0, controller.signal).catch(e => { if (!controller.signal.aborted) setError(e); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [list]);
  useEffect(() => { const controller = new AbortController(); loadPeople(controller.signal).catch(e => { if (!controller.signal.aborted) setError(e); }); return () => controller.abort(); }, [loadPeople]);

  const loadMeeting = useCallback(async (id: string, preserveTranscript = false) => {
    detailRequest.current?.abort(); const controller = new AbortController(); detailRequest.current = controller;
    setLoading(true); setError(null);
    try {
      const row = await api<Meeting>(scoped(workspace.id, "/meetings/" + encodeURIComponent(id)), { signal: controller.signal });
      if (controller.signal.aborted) return;
      if ([...dirtyItems.current.values()].some(Boolean)) { setError(new Error("Save or discard your outcome edit before refreshing this meeting.")); return; }
      setMeeting(row); setActive(id); setSlug(row.id);
      if (!preserveTranscript) { setText(row.raw_text); setTitle(row.title); setOccurred(row.occurred_on || ""); setVisibility(row.visibility); }
      setSelected(previous => previous.filter(id => row.tasks.some(item => item.id === id && item.status === "approved")));
      await list(0, controller.signal); return row;
    } catch (e) { if (!controller.signal.aborted) setError(e); } finally { if (!controller.signal.aborted) setLoading(false); }
  }, [workspace.id, list]);

  useEffect(() => {
    if (route.meeting === active) return;
    detailRequest.current?.abort(); dirtyItems.current.clear(); setSelected([]); setJobId(null); setJob(null); setMeeting(null); setError(null);
    if (route.meeting && route.meeting !== "new") { void loadMeeting(route.meeting); }
    else { setActive(route.meeting || ""); setSlug("meeting-" + crypto.randomUUID()); setTitle(""); setText(""); setOccurred(""); setVisibility(workspace.department === "hr" ? "restricted" : "workspace"); }
  }, [route.meeting, loadMeeting, workspace.department]);

  function go(step: Step, id = active) { navigate(routePath(workspace.id, "meetings", id || "new", step)); }
  function reviewCalendar(entry: CalendarEntry) { navigate(routePath(workspace.id, "meetings", entry.meeting_id, "review") + "?" + new URLSearchParams({ outcome: entry.item_id })); }
  async function openDemo(result: { meeting_id: string; job_id: string | null }) {
    const saved = await loadMeeting(result.meeting_id);
    if (!saved) return;
    setJobId(result.job_id); setJob(null); go("people", saved.id);
  }
  async function imported(result: ImportedMeeting) {
    const saved = await loadMeeting(result.meeting_id); if (!saved) return;
    transcriptDirty.current = false; onDirty(false); setJobId(result.job_id); setJob(null); go("people", saved.id);
  }
  async function save(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(null);
    try {
      const result = await api<{ job_id: string | null }>(scoped(workspace.id, "/index"), { method: "POST", body: JSON.stringify({ meeting_id: slug, title, transcript: text, visibility, occurred_on: occurred || null, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone, ...(meeting ? { expected_version: meeting.version } : {}) }) });
      const saved = await loadMeeting(slug); if (!saved) return;
      transcriptDirty.current = false; onDirty(false); setJobId(result.job_id); setJob(null); go("people", slug);
    } catch (e) { setError(e); } finally { setBusy(false); }
  }
  async function upload(file?: File) {
    if (!file) return;
    try {
      if (!/\.(txt|md)$/i.test(file.name) || file.size > 1_000_000) throw new Error("Choose a UTF-8 .txt or .md file smaller than 1 MB.");
      const value = new TextDecoder("utf-8", { fatal: true }).decode(await file.arrayBuffer());
      setText(value); if (!meeting && !title) setTitle(file.name.replace(/\.[^.]+$/, ""));
    } catch (e) { setError(e); }
  }
  async function extract() {
    setError(null); setBusy(true);
    try { const result = await api<{ job_id: string }>(scoped(workspace.id, "/meetings/" + active + "/extract"), { method: "POST" }); setJobId(result.job_id); setJob(null); } catch (e) { setError(e); } finally { setBusy(false); }
  }
  useEffect(() => {
    if (!jobId) return;
    const controller = new AbortController(); let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const state = await api<Job>(scoped(workspace.id, "/jobs/" + jobId), { signal: controller.signal });
        if (controller.signal.aborted) return;
        setJob(state);
        if (["queued", "running"].includes(state.state)) timer = setTimeout(poll, 1200);
        else if (active && active !== "new") await loadMeeting(active, true);
      } catch (e) { if (!controller.signal.aborted) setError(e); }
    }
    void poll(); return () => { controller.abort(); clearTimeout(timer); };
  }, [jobId, workspace.id, active, loadMeeting]);
  useEffect(() => {
    if (!meeting || meeting.index_status !== "queued" || jobId) return;
    const timer = setTimeout(() => { void loadMeeting(meeting.id, true); }, 1500);
    return () => clearTimeout(timer);
  }, [meeting, jobId, loadMeeting]);
  async function confirm(mentionId: string, participantId: string) {
    setBusy(true); setError(null);
    try { await api(scoped(workspace.id, "/meetings/" + active + "/mentions/" + mentionId + "/confirm"), { method: "POST", body: JSON.stringify({ participant_id: participantId }) }); await loadMeeting(active, true); } catch (e) { setError(e); } finally { setBusy(false); }
  }
  async function archive() {
    if (!meeting || !window.confirm("Archive this meeting? Its transcript and review history will be retained.")) return;
    try { await api(scoped(workspace.id, "/meetings/" + active), { method: "DELETE" }); navigate(routePath(workspace.id)); await list(); } catch (e) { setError(e); }
  }
  async function reconcile() {
    if (!job?.result?.operation_id) return;
    try { const result = await api<NonNullable<Job["result"]>>(scoped(workspace.id, "/operations/" + job.result.operation_id + "/reconcile"), { method: "POST" }); setJob(previous => previous ? { ...previous, result } : previous); } catch (e) { setError(e); }
  }
  function changeReview(action: () => void) {
    if ([...dirtyItems.current.values()].some(Boolean) && !window.confirm("Discard unsaved outcome edits?")) return;
    dirtyItems.current.clear(); onDirty(transcriptDirty.current); action();
  }
  const pending = busy || loading || Boolean(jobId && (!job || ["queued", "running"].includes(job.state)));
  const ready = Boolean(meeting && meeting.index_status === "ready" && !pending);
  const step = meeting || route.meeting === "new" ? route.step : "transcript";
  return <div className={"workbench guided step-" + step}>
    {route.meeting && <ContextBubble label={stepNames[step] + " tools"} hint={{ transcript: "Next: confirm the people and extract outcomes.", people: "Next: review each outcome against its evidence.", review: "Next: choose a handoff after approving the source.", share: "Delivery and your personal progress stay separate.", calendar: "Reviewed dates and your personal plan keep their own meaning." }[step]} actions={[
      { id: "meetings", label: "All meetings", detail: "Return to your saved conversations", run: () => navigate(routePath(workspace.id)) },
      { id: "plan", label: "My day", detail: "Plan approved work and track personal progress", run: () => navigate(routePath(workspace.id, "plan")) },
      ...(step === "people" ? [{ id: "directory", label: "People directory", detail: "Review participant context", run: () => navigate(settingsPath(workspace.id, "people")) }] : []),
      ...(step === "share" ? [{ id: "connections", label: "Connections", detail: "Check provider access and destinations", run: () => navigate(settingsPath(workspace.id, "connections")) }] : []),
    ]} />}
    {!route.meeting ? <><section className="intro"><div><span className="eyebrow">{workspace.name}</span><h1>Make the next step clear.</h1><p>{example.purpose} Start with a transcript, review what matters, and choose how to hand it over.</p></div>{editable && !user.is_visitor && <button className="primary" onClick={() => go("transcript", "new")}>New meeting</button>}</section><ErrorNotice error={error} />{loading && <p role="status">Loading meetings…</p>}
      {user.is_visitor && <DemoScenarios workspace={workspace} disabled={pending} onLoaded={openDemo} />}<MeetingList meetings={meetings} query={search} onQuery={setSearch} loading={loading} hasMore={nextOffset !== null} onMore={() => { setLoading(true); void list(nextOffset!).catch(setError).finally(() => setLoading(false)); }} onOpen={id => go("transcript", id)} visitor={Boolean(user.is_visitor)} /></> : <>
      <div className="meeting-heading"><button className="quiet" onClick={() => navigate(routePath(workspace.id))}>All meetings</button><span>{meeting?.title || "New meeting"}</span>{meeting && <span className="badge">Revision {meeting.current_revision}</span>}</div>
      <nav className="stepper" aria-label="Meeting steps"><ol>{meetingStages.map((value, index) => <li key={value}><button aria-current={(step === "share" ? "review" : step) === value ? "step" : undefined} className={(step === "share" ? "review" : step) === value ? "active" : ""} disabled={value !== "transcript" && (!meeting || (value !== "people" && !ready))} onClick={() => go(value)}><span aria-hidden="true">{index + 1}</span>{stepNames[value]}</button></li>)}</ol></nav>
      <ErrorNotice error={error} />{loading && <p role="status">Loading meeting…</p>}
      {meeting && (step === "review" || step === "share") && <nav className="review-deliver-tabs" aria-label="Review and delivery"><button aria-pressed={step === "review"} onClick={() => go("review")}>Review outcomes</button><button aria-pressed={step === "share"} onClick={() => go("share")}>Prepare delivery</button><button className="quiet" onClick={() => go("calendar")}>View outcome calendar</button></nav>}
      {job && <div className={"notice " + (job.state === "failed" ? "error" : "")} role="status"><strong>{job.kind?.includes("publish") ? "Delivery processing" : "Job"} {job.state}</strong>{job.kind?.includes("publish") && <span> · Check the provider receipt for its actual result.</span>}{job.error_code && <span> · {job.kind === "extract" ? "Extraction did not finish. You can retry or ask the application operator to check the worker." : "The operation did not finish. Check its receipt before trying another delivery."}</span>}{job.result?.mode && <span> · {job.result.mode === "rules" ? "Rule-based extraction" : job.result.mode === "ollama" ? "Local AI extraction" : job.result.mode === "mixed" ? "Mixed local AI and rule-based extraction" : "Extraction mode: " + job.result.mode} · {job.result.created} new outcomes</span>}{job.result?.coverage && <details><summary>Processing details</summary><p>Processed {job.result.coverage.processed_chunks}/{job.result.coverage.total_chunks} chunks. {job.result.coverage.warnings.join(" ")}</p></details>}{job.result?.results?.map((result, i) => <p key={i}>{result.status}{result.url && <> · <a href={result.url} target="_blank" rel="noopener noreferrer">Open delivered outcome</a></>}</p>)}{job.kind === "publish" && job.result?.state === "uncertain" && ["owner", "reviewer"].includes(workspace.role) && <button onClick={reconcile}>Check uncertain delivery status</button>}</div>}
      {user.is_visitor && step === "transcript" && (meeting ? <section className="panel step-panel"><span className="eyebrow">Synthetic source</span><h1>Inspect the conversation.</h1><p>This is an approved, immutable demo transcript. Your outcome reviews and personal plan are editable; real uploads belong in invited private workspaces.</p><pre className="payload-text">{meeting.raw_text}</pre><button className="primary" onClick={() => go("people")}>Continue to people</button></section> : <DemoScenarios workspace={workspace} disabled={pending} onLoaded={openDemo} />)}{!user.is_visitor && (meeting || route.meeting === "new") && step === "transcript" && <TranscriptStep workspace={workspace} onImported={imported} meeting={meeting} title={title} setTitle={setTitle} text={text} setText={setText} slug={slug} setSlug={setSlug} occurred={occurred} setOccurred={setOccurred} visibility={visibility} setVisibility={setVisibility} editable={editable} pending={pending} dirty={isDirty} onSubmit={save} onUpload={upload} onExample={() => { setTitle(example.title); setText(example.text); }} onContinue={() => go("people")} department={workspace.department} />}
      {meeting && step === "people" && <PeopleStep directoryEditable={!user.is_visitor} meeting={meeting} people={people} workspace={workspace} pending={pending} ready={ready} onExtract={extract} onConfirm={confirm} onParticipantAdded={loadPeople} onDirty={notifyDirty} onBack={() => go("transcript")} onContinue={() => go("review")} />}
      {meeting && step === "review" && <ReviewStep focusItem={route.outcome} meeting={meeting} people={people} workspace={workspace} pending={pending} onDirty={notifyDirty} onSaved={() => loadMeeting(active, true)} changeReview={changeReview} onBack={() => go("people")} onContinue={() => go("share")} />}
      {meeting && step === "share" && <ShareStep key={meeting.id} meeting={meeting} workspace={workspace} user={user} selected={selected} onSelect={(id, checked) => setSelected(previous => checked ? [...new Set([...previous, id])] : previous.filter(value => value !== id))} onJob={id => { setJobId(id); setJob(null); }} onBack={() => go("review")} onConnections={() => navigate(settingsPath(workspace.id, "connections"))} stage={route.handoff || "choose"} provider={route.provider} onStage={(stage, provider) => navigate(sharePath(workspace.id, meeting.id, stage, provider))} onPlan={() => navigate(routePath(workspace.id, "plan"))} onCalendar={() => go("calendar")} />}
      {meeting && step === "calendar" && <OutcomeCalendar workspace={workspace} meetingId={meeting.id} meetingTitle={meeting.title} onReview={reviewCalendar} onBack={() => go("review")} />}
      {meeting && step === "transcript" && <MeetingHistory meeting={meeting} workspace={workspace} onArchive={archive} />}
    </>}
  </div>;
}
