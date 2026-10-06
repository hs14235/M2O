import { useEffect, useId, useState } from "react";
import { api, scoped } from "../api";
import type { Kind, Outcome, Participant, Workspace } from "../types";
import { ErrorNotice } from "./Feedback";

export const kindNames: Record<Kind, string> = { action: "Action", decision: "Decision", blocker: "Blocker", follow_up: "Follow-up", risk: "Risk" };
const kinds = Object.keys(kindNames) as Kind[];

export function OutcomeCard({ item, participants, workspace, meetingId, onSaved, onDirty, selected, onSelect, selectable = true }: { item: Outcome; participants: Participant[]; workspace: Workspace; meetingId: string; onSaved: () => void; onDirty: (id: string, dirty: boolean) => void; selected: boolean; onSelect: (id: string, checked: boolean) => void; selectable?: boolean }) {
  const prefix = useId();
  const [title, setTitle] = useState(item.title), [body, setBody] = useState(item.body), [kind, setKind] = useState(item.kind);
  const [labels, setLabels] = useState(item.labels.join(", ")), [owner, setOwner] = useState(item.owner_id || ""), [due, setDue] = useState(item.due_date || "");
  const [error, setError] = useState<unknown>(null), [busy, setBusy] = useState(false), [history, setHistory] = useState<{ version: number; payload: Outcome }[] | null>(null);
  const editable = workspace.role !== "viewer", reviewer = ["owner", "reviewer"].includes(workspace.role);
  const dirty = title !== item.title || body !== item.body || kind !== item.kind || labels !== item.labels.join(", ") || owner !== (item.owner_id || "") || due !== (item.due_date || "");
  useEffect(() => { onDirty(item.id, dirty); return () => onDirty(item.id, false); }, [dirty, item.id, onDirty]);
  async function save(status?: Outcome["status"]) {
    setBusy(true); setError(null);
    try {
      await api(scoped(workspace.id, "/meetings/" + meetingId + "/outcomes/" + item.id), { method: "PATCH", body: JSON.stringify({ expected_version: item.version, ...(dirty ? { title, body, kind, labels: labels.split(",").map(x => x.trim()).filter(Boolean), owner_id: owner || null, due_date: due || null } : {}), ...(status ? { status } : {}) }) });
      onDirty(item.id, false); onSaved();
    } catch (e) { setError(e); } finally { setBusy(false); }
  }
  async function showHistory() {
    try { setHistory(await api(scoped(workspace.id, "/meetings/" + meetingId + "/outcomes/" + item.id + "/history"))); } catch (e) { setError(e); }
  }
  return <article className={"outcome " + item.kind} aria-labelledby={prefix + "-heading"}>
    <div className="outcome-top"><span className="eyebrow">{kindNames[item.kind]}</span><span className="badge">{item.status} · v{item.version}</span></div>
    <h3 id={prefix + "-heading"}>{item.title}</h3>
    <p className="muted">{item.owner_id ? "Confirmed owner" : item.assignee_hint ? "Suggested owner: " + item.assignee_hint : "No owner suggested"}{item.due_date && <> · Reviewed due date: {item.due_date}</>}</p>
    {item.due_hint && !item.due_date && <p className="notice">Date needs review: {item.due_hint}. Set a calendar date after checking the meeting context.</p>}
    <details><summary>Review fields</summary>
      <fieldset disabled={!editable || busy}><legend className="sr-only">Edit {item.title}</legend>
        <label htmlFor={prefix + "-title"}>Title</label><input id={prefix + "-title"} value={title} maxLength={200} onChange={e => setTitle(e.target.value)} />
        <label htmlFor={prefix + "-body"}>Outcome details</label><textarea id={prefix + "-body"} value={body} maxLength={4000} onChange={e => setBody(e.target.value)} rows={3} />
        <div className="form-grid">
          <label>Type<select value={kind} onChange={e => setKind(e.target.value as Kind)}>{kinds.map(k => <option key={k} value={k}>{kindNames[k]}</option>)}</select></label>
          <label>Confirmed owner<select value={owner} onChange={e => setOwner(e.target.value)}><option value="">Unassigned</option>{participants.map(p => <option value={p.id} key={p.id}>{p.name} · {p.role || "Participant"}</option>)}</select></label>
          <label>Due date<input type="date" value={due} onChange={e => setDue(e.target.value)} /></label>
          <label>Labels, separated by commas<input value={labels} onChange={e => setLabels(e.target.value)} /></label>
        </div>
      </fieldset>
      {editable && <button disabled={!dirty || busy || !title.trim()} onClick={() => save()}>Save review</button>}
    </details>
    <details><summary>Evidence · {item.evidence.length} source{item.evidence.length !== 1 ? "s" : ""}</summary>{item.evidence.map(e => <blockquote key={e.id}><cite>Chunk {e.i + 1} · line {e.start_line}{e.speaker ? " · " + e.speaker : ""}</cite><p>{e.text}</p></blockquote>)}</details>
    <div className="actions">
      {reviewer && item.status === "draft" && <button className="primary" disabled={busy || !title.trim()} onClick={() => save("approved")}>Approve outcome</button>}
      {editable && item.status !== "dismissed" && item.status !== "done" && <button disabled={busy} onClick={() => save("dismissed")}>Dismiss</button>}
      {editable && ["done", "dismissed", "approved"].includes(item.status) && <button disabled={busy} onClick={() => save("draft")}>Return to draft</button>}
      <button className="quiet" onClick={showHistory}>Review history</button>
    </div>
    {item.status === "approved" && ["action", "follow_up"].includes(item.kind) && <p className="muted">Approved for handoff. Track your own progress in My day.</p>}
    {selectable && item.status === "approved" && <label className="check"><input type="checkbox" checked={selected} onChange={e => onSelect(item.id, e.target.checked)} disabled={dirty} />Select for handoff</label>}
    {dirty && <p role="status" className="muted">Unsaved review. Editing approved content returns it to draft.</p>}
    <ErrorNotice error={error} />
    {history && <details open><summary>Saved revisions</summary>{history.map(row => <p key={row.version}><strong>v{row.version}</strong> · {row.payload.title} · {row.payload.status || "draft"}</p>)}</details>}
  </article>;
}
