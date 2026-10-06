import { useEffect, useRef, useState } from "react";
import { api, scoped } from "../api";
import type { HandoffStage } from "../navigation";
import type { Meeting, Workspace } from "../types";
import type { SlackStatus } from "./SlackConnection";
import { ErrorNotice } from "./Feedback";
import { PayloadInspection } from "./ExactPayload";

interface SlackPreview {
  id: string; action: "create" | "update"; expires_at: string; payload_hash: string;
  destination: { id: string; version: number; team_name: string; channel_id: string; channel_name: string };
  snapshots: { item_id: string; version: number; revision_id: string }[];
  target: { operation_id: string; message_ts: string } | null;
  payload: { text: string; blocks: { type: string; text?: { text: string }; elements?: { text?: string }[] }[] };
}
interface SlackReceipt { operation_id: string; action: string; state: string; created_at: string; can_reconcile: boolean; can_retry_rejected: boolean; proposal: SlackPreview; result: { status: string; message_ts?: string; url?: string; error?: string } | null }

export function SlackPublisher({ workspace, meeting, selected, stage, onStage, onJob }: { workspace: Workspace; meeting: Meeting; selected: string[]; stage: HandoffStage; onStage: (stage: HandoffStage) => void; onJob: (id: string) => void }) {
  const [status, setStatus] = useState<SlackStatus | null>(null), [action, setAction] = useState<"create" | "update">("create"), [target, setTarget] = useState(""), [evidence, setEvidence] = useState(false), [disclosure, setDisclosure] = useState(false), [retry, setRetry] = useState(false);
  const [preview, setPreview] = useState<{ key: string; value: SlackPreview } | null>(null), [receipts, setReceipts] = useState<SlackReceipt[]>([]), [loaded, setLoaded] = useState(false), [refreshKey, setRefreshKey] = useState(0), [timestamps, setTimestamps] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false), [error, setError] = useState<unknown>(null), request = useRef<AbortController | null>(null);
  const key = JSON.stringify([workspace.id, meeting.id, meeting.current_revision, meeting.visibility, selected, meeting.tasks.map(item => [item.id, item.version, item.status]), status?.version, action, target, evidence, disclosure]);
  const currentKey = useRef(key); currentKey.current = key;
  const currentStage = useRef(stage), stageEpoch = useRef(0);
  const [receiptError, setReceiptError] = useState<unknown>(null);
  if (currentStage.current !== stage) { currentStage.current = stage; stageEpoch.current += 1; }
  const stored = preview?.key === key && Date.parse(preview.value.expires_at) > Date.now() ? preview.value : null;
  const pendingDelivery = receipts.some(receipt => ["queued", "sending"].includes(receipt.state));
  const eligible = selected.length > 0 && selected.length <= 10 && selected.every(id => meeting.tasks.some(item => item.id === id && item.status === "approved"));
  const targets = receipts.filter(receipt => receipt.state === "completed" && ["created", "updated", "existing"].includes(receipt.result?.status || "") && receipt.proposal.destination.version === status?.version && receipt.proposal.destination.channel_id === status?.destination?.channel_id);
  useEffect(() => {
    const controller = new AbortController();
    api<SlackStatus>(scoped(workspace.id, "/integrations/slack"), { signal: controller.signal }).then(value => { if (!controller.signal.aborted) setStatus(value); }).catch(e => { if (!controller.signal.aborted) setError(e); });
    return () => { controller.abort(); request.current?.abort(); };
  }, [workspace.id]);
  useEffect(() => {
    const controller = new AbortController();
    async function refresh() {
      try { const value = await api<SlackReceipt[]>(scoped(workspace.id, "/meetings/" + meeting.id + "/slack/deliveries"), { signal: controller.signal }); if (!controller.signal.aborted) { setReceipts(value); setLoaded(true); setReceiptError(null); } }
      catch (e) { if (!controller.signal.aborted) setReceiptError(e); }
    }
    void refresh(); const timer = pendingDelivery ? setInterval(() => void refresh(), 3000) : undefined;
    return () => { controller.abort(); clearInterval(timer); };
  }, [workspace.id, meeting.id, refreshKey, pendingDelivery, stage]);
  useEffect(() => { if (!preview) return; const timer = setTimeout(() => setPreview(null), Math.max(0, Date.parse(preview.value.expires_at) - Date.now())); return () => clearTimeout(timer); }, [preview]);
  async function run(operation: (signal: AbortSignal) => Promise<void>) {
    request.current?.abort(); const controller = new AbortController(); request.current = controller; setBusy(true); setError(null);
    try { await operation(controller.signal); } catch (e) { if (!controller.signal.aborted) setError(e); } finally { if (!controller.signal.aborted) setBusy(false); }
  }
  async function prepare() {
    const requestedEpoch = stageEpoch.current;
    if (!status?.version || !eligible) return;
    const requested = key; setPreview(null); setRetry(false);
    await run(async signal => {
      const value = await api<SlackPreview>(scoped(workspace.id, "/meetings/" + meeting.id + "/slack/preview"), { signal, method: "POST", body: JSON.stringify({ action, expected_revision: meeting.current_revision, versions: Object.fromEntries(selected.map(id => [id, meeting.tasks.find(item => item.id === id)!.version])), expected_destination_version: status.version, include_evidence: evidence, confirm_restricted_share: disclosure, target_operation_id: action === "update" ? target : null }) });
      if (!signal.aborted && currentKey.current === requested && stageEpoch.current === requestedEpoch) { setPreview({ key: requested, value }); onStage("preview"); }
    });
  }
  async function approve() {
    const requestedEpoch = stageEpoch.current;
    if (!stored) return;
    await run(async signal => {
      const value = await api<{ job_id: string }>(scoped(workspace.id, "/slack/proposals/" + stored.id + "/approve"), { signal, method: "POST", body: JSON.stringify({ payload_hash: stored.payload_hash, retry_rejected: retry }) });
      if (!signal.aborted) { setPreview(null); setRefreshKey(value => value + 1); onJob(value.job_id); if (stageEpoch.current === requestedEpoch) onStage("receipt"); }
    });
  }
  return <section hidden={stage === "choose"} className="panel publisher" aria-labelledby="slack-publish-title"><span className="eyebrow">Slack handoff</span><h2 id="slack-publish-title">{stage === "preview" ? "Review the exact message." : stage === "receipt" ? "Your Slack delivery history." : "Give your team a clear next step."}</h2><ErrorNotice error={error} />
    {stage === "configure" && <fieldset disabled={busy || !status?.can_create}><legend className="sr-only">Prepare Slack handoff</legend><p>{status?.account?.team_name || "Slack workspace"} · {status?.destination ? "#" + status.destination.channel_name : "No verified channel"}</p>{!status?.can_create && <p className="notice">Check Connections for Slack account permissions and a verified channel.</p>}<label>Slack action<select value={action} onChange={e => setAction(e.target.value as typeof action)}><option value="create">Create a message</option><option value="update" disabled={!status?.can_update}>Update a previous M2O message</option></select></label>{action === "update" && <label>Previous M2O delivery<select value={target} onChange={e => setTarget(e.target.value)}><option value="">Choose a delivered message</option>{targets.map(receipt => <option key={receipt.operation_id} value={receipt.operation_id}>#{receipt.proposal.destination.channel_name} · {new Date(receipt.created_at).toLocaleString()} · {receipt.result?.message_ts}</option>)}</select></label>}<label className="check"><input type="checkbox" checked={evidence} onChange={e => setEvidence(e.target.checked)} />Include transcript evidence in Slack</label>{meeting.visibility === "restricted" && <label className="check"><input type="checkbox" checked={disclosure} onChange={e => setDisclosure(e.target.checked)} />I approve sharing these restricted outcomes with this Slack channel</label>}<p className="muted">A message can share private context. Preparing the preview does not send it or complete your plan.</p><button className="primary" disabled={!eligible || (action === "update" && !target) || (meeting.visibility === "restricted" && !disclosure)} onClick={prepare}>Generate exact Slack preview</button></fieldset>}
    {stage === "preview" && (stored ? <div className="preview"><p role="status">{stored.action === "create" ? "Create" : "Update"} in {stored.destination.team_name} / #{stored.destination.channel_name} · expires {new Date(stored.expires_at).toLocaleTimeString()}</p>{stored.target && <p className="notice">Updating the previous M2O message {stored.target.message_ts}. M2O checks its current content before sending.</p>}<article className="exact-payload"><h3>Stored message content</h3>{stored.payload.blocks.map((block, i) => <pre className="payload-text" key={i}>{block.text?.text || block.elements?.map(element => element.text || "").join("\n") || block.type}</pre>)}<details><summary>Notification fallback text</summary><pre className="payload-text">{stored.payload.text}</pre></details><PayloadInspection payload={stored.payload} hash={stored.payload_hash} /></article>{receipts.some(receipt => receipt.can_retry_rejected) && <label className="check"><input type="checkbox" checked={retry} disabled={busy} onChange={e => setRetry(e.target.checked)} />Retry a confirmed rejected delivery of this exact payload</label>}<button className="primary" disabled={busy || !status?.can_create} onClick={approve}>Approve exact preview and {stored.action === "create" ? "send Slack message" : "update Slack message"}</button></div> : <p className="notice">There is no current preview in this browser session. Return to preparation after a refresh, expiry or source change.</p>)}
    {stage === "receipt" && <section aria-label="Slack delivery receipts">{Boolean(receiptError) && <><ErrorNotice error={receiptError} /><p>Delivery history could not be refreshed. A failed read does not mean a message was not sent.</p><button onClick={() => { setReceiptError(null); setRefreshKey(value => value + 1); }}>Refresh Slack receipts</button></>}{!loaded ? !receiptError && <p role="status">Loading recorded deliveries…</p> : !receipts.length ? !receiptError && <p>No recorded Slack delivery is available for this meeting.</p> : receipts.map(receipt => <article className="preview" key={receipt.operation_id}><h3>{receipt.action} · #{receipt.proposal.destination.channel_name}</h3><p role="status">{receipt.state}{receipt.result ? " · " + receipt.result.status : ""}</p>{receipt.result?.url && <a href={receipt.result.url} target="_blank" rel="noopener noreferrer">Open delivered Slack message</a>}{receipt.result?.message_ts && <p className="muted">Message timestamp: {receipt.result.message_ts}</p>}{receipt.result?.error && <p>{receipt.result.error}</p>}<details><summary>Inspect this delivery's stored content</summary><pre className="payload-text">{receipt.proposal.payload.text}</pre><PayloadInspection payload={receipt.proposal.payload} hash={receipt.proposal.payload_hash} /></details>{receipt.state === "uncertain" && <p className="notice">The result is uncertain. Check the channel before sending again; reconciliation verifies an existing message without resending.</p>}{receipt.can_reconcile && <><label>Slack message timestamp to reconcile<input pattern="[0-9]{10,20}\.[0-9]{6}" maxLength={27} value={timestamps[receipt.operation_id] || ""} placeholder="1234567890.123456" onChange={e => setTimestamps(previous => ({ ...previous, [receipt.operation_id]: e.target.value }))} /></label><button disabled={busy || !/^[0-9]{10,20}\.[0-9]{6}$/.test(timestamps[receipt.operation_id] || "")} onClick={() => run(async signal => { await api(scoped(workspace.id, "/slack/operations/" + receipt.operation_id + "/reconcile"), { signal, method: "POST", body: JSON.stringify({ message_ts: timestamps[receipt.operation_id] }) }); if (!signal.aborted) setRefreshKey(value => value + 1); })}>Verify existing Slack delivery</button></>}</article>)}</section>}
  </section>;
}
