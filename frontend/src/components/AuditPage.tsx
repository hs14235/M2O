import { useEffect, useState } from "react";
import { api, scoped } from "../api";
import type { Workspace } from "../types";
import { ErrorNotice } from "./Feedback";

interface Event { action: string; created_at: string; target_id: string; actor_id: string }
export default function AuditPage({ workspace }: { workspace: Workspace }) {
  const [events, setEvents] = useState<Event[]>([]), [error, setError] = useState<unknown>(null), [loaded, setLoaded] = useState(false), [reload, setReload] = useState(0);
  const permitted = ["owner", "reviewer"].includes(workspace.role);
  useEffect(() => {
    if (!permitted) return;
    const controller = new AbortController(); setError(null); setLoaded(false);
    api<Event[]>(scoped(workspace.id, "/audit?limit=100"), { signal: controller.signal }).then(value => { if (!controller.signal.aborted) { setEvents(value); setLoaded(true); } }).catch(e => { if (!controller.signal.aborted) setError(e); });
    return () => controller.abort();
  }, [workspace.id, permitted, reload]);
  return <section className="panel audit-page"><span className="eyebrow">Workspace history</span><h1>Follow the trail.</h1><p>Recent recorded changes for this workspace. Review, delivery and personal execution have their own events.</p>{!permitted ? <p role="alert">Audit history requires owner or reviewer authority.</p> : <><ErrorNotice error={error} /><button onClick={() => setReload(value => value + 1)}>Refresh audit history</button>{!loaded ? !error && <p role="status">Loading recorded changes…</p> : !events.length ? <p>No audit events have been recorded.</p> : <ol className="timeline">{events.map((event, index) => <li key={event.created_at + ":" + index}><strong>{event.action.replaceAll(".", " · ").replaceAll("_", " ")}</strong><time dateTime={event.created_at}>{new Date(event.created_at).toLocaleString()}</time><details><summary>Record context</summary><p>Target: <code>{event.target_id}</code></p><p>Actor: <code>{event.actor_id}</code></p></details></li>)}</ol>}{events.length === 100 && <p className="muted">Showing the 100 most recent recorded changes.</p>}</>}</section>;
}
