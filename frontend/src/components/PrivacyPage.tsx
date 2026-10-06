import { useEffect, useState } from "react";
import { api, scoped } from "../api";
import type { User } from "../types";
import { ErrorNotice } from "./Feedback";

interface PrivacyStatus { id: string; name: string; version: number; state: "active" | "pending_erasure" | "erased"; can_erase: boolean; retention_days: number; remote_content_erased: false }
interface ErasureReceipt { state: "erased" | "pending_erasure"; retention_days: number; retry_required?: boolean; remote_content_erased: false }
export default function PrivacyPage({ workspaceId, user, onWorkspaceChanged, onAccountErased }: { workspaceId: string; user: User; onWorkspaceChanged: () => Promise<void>; onAccountErased: () => void }) {
  const [status, setStatus] = useState<PrivacyStatus | null>(null), [receipt, setReceipt] = useState<ErasureReceipt | null>(null), [error, setError] = useState<unknown>(null), [busy, setBusy] = useState(false), [refresh, setRefresh] = useState(0);
  const [password, setPassword] = useState(""), [name, setName] = useState(""), [accountPassword, setAccountPassword] = useState(""), [confirmation, setConfirmation] = useState(""), [download, setDownload] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    api<PrivacyStatus>(scoped(workspaceId, "/privacy"), { signal: controller.signal }).then(value => { if (!controller.signal.aborted) { setStatus(value); setError(null); } }).catch(e => { if (!controller.signal.aborted) setError(e); });
    return () => controller.abort();
  }, [workspaceId, refresh]);
  async function exportData(account: boolean) {
    setBusy(true); setError(null); setDownload("");
    try {
      const data = await api(account ? "/privacy/account/export" : scoped(workspaceId, "/privacy/export"));
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
      const link = document.createElement("a"); link.href = url; link.download = account ? "m2o-account-export.json" : "m2o-workspace-export.json"; document.body.append(link);
      try { link.click(); setDownload("Download requested. Your browser controls where the private JSON file is saved."); } finally { link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
    } catch (e) { setError(e); } finally { setBusy(false); }
  }
  async function eraseWorkspace(event: React.FormEvent) {
    event.preventDefault(); if (!status) return;
    setBusy(true); setError(null);
    try {
      const result = await api<ErasureReceipt>(scoped(workspaceId, "/privacy/erase"), { method: "POST", body: JSON.stringify({ password, confirmation_name: name, expected_version: status.version }) });
      setReceipt(result);
      if (result.state === "erased") await onWorkspaceChanged();
      else { setStatus(null); setRefresh(value => value + 1); }
    } catch (e) { setError(e); } finally { setPassword(""); setBusy(false); }
  }
  async function eraseAccount(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(null);
    try { await api("/privacy/account/erase", { method: "POST", body: JSON.stringify({ password: accountPassword, confirmation }) }); onAccountErased(); }
    catch (e) { setError(e); } finally { setAccountPassword(""); setBusy(false); }
  }
  return <div className="privacy-page"><span className="eyebrow">Privacy & control</span><h1>Your data, with clear boundaries.</h1><p>Exports contain private information. Erasure changes local M2O data; content already delivered to team tools remains with those providers.</p><ErrorNotice error={error} />{download && <p role="status" className="notice">{download}</p>}<section className="panel"><h2>Take a copy</h2><p>Your account export includes your own account and personal-plan information. A workspace export requires owner authority and includes its retained local content. Keep downloaded files in a private location.</p><div className="actions"><button disabled={busy || Boolean(user.is_visitor)} onClick={() => exportData(true)}>Download my account data</button><button disabled={busy || !status?.can_erase || status.state !== "active"} onClick={() => exportData(false)}>Download workspace data</button></div></section><section className="panel"><h2>Workspace erasure</h2>{receipt?.state === "erased" ? <div className="notice" role="status"><strong>Local workspace content erased.</strong><p>External tool content was not erased. Minimum delivery tombstones may remain for {receipt.retention_days} days to prevent unsafe repeats and preserve unresolved outcomes.</p></div> : !status ? error ? <><p>Workspace privacy status could not be loaded. Erasure is unavailable until current authority and version are checked.</p><button disabled={busy} onClick={() => setRefresh(value => value + 1)}>Refresh privacy status</button></> : <p role="status">Checking workspace privacy status…</p> : <><p><strong>{status.name}</strong> · version {status.version} · {status.state.replaceAll("_", " ")}</p>{status.state === "pending_erasure" && <p className="notice" role="status">Erasure is pending while previously running work settles. Ordinary workspace work is frozen. Refresh this status, then submit an explicit retry; refreshing does not erase or resend anything.</p>}{status.can_erase ? <details open={status.state === "pending_erasure"}><summary>{status.state === "pending_erasure" ? "Retry local workspace erasure" : "Erase this local workspace"}</summary><p>This removes local transcripts, participant context, reviews and plans for this workspace. Running work can delay completion. Minimum delivery tombstones may remain for {status.retention_days} days. External Jira, Slack, GitHub and LinkedIn content is retained by its provider.</p><form onSubmit={eraseWorkspace}><fieldset disabled={busy}><legend className="sr-only">Confirm workspace erasure</legend><label>Type the current workspace name<input required maxLength={120} value={name} onChange={e => setName(e.target.value)} autoComplete="off" /></label><label>Your password for workspace erasure<input required type="password" maxLength={256} autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} /></label><button className="danger" disabled={name !== status.name || !password}>{status.state === "pending_erasure" ? "Retry confirmed workspace erasure" : "Erase confirmed local workspace"}</button></fieldset></form></details> : <p>Your current role cannot erase this workspace.</p>}<button disabled={busy} onClick={() => setRefresh(value => value + 1)}>Refresh privacy status</button></>}</section>{!user.is_visitor && <section className="panel"><h2>Delete my account</h2><details><summary>Review account deletion</summary><p>Your account is deactivated and anonymized; sessions and credentials are revoked. Shared workspace content is retained. If you are a workspace's only active owner, assign another owner or erase that workspace first.</p><form onSubmit={eraseAccount}><fieldset disabled={busy}><legend className="sr-only">Confirm account deletion</legend><label>Type DELETE MY ACCOUNT<input required value={confirmation} onChange={e => setConfirmation(e.target.value)} autoComplete="off" /></label><label>Your password for account deletion<input required type="password" maxLength={256} autoComplete="current-password" value={accountPassword} onChange={e => setAccountPassword(e.target.value)} /></label><button className="danger" disabled={confirmation !== "DELETE MY ACCOUNT" || !accountPassword}>Delete confirmed account</button></fieldset></form></details></section>}</div>;
}
