import { useEffect, useRef, useState } from "react";
import { api, scoped } from "../api";
import type { GitHubReceipt, GitHubStatus, Outcome, Proposal, User, Workspace } from "../types";
import type { HandoffStage } from "../navigation";
import { ErrorNotice } from "./Feedback";
import { PayloadInspection } from "./ExactPayload";

export function Publisher({ workspace, user, meetingId, selected, items, onJob, publicationEnabled = false, stage, onStage, visibility = "workspace" }: { workspace: Workspace; user: User; meetingId: string; selected: string[]; items: Outcome[]; onJob: (id: string) => void; publicationEnabled?: boolean; stage?: HandoffStage; onStage?: (stage: HandoffStage) => void; visibility?: "workspace" | "restricted" }) {
  const [repo, setRepo] = useState(user.capabilities.allowed_repos[0] || "demo/example");
  const [evidence, setEvidence] = useState(false), [disclosure, setDisclosure] = useState(false), [proposal, setProposal] = useState<Proposal | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState<unknown>(null);
  const [status, setStatus] = useState<GitHubStatus | null>(null), [receipts, setReceipts] = useState<GitHubReceipt[]>([]), [receiptsLoaded, setReceiptsLoaded] = useState(false), [refreshKey, setRefreshKey] = useState(0);
  const snapshotKey = JSON.stringify([selected, items.map(item => [item.id, item.version, item.status]), repo, evidence, disclosure, visibility, meetingId, status?.destination]);
  const currentKey = useRef(snapshotKey), pending = useRef<AbortController | null>(null); currentKey.current = snapshotKey;
  const currentStage = useRef(stage), stageEpoch = useRef(0);
  if (currentStage.current !== stage) { currentStage.current = stage; stageEpoch.current += 1; }
  const [proposalKey, setProposalKey] = useState<string | null>(null);
  const [receiptError, setReceiptError] = useState<unknown>(null);
  const stored = proposal && proposalKey === snapshotKey && Date.parse(proposal.expires_at) > Date.now() ? proposal : null;
  const hasPending = receipts.some(receipt => ["queued", "sending"].includes(receipt.state));
  useEffect(() => {
    if (!stage) return;
    const controller = new AbortController();
    api<GitHubStatus>(scoped(workspace.id, "/integrations/github"), { signal: controller.signal }).then(value => { if (!controller.signal.aborted) { setStatus(value); if (value.destination) setRepo(value.destination.repo); } }).catch(e => { if (!controller.signal.aborted) setError(e); });
    return () => controller.abort();
  }, [workspace.id, Boolean(stage)]);
  useEffect(() => {
    if (!stage) return;
    const controller = new AbortController();
    async function refresh() {
      try { const value = await api<GitHubReceipt[]>(scoped(workspace.id, "/meetings/" + meetingId + "/deliveries/github"), { signal: controller.signal }); if (!controller.signal.aborted) { setReceipts(value); setReceiptsLoaded(true); setReceiptError(null); } }
      catch (e) { if (!controller.signal.aborted) setReceiptError(e); }
    }
    void refresh(); const timer = hasPending ? setInterval(() => void refresh(), 3000) : undefined;
    return () => { controller.abort(); clearInterval(timer); };
  }, [workspace.id, meetingId, stage, refreshKey, hasPending]);
  useEffect(() => { setProposal(null); }, [snapshotKey]);
  useEffect(() => () => pending.current?.abort(), []);
  useEffect(() => {
    if (!proposal) return;
    const timer = setTimeout(() => setProposal(null), Math.max(0, new Date(proposal.expires_at).getTime() - Date.now()));
    return () => clearTimeout(timer);
  }, [proposal]);
  const eligible = selected.length > 0 && selected.length <= 30 && selected.every(id => items.some(item => item.id === id && item.status === "approved"));
  async function preview() {
    pending.current?.abort(); const controller = new AbortController(); pending.current = controller; const requestedKey = snapshotKey, requestedEpoch = stageEpoch.current;
    setBusy(true); setError(null); setProposal(null);
    try {
      const result = await api<Proposal>(scoped(workspace.id, "/meetings/" + meetingId + "/preview"), { signal: controller.signal, method: "POST", body: JSON.stringify({ repo, task_ids: selected, include_evidence: evidence, ...(stage ? { expected_versions: Object.fromEntries(selected.map(id => [id, items.find(item => item.id === id)!.version])), expected_destination_version: status?.destination?.version, external_disclosure_confirmed: disclosure } : {}) }) });
      if (!controller.signal.aborted && currentKey.current === requestedKey && stageEpoch.current === requestedEpoch) { setProposal(result); setProposalKey(requestedKey); onStage?.("preview"); }
    } catch (e) { if (!controller.signal.aborted) setError(e); } finally { if (!controller.signal.aborted) setBusy(false); }
  }
  async function publish() {
    if (!stored) return;
    pending.current?.abort(); const controller = new AbortController(); pending.current = controller; const requestedEpoch = stageEpoch.current; setBusy(true); setError(null);
    try {
      const job = await api<{ job_id: string }>(scoped(workspace.id, "/proposals/" + stored.id + "/approve"), { signal: controller.signal, method: "POST", body: JSON.stringify({ payload_hash: stored.payload_hash }) });
      if (!controller.signal.aborted) { onJob(job.job_id); setProposal(null); setRefreshKey(value => value + 1); if (stageEpoch.current === requestedEpoch) onStage?.("receipt"); }
    } catch (e) { if (!controller.signal.aborted) setError(e); } finally { if (!controller.signal.aborted) setBusy(false); }
  }
  async function reconcile(receipt: GitHubReceipt) {
    setBusy(true); setError(null);
    const controller = new AbortController(); pending.current?.abort(); pending.current = controller;
    try { await api(scoped(workspace.id, "/operations/" + receipt.operation_id + "/reconcile"), { signal: controller.signal, method: "POST" }); if (!controller.signal.aborted) setRefreshKey(value => value + 1); }
    catch (e) { if (!controller.signal.aborted) setError(e); } finally { if (!controller.signal.aborted) setBusy(false); }
  }
  const allowed = user.capabilities.allowed_repos.some(value => value.toLowerCase() === repo.toLowerCase());
  const bound = !stage || Boolean(status?.can_publish && stored?.destination && status.destination?.id === stored.destination.id && status.destination.version === stored.destination.version && status.destination.repo.toLowerCase() === repo.toLowerCase());
  const canPublish = publicationEnabled && !user.capabilities.demo_mode && ["owner", "reviewer"].includes(workspace.role) && allowed && bound;
  return <section hidden={stage === "choose"} className="panel publisher" aria-labelledby="publish-title">
    <div className="section-heading"><div><span className="eyebrow">GitHub handoff</span><h2 id="publish-title">{stage === "receipt" ? "Your GitHub delivery history." : stage === "preview" ? "Review the exact issues." : "Prepare your GitHub issues."}</h2></div><span className="badge">{canPublish ? "Publication enabled" : "Preview only"}</span></div>
    <fieldset hidden={Boolean(stage && stage !== "configure")} disabled={busy}><legend className="sr-only">Prepare GitHub handoff</legend>
      <p>{selected.length} approved outcome{selected.length !== 1 ? "s" : ""} selected. The preview includes the exact payload and duplicate marker.</p>
      <label>GitHub repository<input value={repo} readOnly={Boolean(stage && status?.destination)} maxLength={180} onChange={e => setRepo(e.target.value)} placeholder="owner/repository" /></label>
      {stage && !status?.destination && <p className="notice">This is an offline preview destination. An owner must bind an allowed repository in Connections before publication.</p>}
      <label className="check"><input type="checkbox" checked={evidence} onChange={e => setEvidence(e.target.checked)} />Include transcript evidence in issue bodies</label>
      {visibility === "restricted" && <label className="check"><input type="checkbox" checked={disclosure} onChange={e => setDisclosure(e.target.checked)} />I approve sharing the selected outcome content with this GitHub destination</label>}
      <p className="muted">Preparing a preview does not send an issue. Outcome content and optional evidence may contain private meeting details.</p>
      <button className="primary" disabled={!eligible || busy || workspace.role === "viewer" || (visibility === "restricted" && !disclosure) || Boolean(stage && !status)} onClick={preview}>Generate exact preview</button>
    </fieldset>
    <ErrorNotice error={error} />
    {(!stage || stage === "preview") && stored && <div className="preview"><p role="status">Stored preview · expires {new Date(stored.expires_at).toLocaleTimeString()}</p>{stored.would_create.map((payload, index) => <article className="exact-payload" key={index}><h3>{payload.title}</h3><pre className="payload-text">{payload.body}</pre><p className="muted">Labels: {payload.labels.join(", ") || "None"} · Assignees: {payload.assignees?.join(", ") || "Unassigned"}</p><PayloadInspection payload={payload} hash={stored.payload_hash} /></article>)}
      <button className="primary" disabled={!canPublish || busy} onClick={publish}>Approve exact preview and publish to GitHub</button>
      {!canPublish && <p className="notice">{user.capabilities.demo_mode ? "Demo mode blocks external writes. This preview is fully reviewable locally." : "Publication needs current reviewer authority and a configured workspace repository binding. Check Connections."}</p>}
    </div>}
    {stage === "preview" && !stored && <p className="notice">There is no current preview in this browser session. Return to preparation after a refresh, expiry or source change.</p>}
    {stage === "receipt" && <section aria-label="GitHub delivery receipts">{Boolean(receiptError) && <><ErrorNotice error={receiptError} /><p>Delivery history could not be refreshed. This does not establish whether an issue was sent.</p><button onClick={() => { setReceiptError(null); setRefreshKey(value => value + 1); }}>Refresh GitHub receipts</button></>}{!receiptsLoaded ? !receiptError && <p role="status">Loading recorded deliveries…</p> : !receipts.length ? !receiptError && <p>No GitHub delivery has been recorded for this meeting.</p> : receipts.map(receipt => <article className="preview" key={receipt.operation_id}><h3>{receipt.repo}</h3><p role="status">{receipt.state}</p>{receipt.results.map((result, i) => <div key={result.item_id || i}><p>Outcome v{result.version} · {result.status}</p>{result.status === "conflict" && <p className="notice">An issue exists, but its content differs from the approved preview. Review it in GitHub, then check the existing delivery. M2O has not approved an overwrite or a replacement send.</p>}{result.url && <a href={result.url} target="_blank" rel="noopener noreferrer">Open issue {result.number} in GitHub</a>}{result.error && <p>{result.error}</p>}</div>)}{receipt.state === "uncertain" && <p className="notice">The provider result is uncertain. Verify the existing issue before preparing another send.</p>}{receipt.can_reconcile && <button disabled={busy} onClick={() => reconcile(receipt)}>Check existing GitHub delivery</button>}</article>)}</section>}
  </section>;
}
