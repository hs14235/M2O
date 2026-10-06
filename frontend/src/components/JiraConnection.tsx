import { useEffect, useRef, useState } from "react";
import { api, scoped } from "../api";
import type { Workspace } from "../types";
import { ErrorNotice } from "./Feedback";

interface Status {
  configured: boolean; can_manage: boolean;
  state: "disconnected" | "connected" | "reauthorization_required";
  version: number | null;
  destination: { resource_id: string; name: string; url: string; project_key: string; project_name: string } | null;
}
interface Site { id: string; name: string; url: string }

export default function JiraConnection({ workspace, onChanged }: { workspace: Workspace; onChanged?: () => void }) {
  const [status, setStatus] = useState<Status | null>(null), [sites, setSites] = useState<Site[]>([]);
  const [site, setSite] = useState(""), [project, setProject] = useState("");
  const [busy, setBusy] = useState(false), [error, setError] = useState<unknown>(null), [notice, setNotice] = useState("");
  const request = useRef<AbortController | null>(null);
  const path = scoped(workspace.id, "/integrations/jira");
  useEffect(() => {
    const controller = new AbortController();
    api<Status>(path, { signal: controller.signal }).then(value => {
      if (!controller.signal.aborted) { setStatus(value); setProject(value.destination?.project_key || ""); }
    }).catch(e => { if (!controller.signal.aborted) setError(e); });
    return () => { controller.abort(); request.current?.abort(); };
  }, [path]);
  async function run(operation: (signal: AbortSignal) => Promise<void>) {
    const controller = new AbortController(); request.current = controller;
    setBusy(true); setError(null); setNotice("");
    try { await operation(controller.signal); }
    catch (e) {
      if (!controller.signal.aborted) {
        setError(e);
        try {
          const result = await api<Status>(path, { signal: controller.signal });
          if (!controller.signal.aborted) { setStatus(result); onChanged?.(); }
        } catch { /* Keep the original error if the status request also fails. */ }
      }
    }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  return <section className="panel" aria-labelledby="jira-account-heading">
    <span className="eyebrow">Jira destination</span><h2 id="jira-account-heading">Give your outcomes a place to land.</h2>
    <p>Connect your account, choose an authorized site, then verify the space key. This checks access without creating an issue.</p>
    <ErrorNotice error={error} />
    {!status ? <p role="status">Checking your Jira connection…</p> : <>
      {!status.configured && <p className="notice">The application operator must configure Jira credentials and protected credential storage.</p>}
      {status.state === "reauthorization_required" && <p className="notice">Reconnect Jira to renew your authorization.</p>}
      {status.state === "connected" && <p className="notice">Account connected.{status.destination ? ` Verified destination: ${status.destination.name} / ${status.destination.project_key} (${status.destination.project_name}).` : " Choose a destination below."}</p>}
      {!status.can_manage && <p className="muted">Connections are managed by workspace owners outside demo mode.</p>}
      <div className="button-row">
        <button disabled={busy || !status.configured || !status.can_manage} onClick={() => run(async signal => {
          const result = await api<{ url: string }>(path + "/connect", { method: "POST", signal });
          if (!signal.aborted) window.location.assign(result.url);
        })}>{status.state === "disconnected" ? "Connect Jira" : "Reconnect Jira"}</button>
        {status.state !== "disconnected" && <button disabled={busy || workspace.role !== "owner"} onClick={() => run(async signal => {
          await api(path, { method: "DELETE", signal });
          const result = await api<Status>(path, { signal });
          if (!signal.aborted) { setStatus(result); setSites([]); setSite(""); setProject(""); onChanged?.(); setNotice("Disconnected from this workspace. Other workspaces keep their own access. Revoke the Atlassian grant in your Atlassian connected-app settings if needed."); }
        })}>Disconnect from this workspace</button>}
      </div>
      {status.state === "connected" && status.can_manage && <>
        <button disabled={busy} onClick={() => run(async signal => {
          const result = await api<Site[]>(path + "/sites", { signal });
          if (!signal.aborted) { setSites(result); setSite(result[0]?.id || ""); setNotice(result.length ? "Select a site and enter its space key." : "No Jira sites granted the required permissions. Check access and reconnect."); }
        })}>Find authorized Jira sites</button>
        {sites.length > 0 && <form onSubmit={event => {
          event.preventDefault(); void run(async signal => {
            const result = await api<Status>(path + "/destination", { method: "POST", signal, body: JSON.stringify({ resource_id: site, project_key: project.trim().toUpperCase(), expected_version: status.version }) });
            if (!signal.aborted) { setStatus(result); onChanged?.(); setNotice("Destination verified and saved. No issue was created."); }
          });
        }}>
          <label htmlFor="jira-site">Authorized Jira site</label><select id="jira-site" value={site} disabled={busy} onChange={event => setSite(event.target.value)}>{sites.map(value => <option key={value.id} value={value.id}>{value.name} — {value.url}</option>)}</select>
          <label htmlFor="jira-project">Space key</label><input id="jira-project" value={project} disabled={busy} required maxLength={40} pattern="[A-Za-z][A-Za-z0-9_]{1,39}" onChange={event => setProject(event.target.value)} autoComplete="off" />
          <button disabled={busy || !site || !project.trim()} type="submit">Verify and save destination</button>
        </form>}
      </>}
    </>}
    {(busy || notice) && <p role="status">{busy ? "Checking Jira…" : notice}</p>}
  </section>;
}
