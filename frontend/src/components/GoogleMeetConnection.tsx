import { useEffect, useState } from "react";
import { api, scoped } from "../api";
import type { GoogleMeetStatus, User, Workspace } from "../types";
import { ErrorNotice } from "./Feedback";

export default function GoogleMeetConnection({ workspace, user }: { workspace: Workspace; user: User }) {
  const [status, setStatus] = useState<GoogleMeetStatus | null>(null), [error, setError] = useState<unknown>(null), [busy, setBusy] = useState(false), [refresh, setRefresh] = useState(0), [notice, setNotice] = useState("");
  const eligible = !user.is_visitor && workspace.role !== "viewer" && !user.capabilities.demo_mode;
  useEffect(() => {
    if (!eligible) return;
    const controller = new AbortController();
    api<GoogleMeetStatus>(scoped(workspace.id, "/integrations/google-meet"), { signal: controller.signal }).then(value => { if (!controller.signal.aborted) setStatus(value); }).catch(e => { if (!controller.signal.aborted) setError(e); });
    return () => controller.abort();
  }, [workspace.id, eligible, refresh]);
  async function connect() { setBusy(true); setError(null); try { const value = await api<{ url: string }>(scoped(workspace.id, "/integrations/google-meet/connect"), { method: "POST" }); window.location.assign(value.url); } catch (e) { setError(e); setBusy(false); } }
  async function disconnect() { setBusy(true); setError(null); try { await api(scoped(workspace.id, "/integrations/google-meet"), { method: "DELETE" }); setNotice("Your local Google Meet connection was removed. Google's account consent remains under your control."); setStatus(null); setRefresh(value => value + 1); } catch (e) { setError(e); } finally { setBusy(false); } }
  return <section className="panel"><span className="eyebrow">Meeting source</span><h2>Your Google Meet connection</h2><p>Import the latest accessible meeting's existing transcript entries, then review the text before saving. Google labels still need participant confirmation in M2O.</p><ErrorNotice error={error} />{notice && <p role="status">{notice}</p>}{!eligible ? <p>Google Meet import requires an invited private contributor account. Synthetic demos use their prepared examples.</p> : !status ? !error && <p role="status">Checking Google Meet readiness…</p> : status.setup_required ? <div className="notice"><strong>Google Meet setup is required.</strong><p>The operator needs a Google Cloud OAuth app with read-only Meet access. Meetings must already generate transcripts; a connection cannot create a missing transcript.</p><details><summary>What is needed?</summary><p>Enable Google Meet REST API, configure the actual M2O consent screen, grant meetings.space.readonly, and register the callback for this installation. Client credentials belong in private backend configuration.</p></details></div> : <><p>Connection: {status.state.replaceAll("_", " ")}</p>{status.can_import ? <><p className="notice">Ready to preview an existing transcript from a meeting's Transcript step.</p><button disabled={busy} onClick={disconnect}>Disconnect my Google Meet account</button></> : <button disabled={busy || !status.configured} onClick={connect}>{status.state === "reauthorization_required" ? "Reconnect my Google Meet account" : "Connect my Google Meet account"}</button>}</>}<details><summary>Import boundaries</summary><p>Only the latest accessible conference is checked. An active meeting, absent transcript, or processing artifact has its own empty state; M2O does not silently import an older meeting. API entries can differ from an edited Google Docs transcript.</p></details></section>;
}
