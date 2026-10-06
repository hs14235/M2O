import { useEffect, useRef, useState } from "react";
import { api, scoped } from "../api";
import type { GoogleMeetPreview, GoogleMeetStatus, Workspace } from "../types";
import { ErrorNotice } from "./Feedback";

export interface ImportedMeeting { meeting_id: string; job_id: string | null; reused: boolean; import_id: string }
export default function GoogleMeetImport({ workspace, meetingId, title, visibility, disabled, beforeSave, onImported }: { workspace: Workspace; meetingId: string; title: string; visibility: "restricted" | "workspace"; disabled: boolean; beforeSave: () => boolean; onImported: (value: ImportedMeeting) => Promise<void> }) {
  const [open, setOpen] = useState(false), [status, setStatus] = useState<GoogleMeetStatus | null>(null), [preview, setPreview] = useState<GoogleMeetPreview | null>(null), [name, setName] = useState(title || "Latest Google Meet transcript"), [busy, setBusy] = useState(false), [error, setError] = useState<unknown>(null), [phase, setPhase] = useState<"read" | "save" | null>(null);
  const root = useRef<HTMLDivElement>(null), trigger = useRef<HTMLButtonElement>(null), pending = useRef<AbortController | null>(null), epoch = useRef(0);
  const key = JSON.stringify([workspace.id, meetingId, visibility]), current = useRef(key); current.current = key;
  const fresh = preview && Date.parse(preview.expires_at) > Date.now() ? preview : null;
  useEffect(() => { setPreview(null); setStatus(null); setName(title || "Latest Google Meet transcript"); epoch.current += 1; pending.current?.abort(); setBusy(false); }, [key]);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController(); setError(null);
    api<GoogleMeetStatus>(scoped(workspace.id, "/integrations/google-meet"), { signal: controller.signal }).then(value => { if (!controller.signal.aborted) setStatus(value); }).catch(e => { if (!controller.signal.aborted) setError(e); });
    root.current?.querySelector<HTMLElement>("h2")?.focus();
    return () => controller.abort();
  }, [open, key]);
  useEffect(() => () => pending.current?.abort(), []);
  useEffect(() => { if (!preview) return; const timer = setTimeout(() => setPreview(null), Math.max(0, Date.parse(preview.expires_at) - Date.now())); return () => clearTimeout(timer); }, [preview]);
  function close() { if (phase === "save" && busy) return; pending.current?.abort(); epoch.current += 1; setBusy(false); setPhase(null); setOpen(false); setPreview(null); trigger.current?.focus(); }
  async function run(kind: "read" | "save", action: (signal: AbortSignal, generation: number) => Promise<void>) {
    pending.current?.abort(); const request = new AbortController(); pending.current = request; const generation = ++epoch.current;
    setBusy(true); setPhase(kind); setError(null);
    try { await action(request.signal, generation); } catch (e) { if (!request.signal.aborted && epoch.current === generation) setError(e); } finally { if (!request.signal.aborted && epoch.current === generation) { setBusy(false); setPhase(null); } }
  }
  async function read() {
    setPreview(null); const snapshot = key;
    await run("read", async (signal, generation) => { const value = await api<GoogleMeetPreview>(scoped(workspace.id, "/imports/google-meet/preview"), { signal, method: "POST", body: "{}" }); if (!signal.aborted && epoch.current === generation && current.current === snapshot) setPreview(value); });
  }
  async function save(event: React.FormEvent) {
    event.preventDefault(); if (!fresh || !beforeSave()) return; const snapshot = key;
    await run("save", async (signal, generation) => {
      const value = await api<ImportedMeeting>(scoped(workspace.id, "/imports/google-meet/" + fresh.preview_id + "/save"), { signal, method: "POST", body: JSON.stringify({ payload_hash: fresh.payload_hash, title: name, meeting_id: meetingId, visibility }) });
      if (!signal.aborted && epoch.current === generation && current.current === snapshot) { setPreview(null); await onImported(value); }
    });
  }
  return <div className="google-import"><button ref={trigger} type="button" className="import-trigger" disabled={disabled || workspace.role === "viewer"} aria-expanded={open} aria-controls="google-import-panel" onClick={() => { setOpen(true); setName(title || "Latest Google Meet transcript"); }}>Import latest Google Meet transcript</button>{open && <section id="google-import-panel" ref={root} className="panel google-import-panel" aria-label="Google Meet transcript import"><div className="section-heading"><div><span className="eyebrow">Existing transcript · read-only provider access</span><h2 tabIndex={-1}>Bring in your latest accessible meeting.</h2></div><button type="button" disabled={busy && phase === "save"} onClick={close}>Close import</button></div><ErrorNotice error={error} />{!status ? !error && <p role="status">Checking import readiness…</p> : status.setup_required ? <div className="notice"><strong>Google Meet setup is required.</strong><p>No Google Cloud OAuth app is configured for this installation. The operator must configure read-only Meet access, and your meetings must generate transcripts before import is available.</p></div> : !status.can_import ? <><p>Connection: {status.state.replaceAll("_", " ")}. Connect your own private account to read existing transcripts.</p><button type="button" disabled={busy || !status.configured} onClick={() => run("read", async signal => { const value = await api<{ url: string }>(scoped(workspace.id, "/integrations/google-meet/connect"), { signal, method: "POST" }); if (!signal.aborted) window.location.assign(value.url); })}>{status.state === "reauthorization_required" ? "Reconnect Google Meet" : "Connect Google Meet"}</button></> : <><p>We check the latest accessible conference only. Missing or processing transcripts remain unavailable; an older meeting is not substituted.</p><button type="button" disabled={busy} onClick={read}>{fresh ? "Refresh latest transcript preview" : "Preview latest accessible Google Meet transcript"}</button></>}{busy && <p role="status">{phase === "save" ? "Saving the reviewed source to M2O…" : "Reading the latest accessible meeting. Large or incomplete results are rejected rather than truncated…"}</p>}{fresh && <div className="google-source-preview"><p>Conference ended {new Date(fresh.source.end_time).toLocaleString()} · preview expires {new Date(fresh.expires_at).toLocaleTimeString()}</p><details><summary>Source and participant labels</summary><p><code>{fresh.source.conference_record}</code> · Meet API entries</p><p>Participant labels are unconfirmed: {fresh.participants.map(person => person.name).join(", ") || "No participant labels available"}.</p><ul>{fresh.source.transcript_names.map(value => <li key={value}><code>{value}</code></li>)}</ul></details><pre className="payload-text">{fresh.transcript}</pre><form onSubmit={save}><fieldset disabled={busy}><legend className="sr-only">Save exact imported transcript</legend><label>Imported meeting title<input required maxLength={200} value={name} onChange={event => setName(event.target.value)} /></label><p>Access for a new import: {visibility === "restricted" ? "Creator, owners and reviewers" : "Workspace members"}. Participant confirmation and outcome review follow after indexing. An unchanged source reopens its existing meeting and preserves that meeting’s access and reviews.</p><button className="primary" disabled={!name.trim() || disabled}>Save this transcript and continue</button></fieldset></form></div>}<details><summary>What is imported?</summary><p>Existing structured Meet transcript entries, which can differ from an edited Google Docs transcript. M2O does not record a meeting, create transcription or manage Google Calendar.</p></details></section>}</div>;
}
