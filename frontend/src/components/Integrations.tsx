import { useEffect, useState } from "react";
import { api, scoped } from "../api";
import type { Integration, User, Workspace } from "../types";
import { ErrorNotice } from "./Feedback";
import JiraConnection from "./JiraConnection";
import GitHubConnection from "./GitHubConnection";
import SlackConnection from "./SlackConnection";
import SlackActions from "./SlackActions";
import GoogleMeetConnection from "./GoogleMeetConnection";

export const integrationStatus: Record<Integration["status"], string> = { ready: "Ready", configured: "Configured", connected: "Connected", preview_only: "Preview available", unavailable: "Adapter not available", needs_configuration: "Setup required" };

export default function Integrations({ workspace, user, refreshUser }: { workspace: Workspace; user: User; refreshUser: () => void }) {
  const [connectionRevision, setConnectionRevision] = useState(0);
  const [catalog, setCatalog] = useState<Integration[]>([]), [error, setError] = useState<unknown>(null), [busy, setBusy] = useState(false), [loading, setLoading] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    api<Integration[]>(scoped(workspace.id, "/integrations"), { signal: controller.signal }).then(setCatalog).catch(e => { if (!controller.signal.aborted) setError(e); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [workspace.id, user.linkedin.connected, connectionRevision]);
  async function linkedin(disconnect = false) {
    setBusy(true); setError(null);
    try {
      if (disconnect) { await api("/integrations/linkedin", { method: "DELETE" }); refreshUser(); }
      else { const result = await api<{ url: string }>("/integrations/linkedin/connect", { method: "POST" }); window.location.assign(result.url); }
    } catch (e) { setError(e); } finally { setBusy(false); }
  }
  return <div className="connections"><span className="eyebrow">Workspace connections</span><h1>Choose tools for the work.</h1><p>Prepare and review outcomes first. A connected tool is only needed when you choose to deliver them there.</p><ErrorNotice error={error} />{loading && <p role="status">Checking available connections…</p>}
    <GoogleMeetConnection workspace={workspace} user={user} />
    <section aria-labelledby="delivery-connections"><h2 id="delivery-connections">Outcome destinations</h2><div className="connection-grid">{catalog.filter(item => item.purpose === "delivery").map(item => <article className="panel" key={item.id}><div className="section-heading"><h3>{item.name}</h3><span className="badge">{integrationStatus[item.status]}</span></div><p>{item.description}</p>{item.id === "github" && user.capabilities.demo_mode && <p className="muted">Demo mode allows previews. Publishing is blocked.</p>}</article>)}</div></section>
    <section className="panel"><span className="eyebrow">Participant context</span><h2>Your LinkedIn connection</h2><p>Connect your own account's basic profile. Confirm transcript names against your workspace directory; this connection does not search for other people or verify their identity.</p>{user.linkedin.connected ? <><p className="notice">Connected: {user.linkedin.profile?.name || "Your LinkedIn account"}</p><button disabled={busy} onClick={() => linkedin(true)}>Disconnect and delete stored profile</button></> : <><button disabled={busy || !user.capabilities.linkedin_configured} onClick={() => linkedin()}>Connect my LinkedIn account</button>{!user.capabilities.linkedin_configured && <p className="muted">An approved LinkedIn application must be configured by the application operator first.</p>}</>}</section>
    {user.is_visitor ? <section className="panel"><h2>Explore without connecting live accounts</h2><p>This isolated demo offers local reviewed handoffs and supported offline previews. Jira, Slack, GitHub and LinkedIn account connections belong to invited private use.</p></section> : <><JiraConnection key={workspace.id} workspace={workspace} onChanged={() => setConnectionRevision(value => value + 1)} />
    <GitHubConnection key={"github-" + workspace.id} workspace={workspace} user={user} onChanged={() => setConnectionRevision(value => value + 1)} />
    <SlackConnection key={"slack-" + workspace.id} workspace={workspace} onChanged={() => setConnectionRevision(value => value + 1)} />
    <SlackActions key={"slack-actions-" + workspace.id + "-" + connectionRevision} workspace={workspace} /></> }
  </div>;
}
