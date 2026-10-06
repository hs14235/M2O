import { useEffect, useRef, useState } from "react";
import { api, scoped } from "../api";
import type { Workspace } from "../types";
import { ErrorNotice } from "./Feedback";

export interface SlackStatus {
  configured: boolean; can_manage: boolean; state: string; version: number | null;
  account: { team_id: string; team_name: string } | null; destination: { channel_id: string; channel_name: string } | null;
  can_create: boolean; can_update: boolean; can_reconcile: boolean; can_link: boolean; can_capture_meeting: boolean; can_change_my_plan: boolean;
  delivery_reasons: string[]; interaction_reasons: string[];
}
const reasons: Record<string, string> = { needs_configuration: "The operator must configure the Slack app and protected credential storage.", demo_mode: "Demo mode allows local work and blocks Slack writes.", owner_required: "This connection is managed by a workspace owner.", not_connected: "Connect the Slack account before choosing a channel.", reauthorization_required: "Reconnect Slack to renew access.", missing_scopes: "Reconnect with the app's required channel and message permissions.", unverified_destination: "Verify a channel containing the M2O app." };

export default function SlackConnection({ workspace, onChanged }: { workspace: Workspace; onChanged: () => void }) {
  const [status, setStatus] = useState<SlackStatus | null>(null), [channel, setChannel] = useState(""), [busy, setBusy] = useState(false), [error, setError] = useState<unknown>(null), [notice, setNotice] = useState("");
  const pending = useRef<AbortController | null>(null), path = scoped(workspace.id, "/integrations/slack");
  useEffect(() => {
    const controller = new AbortController();
    api<SlackStatus>(path, { signal: controller.signal }).then(value => { if (!controller.signal.aborted) { setStatus(value); setChannel(value.destination?.channel_id || ""); } }).catch(e => { if (!controller.signal.aborted) setError(e); });
    return () => { controller.abort(); pending.current?.abort(); };
  }, [path]);
  async function run(operation: (signal: AbortSignal) => Promise<void>) {
    pending.current?.abort(); const controller = new AbortController(); pending.current = controller; setBusy(true); setError(null); setNotice("");
    try { await operation(controller.signal); } catch (e) { if (!controller.signal.aborted) setError(e); } finally { if (!controller.signal.aborted) setBusy(false); }
  }
  return <section className="panel" aria-labelledby="slack-account-heading"><span className="eyebrow">Slack destination</span><h2 id="slack-account-heading">Give the conversation a team channel.</h2><p>Connect Slack and verify the channel containing M2O. Reviewed delivery can create a message or update a previous M2O message.</p><ErrorNotice error={error} />{!status ? <p role="status">Checking Slack access…</p> : <>{status.delivery_reasons.map(reason => <p className="muted" key={reason}>{reasons[reason] || "This Slack connection needs attention before delivery."}</p>)}{status.account && <p>Workspace: <strong>{status.account.team_name}</strong>{status.destination && <> · #{status.destination.channel_name}</>}</p>}<div className="actions"><button disabled={busy || !status.configured || !status.can_manage} onClick={() => run(async signal => { const value = await api<{ url: string }>(path + "/connect", { signal, method: "POST" }); if (!signal.aborted) window.location.assign(value.url); })}>{status.state === "disconnected" ? "Connect Slack" : "Reconnect Slack"}</button>{status.state !== "disconnected" && status.can_manage && <button disabled={busy} onClick={() => run(async signal => { await api(path, { signal, method: "DELETE" }); const value = await api<SlackStatus>(path, { signal }); if (!signal.aborted) { setStatus(value); setChannel(""); setNotice("Disconnected from this workspace. No message was removed."); onChanged(); } })}>Disconnect Slack from this workspace</button>}</div>{status.state === "connected" && status.can_manage && <form onSubmit={event => { event.preventDefault(); void run(async signal => { const value = await api<SlackStatus>(path + "/destination", { signal, method: "POST", body: JSON.stringify({ channel_id: channel.trim().toUpperCase(), expected_version: status.version }) }); if (!signal.aborted) { setStatus(value); setNotice("Channel verified and saved. No Slack message was sent."); onChanged(); } }); }}><label>Slack channel ID<input required pattern="C[A-Z0-9]{7,63}" maxLength={64} value={channel} disabled={busy} onChange={event => setChannel(event.target.value.toUpperCase())} placeholder="C…" /></label><p className="muted">Open the channel name in Slack, then copy its Channel ID from the channel details.</p><button disabled={busy || !channel || !status.version}>Verify Slack channel</button></form>}{!status.can_capture_meeting && !status.can_change_my_plan && <p className="muted">Interactive meeting capture and personal progress actions are not available on this connection.</p>}</>}{notice && <p role="status">{notice}</p>}</section>;
}
