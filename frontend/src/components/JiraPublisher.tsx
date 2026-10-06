import { useEffect, useRef, useState } from "react";
import { api, scoped } from "../api";
import type { Outcome, Workspace } from "../types";
import { ErrorNotice } from "./Feedback";
import type { HandoffStage } from "../navigation";
import { JiraPayload } from "./ExactPayload";

interface JiraField { id: string; name: string; required: boolean; has_default: boolean; control: string; options: { id: string; name: string }[] }
interface Destination { project_key: string; project_name: string; resource_url: string; version: number }
interface Metadata { destination: Destination; issue_types: { id: string; name: string }[]; fields: JiraField[]; issue: { key: string; fields: { issuetype: { id: string }; summary: string } } | null }
interface Preview { id: string; action: "create" | "update"; destination: Destination; payload_hash: string; payload: { fields: Record<string, unknown> & { summary: string } }; expires_at: string }
interface Receipt { operation_id: string; state: string; action: string; item_version: number; project_key: string; result: { status: string; issue_key?: string; url?: string; error?: string } | null }

export function JiraPublisher({ workspace, meetingId, selected, items, onJob, stage, onStage }: { workspace: Workspace; meetingId: string; selected: string[]; items: Outcome[]; onJob: (id: string) => void; stage?: HandoffStage; onStage?: (stage: HandoffStage) => void }) {
  const [action, setAction] = useState<"create" | "update">("create"), [issueKey, setIssueKey] = useState(""), [type, setType] = useState(""), [itemId, setItemId] = useState(""), [evidence, setEvidence] = useState(false);
  const [metadata, setMetadata] = useState<{ key: string; value: Metadata } | null>(null), [types, setTypes] = useState<Metadata["issue_types"]>([]), [values, setValues] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<{ key: string; value: Preview } | null>(null), [receipts, setReceipts] = useState<Receipt[]>([]), [reconcileKeys, setReconcileKeys] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false), [error, setError] = useState<unknown>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [retryRejected, setRetryRejected] = useState(false);
  const pending = useRef<AbortController | null>(null), sequence = useRef(0);
  const approved = items.filter(item => selected.includes(item.id) && item.status === "approved"), chosen = approved.find(item => item.id === itemId) || approved[0];
  const metadataKey = JSON.stringify([workspace.id, action, type, issueKey]);
  const key = JSON.stringify([metadataKey, chosen?.id, chosen?.version, items.map(item => [item.id, item.version, item.status]), evidence, values]);
  const currentKey = useRef(key); currentKey.current = key;
  const currentStage = useRef(stage), stageEpoch = useRef(0);
  const [receiptsLoaded, setReceiptsLoaded] = useState(false), [receiptError, setReceiptError] = useState<unknown>(null);
  if (currentStage.current !== stage) { currentStage.current = stage; stageEpoch.current += 1; }
  const currentMetadataKey = useRef(metadataKey); currentMetadataKey.current = metadataKey;
  const usable = metadata?.key === metadataKey && metadata.value.fields.length > 0 ? metadata.value : null;
  const stored = preview?.key === key && new Date(preview.value.expires_at).getTime() > Date.now() ? preview.value : null;
  const blocked = usable?.fields.filter(field => field.required && !field.has_default && field.control === "unsupported" && !["project", "issuetype"].includes(field.id)) || [];
  const hasPendingDelivery = receipts.some(receipt => ["queued", "sending"].includes(receipt.state));

  useEffect(() => {
    let active = true; const controller = new AbortController();
    async function refresh() {
      try { const result = await api<Receipt[]>(scoped(workspace.id, "/meetings/" + meetingId + "/jira/deliveries"), { signal: controller.signal }); if (active) { setReceipts(result); setReceiptsLoaded(true); setReceiptError(null); } }
      catch (e) { if (active && !controller.signal.aborted) setReceiptError(e); }
    }
    void refresh(); const timer = hasPendingDelivery ? setInterval(() => void refresh(), 3000) : undefined;
    return () => { active = false; controller.abort(); clearInterval(timer); };
  }, [workspace.id, meetingId, refreshKey, hasPendingDelivery, stage]);
  useEffect(() => () => { pending.current?.abort(); sequence.current += 1; }, [workspace.id, meetingId]);
  useEffect(() => { if (!preview) return; const timer = setTimeout(() => setPreview(null), Math.max(0, new Date(preview.value.expires_at).getTime() - Date.now())); return () => clearTimeout(timer); }, [preview]);

  async function perform(work: (signal: AbortSignal) => Promise<void>) {
    pending.current?.abort(); const controller = new AbortController(); pending.current = controller; const request = ++sequence.current;
    setBusy(true); setError(null);
    try { await work(controller.signal); } catch (e) { if (!controller.signal.aborted) setError(e); }
    finally { if (request === sequence.current && !controller.signal.aborted) setBusy(false); }
  }
  async function discover() {
    const requested = metadataKey; setPreview(null); setMetadata(null); setValues({});
    await perform(async signal => {
      const query = action === "update" ? "?issue_key=" + encodeURIComponent(issueKey) : type ? "?issue_type_id=" + type : "";
      const result = await api<Metadata>(scoped(workspace.id, "/integrations/jira/metadata" + query), { signal });
      if (signal.aborted || currentMetadataKey.current !== requested) return;
      if (action === "create") setTypes(result.issue_types);
      setMetadata({ key: requested, value: result });
    });
  }
  async function prepare() {
    const requestedEpoch = stageEpoch.current;
    if (!chosen || !usable) return;
    const requested = key; setPreview(null); setRetryRejected(false);
    await perform(async signal => {
      const fields: Record<string, string | number | string[]> = {};
      for (const field of usable.fields) {
        const value = values[field.id]; if (!value) continue;
        fields[field.id] = ["number", "integer"].includes(field.control) ? Number(value) : field.control === "strings" ? value.split(",").map(v => v.trim()).filter(Boolean) : value;
      }
      const result = await api<Preview>(scoped(workspace.id, "/meetings/" + meetingId + "/jira/preview"), { signal, method: "POST", body: JSON.stringify({ item_id: chosen.id, expected_item_version: chosen.version, expected_destination_version: usable.destination.version, issue_type_id: action === "update" ? usable.issue!.fields.issuetype.id : type, action, issue_key: action === "update" ? issueKey : null, include_evidence: evidence, fields }) });
      if (!signal.aborted && currentKey.current === requested && stageEpoch.current === requestedEpoch) { setPreview({ key: requested, value: result }); onStage?.("preview"); }
    });
  }
  async function publish() {
    const requestedEpoch = stageEpoch.current;
    if (!stored) return;
    await perform(async signal => {
      const result = await api<{ job_id: string }>(scoped(workspace.id, "/jira/proposals/" + stored.id + "/approve"), { signal, method: "POST", body: JSON.stringify({ payload_hash: stored.payload_hash, retry_rejected: retryRejected }) });
      if (!signal.aborted) { onJob(result.job_id); setPreview(null); setRefreshKey(previous => previous + 1); if (stageEpoch.current === requestedEpoch) onStage?.("receipt"); }
    });
  }
  async function reconcile(receipt: Receipt) {
    const target = reconcileKeys[receipt.operation_id]; if (!target) return;
    await perform(async signal => { await api(scoped(workspace.id, "/jira/operations/" + receipt.operation_id + "/reconcile?issue_key=" + encodeURIComponent(target)), { signal, method: "POST" }); if (!signal.aborted) setRefreshKey(previous => previous + 1); });
  }
  return <section className="panel publisher" aria-labelledby="jira-publish-title">
    <span className="eyebrow">Jira handoff</span><h2 id="jira-publish-title">{stage === "preview" ? "Review the exact issue." : stage === "receipt" ? "Your Jira delivery history." : "Make one outcome actionable."}</h2>
    <p>Your M2O daily-plan progress remains separate from review and the issue's external status.</p>
    <fieldset hidden={Boolean(stage && stage !== "configure")} disabled={busy}><legend>Choose the handoff</legend>
      <label>Reviewed outcome<select value={chosen?.id || ""} onChange={e => setItemId(e.target.value)}><option value="" disabled>Select an approved outcome</option>{approved.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label>
      <label>Jira action<select value={action} onChange={e => { setAction(e.target.value as typeof action); setMetadata(null); setValues({}); }}><option value="create">Create an issue</option><option value="update">Update an existing issue</option></select></label>
      {action === "update" ? <label>Existing issue key<input value={issueKey} maxLength={61} placeholder="M2O-12" onChange={e => setIssueKey(e.target.value.toUpperCase())} /></label> : types.length > 0 && <label>Issue type<select value={type} onChange={e => { setType(e.target.value); setValues({}); }}><option value="">Choose an issue type</option>{types.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}</select></label>}
      <button disabled={action === "update" && !issueKey} onClick={discover}>{action === "update" ? "Load existing issue and editable fields" : type ? "Load issue fields" : "Find available issue types"}</button>
      {usable && <><p>Destination: <strong>{usable.destination.project_name} ({usable.destination.project_key})</strong>{usable.issue && <> · Updating {usable.issue.key}: {usable.issue.fields.summary}</>}</p>
        {usable.fields.filter(field => !["summary", "description", "project", "issuetype"].includes(field.id) && field.control !== "unsupported").map(field => <label key={field.id}>{field.name}{field.required && !field.has_default ? " (required)" : " (optional)"}{field.control === "select" ? <select value={values[field.id] || ""} onChange={e => setValues(previous => ({ ...previous, [field.id]: e.target.value }))}><option value="">Use Jira default</option>{field.options.map(option => <option key={option.id} value={option.id}>{option.name}</option>)}</select> : field.control === "textarea" ? <textarea value={values[field.id] || ""} maxLength={16000} onChange={e => setValues(previous => ({ ...previous, [field.id]: e.target.value }))} /> : <input type={field.control === "date" ? "date" : ["number", "integer"].includes(field.control) ? "number" : "text"} step={field.control === "integer" ? "1" : "any"} maxLength={16000} value={values[field.id] || ""} onChange={e => setValues(previous => ({ ...previous, [field.id]: e.target.value }))} />}{field.control === "strings" && <small>Comma-separated values, without spaces inside a value.</small>}</label>)}
        {blocked.length > 0 && <p className="notice" role="status">This screen requires fields M2O cannot safely map yet: {blocked.map(field => field.name).join(", ")}. Choose another issue type or configure a compatible Jira screen.</p>}
        <label className="check"><input type="checkbox" checked={evidence} onChange={e => setEvidence(e.target.checked)} />Include transcript evidence in Jira</label><p className="muted">Title and description come from the approved outcome. Evidence may contain private meeting details. Omitted optional fields use Jira defaults on creation and remain unchanged on update.</p>
        <button disabled={!chosen || blocked.length > 0} onClick={prepare}>Generate exact Jira preview</button></>}
    </fieldset>
    <ErrorNotice error={error} />
    {(!stage || stage === "preview") && stored && <div className="preview"><p role="status">Review {stored.action === "create" ? "creation" : "update"} in {stored.destination.project_key} · expires {new Date(stored.expires_at).toLocaleTimeString()}</p>{stored.action === "update" && <p className="notice">This replaces the issue title and description. M2O checks for changes immediately before sending; Jira can still change between that check and the update.</p>}<JiraPayload payload={stored.payload} hash={stored.payload_hash} /><label className="check"><input type="checkbox" disabled={busy} checked={retryRejected} onChange={e => setRetryRejected(e.target.checked)} />Retry a previously rejected delivery of this exact payload</label><p className="muted">Retries require confirmed rejection or failure before sending. An uncertain write must be reconciled.</p><button className="primary" disabled={busy} onClick={publish}>Approve exact preview and {stored.action === "create" ? "create Jira issue" : "update Jira issue"}</button></div>}
    {stage === "preview" && !stored && <p className="notice">There is no current preview in this browser session. Return to preparation after a refresh, expiry or source change.</p>}
    {(!stage || stage === "receipt") && <section aria-label="Jira delivery receipts"><h3>Your Jira deliveries</h3>{Boolean(receiptError) && <><ErrorNotice error={receiptError} /><p>Delivery history could not be refreshed. A failed read does not mean an issue was not sent.</p><button onClick={() => { setReceiptError(null); setRefreshKey(value => value + 1); }}>Refresh Jira receipts</button></>}{!receiptsLoaded && !receiptError && <p role="status">Loading recorded deliveries…</p>}{receiptsLoaded && !receiptError && receipts.length === 0 && <p>No recorded Jira deliveries are available for this meeting.</p>}{receipts.map(receipt => <article className="preview" key={receipt.operation_id}><strong>{receipt.action} · {receipt.project_key} · outcome version {receipt.item_version}</strong><p role="status">{receipt.state}</p>{receipt.result?.url && <a href={receipt.result.url} target="_blank" rel="noopener noreferrer">Open {receipt.result.issue_key} in Jira</a>}{receipt.result?.error && <p>{receipt.result.error}</p>}{receipt.state === "uncertain" && <><p>Check Jira for the issue first. M2O will verify its delivery marker without sending again.</p><label>Issue key to reconcile<input value={reconcileKeys[receipt.operation_id] || ""} onChange={e => setReconcileKeys(previous => ({ ...previous, [receipt.operation_id]: e.target.value.toUpperCase() }))} /></label><button disabled={busy || !reconcileKeys[receipt.operation_id]} onClick={() => reconcile(receipt)}>Verify delivery receipt</button></>}</article>)}</section>}
  </section>;
}
