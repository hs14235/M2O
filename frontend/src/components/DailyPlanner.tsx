import { useCallback, useEffect, useRef, useState } from "react";
import { api, scoped } from "../api";
import { routePath } from "../navigation";
import type { DailyPlan, ExecutionState, PlanEntry, PlanSource, Workspace } from "../types";
import { Empty, ErrorNotice } from "./Feedback";
import { ContextBubble } from "./ContextBubble";

export function localDay() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}
const states: Record<ExecutionState, string> = { planned: "Planned", in_progress: "In progress", blocked: "Blocked", done: "Done" };

export default function DailyPlanner({ workspace, navigate }: { workspace: Workspace; navigate: (path: string) => void }) {
  const [day, setDay] = useState(localDay), [plan, setPlan] = useState<DailyPlan | null>(null), [error, setError] = useState<unknown>(null), [busy, setBusy] = useState(false);
  const [query, setQuery] = useState(""), [candidatePage, setCandidatePage] = useState(0), [entryPage, setEntryPage] = useState(0), [completedOpen, setCompletedOpen] = useState(false);
  const search = useRef<HTMLInputElement>(null), completed = useRef<HTMLDetailsElement>(null);
  const editable = workspace.role !== "viewer";
  const load = useCallback(async (signal?: AbortSignal) => {
    const result = await api<DailyPlan>(scoped(workspace.id, "/plan?day=" + encodeURIComponent(day)), { signal });
    if (!signal?.aborted) setPlan(result);
  }, [day, workspace.id]);
  useEffect(() => {
    const controller = new AbortController(); setPlan(null); setError(null); setQuery(""); setCandidatePage(0); setEntryPage(0); setCompletedOpen(false);
    load(controller.signal).catch(e => { if (!controller.signal.aborted) setError(e); });
    return () => controller.abort();
  }, [load]);
  async function change(item: PlanSource, entry?: PlanEntry, values?: Partial<Pick<PlanEntry, "state" | "planned_on" | "priority">>, remove = false) {
    setBusy(true); setError(null);
    try {
      await api(scoped(workspace.id, "/meetings/" + encodeURIComponent(item.meeting_id) + "/outcomes/" + item.item_id + "/plan"), {
        method: remove ? "DELETE" : entry ? "PATCH" : "POST",
        ...(!remove ? { body: JSON.stringify({ expected_item_version: item.item_version, planned_on: entry?.planned_on || day, priority: entry?.priority || 2, ...(entry ? { expected_version: entry.version, state: entry.state } : {}), ...values }) } : {}),
      });
      await load();
      if (values?.state === "done") setCompletedOpen(true);
    } catch (e) { setError(e); } finally { setBusy(false); }
  }
  function open(item: PlanSource) { navigate(routePath(workspace.id, "meetings", item.meeting_id, "review")); }
  const done = plan?.entries.filter(entry => entry.state === "done" && !entry.stale).length || 0;
  const active = plan?.entries.filter(entry => entry.state !== "done" || entry.stale) || [];
  const completedItems = plan?.entries.filter(entry => entry.state === "done" && !entry.stale) || [];
  const candidates = plan?.candidates.filter(item => (item.title + " " + item.meeting_title).toLocaleLowerCase().includes(query.toLocaleLowerCase())) || [];
  const safeEntryPage = Math.min(entryPage, Math.max(0, Math.ceil(active.length / 6) - 1));
  const safeCandidatePage = Math.min(candidatePage, Math.max(0, Math.ceil(candidates.length / 8) - 1));
  function card(entry: PlanEntry) {
    return <article className={"panel plan-card " + (entry.stale ? "stale" : entry.state)} key={entry.id}><span className="eyebrow">{entry.meeting_title}</span><h3>{entry.title}</h3><p className="muted">Reviewed v{entry.reviewed_version} · current v{entry.item_version}{entry.due_date ? " · due " + entry.due_date : entry.due_hint ? " · date needs review" : ""}</p>{entry.stale && <p className="notice">The outcome or transcript changed. Review the source before continuing.</p>}
      <fieldset disabled={!editable || busy}><legend className="sr-only">Plan {entry.title}</legend><label>Progress for {entry.title}<select value={entry.state} disabled={entry.stale} onChange={e => change(entry, entry, { state: e.target.value as ExecutionState })}>{Object.entries(states).map(([value, name]) => <option key={value} value={value}>{name}</option>)}</select></label><details className="plan-schedule"><summary>Priority & date · {entry.priority === 1 ? "Focus first" : entry.priority === 2 ? "Next up" : "When ready"}</summary><div className="form-grid"><label>Priority for {entry.title}<select value={entry.priority} disabled={entry.stale} onChange={e => change(entry, entry, { priority: Number(e.target.value) })}><option value={1}>Focus first</option><option value={2}>Next up</option><option value={3}>When ready</option></select></label><label>Planned date for {entry.title}<input type="date" required value={entry.planned_on} disabled={entry.stale} onChange={e => e.target.value && change(entry, entry, { planned_on: e.target.value })} /></label></div></details></fieldset>
      <div className="actions"><button onClick={() => open(entry)}>Review source</button>{editable && entry.stale && entry.can_reconfirm && <button disabled={busy} onClick={() => change(entry, entry, { state: "planned" })}>Reconfirm current version</button>}{editable && <button className="quiet" disabled={busy} onClick={() => change(entry, entry, undefined, true)}>Remove from my plan</button>}</div></article>;
  }
  async function retryLoad() {
    setBusy(true); setError(null);
    try { await load(); } catch (e) { setError(e); } finally { setBusy(false); }
  }
  return <div className="daily-planner"><div className="section-heading"><div><span className="eyebrow">Your daily plan</span><h1>A clear day starts here.</h1><p>Plan approved actions and follow-ups. Your personal progress is separate from review and delivery.</p></div><label>Plan date<input type="date" required value={day} disabled={busy} onChange={e => e.target.value && setDay(e.target.value)} /></label></div><ErrorNotice error={error} />
    <ContextBubble label="My day tools" hint="A reviewed outcome can join your plan without changing its owner or external status." actions={[
      { id: "candidates", label: "Find reviewed work", detail: "Search the available actions below", disabled: !plan, run: () => { search.current?.scrollIntoView({ block: "center", behavior: "instant" }); search.current?.focus(); } },
      { id: "completed", label: "Completed work", detail: `${done} complete in this plan`, disabled: !done, run: () => { setCompletedOpen(true); requestAnimationFrame(() => { completed.current?.scrollIntoView({ block: "start", behavior: "instant" }); completed.current?.querySelector("summary")?.focus(); }); } },
      { id: "meeting", label: "Open meetings", detail: "Review the source before adding work", run: () => navigate(routePath(workspace.id)) },
    ]} />
    {!plan ? error ? <Empty>Your plan could not be loaded. Your stored progress has not changed.<button disabled={busy} onClick={retryLoad}>Try loading plan again</button></Empty> : <p role="status">Loading your plan…</p> : <><div className="plan-summary" role="status"><strong>{plan.entries.length} planned</strong><span>{done} complete</span><span>{plan.entries.filter(entry => entry.stale).length} need review</span></div>
      <section aria-labelledby="plan-heading"><h2 id="plan-heading">Make space for what matters</h2>{!plan.entries.length && <Empty>No work planned for this date. Add a reviewed outcome below, or review a meeting first.</Empty>}{plan.entries.length > 0 && active.length === 0 && <div className="plan-finish"><span aria-hidden="true">✦</span><div><h3>Room to breathe.</h3><p>All {done} items in this plan are complete. Your source reviews and team tools keep their own status.</p></div></div>}<div className="plan-grid">{active.slice(safeEntryPage * 6, (safeEntryPage + 1) * 6).map(card)}</div>{active.length > 6 && <div className="page-controls"><button disabled={safeEntryPage === 0} onClick={() => setEntryPage(safeEntryPage - 1)}>Previous planned items</button><span>Page {safeEntryPage + 1} of {Math.ceil(active.length / 6)}</span><button disabled={(safeEntryPage + 1) * 6 >= active.length} onClick={() => setEntryPage(safeEntryPage + 1)}>Next planned items</button></div>}{done > 0 && <details ref={completed} className="plan-completed" open={completedOpen} onToggle={event => setCompletedOpen(event.currentTarget.open)}><summary>Completed in this plan · {done}</summary><div className="plan-grid">{completedItems.map(card)}</div></details>}{plan.entries_truncated && <p className="notice">Showing the first 200 entries for this date.</p>}</section>
      <section className="panel"><h2>Ready to plan</h2><p>These are approved actions and follow-ups from meetings you can access. Adding one does not reassign its owner.</p><label>Find reviewed work<input ref={search} type="search" value={query} onChange={event => { setQuery(event.target.value); setCandidatePage(0); }} placeholder="Outcome or meeting name" /></label>{!plan.candidates.length ? <Empty>No unplanned approved actions yet. Open Meetings to review an outcome.</Empty> : !candidates.length ? <Empty>No available outcomes match this search.</Empty> : <><ul className="plan-candidates">{candidates.slice(safeCandidatePage * 8, (safeCandidatePage + 1) * 8).map(item => <li key={item.item_id}><div><strong>{item.title}</strong><small>{item.meeting_title}</small></div><button onClick={() => open(item)}>View source</button>{editable && <button className="primary" disabled={busy} onClick={() => change(item)}>Add to this day</button>}</li>)}</ul>{candidates.length > 8 && <div className="page-controls"><button disabled={safeCandidatePage === 0} onClick={() => setCandidatePage(safeCandidatePage - 1)}>Previous reviewed items</button><span>Page {safeCandidatePage + 1} of {Math.ceil(candidates.length / 8)}</span><button disabled={(safeCandidatePage + 1) * 8 >= candidates.length} onClick={() => setCandidatePage(safeCandidatePage + 1)}>Next reviewed items</button></div>}</>}{plan.candidates_truncated && <p className="notice">Search covers the 100 most recently reviewed candidates available here.</p>}</section>
    </>}
  </div>;
}
