import { useEffect, useState } from "react";
import { api, scoped } from "../api";
import type { Role, Workspace } from "../types";
import { ErrorNotice } from "./Feedback";

interface Invitation { id: string; email: string; role: Role; expires_at: string; state: string }
export default function Invitations({ workspace }: { workspace: Workspace }) {
  const [invitations, setInvitations] = useState<Invitation[]>([]), [email, setEmail] = useState(""), [role, setRole] = useState<Role>("editor"), [issued, setIssued] = useState<(Invitation & { accept_url: string }) | null>(null);
  const [busy, setBusy] = useState(false), [loaded, setLoaded] = useState(false), [error, setError] = useState<unknown>(null), [copied, setCopied] = useState(false);
  async function load(signal?: AbortSignal) { const value = await api<{ invitations: Invitation[] }>(scoped(workspace.id, "/invitations"), { signal }); if (!signal?.aborted) { setInvitations(value.invitations); setLoaded(true); } }
  useEffect(() => { const controller = new AbortController(); load(controller.signal).catch(e => { if (!controller.signal.aborted) setError(e); }); return () => controller.abort(); }, [workspace.id]);
  async function issue(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(null); setIssued(null); setCopied(false);
    try { setIssued(await api(scoped(workspace.id, "/invitations"), { method: "POST", body: JSON.stringify({ email, role }) })); setEmail(""); await load(); }
    catch (e) { setError(e); } finally { setBusy(false); }
  }
  async function revoke(invitation: Invitation) {
    if (!window.confirm("Revoke this invitation? The recipient will need a new link.")) return;
    setBusy(true); setError(null);
    try { await api(scoped(workspace.id, "/invitations/" + invitation.id), { method: "DELETE" }); if (issued?.id === invitation.id) setIssued(null); await load(); }
    catch (e) { setError(e); } finally { setBusy(false); }
  }
  return <section aria-labelledby="invitation-heading"><h2 id="invitation-heading">Invite someone to this workspace</h2><p>Each recipient accepts their own role. New accounts choose their own password; existing accounts authenticate before accepting.</p><form onSubmit={issue}><fieldset disabled={busy}><legend className="sr-only">Issue workspace invitation</legend><label>Invitation email<input required type="email" maxLength={254} value={email} onChange={e => setEmail(e.target.value)} /></label><label>Invited role<select value={role} onChange={e => setRole(e.target.value as Role)}>{["reviewer", "editor", "viewer", "owner"].map(value => <option key={value}>{value}</option>)}</select></label><button className="primary">Create private invitation link</button></fieldset></form><ErrorNotice error={error} />{issued && <div className="notice"><h3>Share this link privately</h3><p>This installation does not send an email. The link is shown once and expires {new Date(issued.expires_at).toLocaleString()}. Anyone holding it can inspect the invitation, so use your approved private channel.</p><label>One-time invitation link<input readOnly value={issued.accept_url} autoComplete="off" onFocus={e => e.target.select()} /></label><div className="actions"><button onClick={async () => { try { await navigator.clipboard.writeText(issued.accept_url); setCopied(true); } catch { setError(new Error("Clipboard access is unavailable. Select and copy the link directly.")); } }}>Copy invitation link</button><button onClick={() => { setIssued(null); setCopied(false); }}>Hide private link</button></div>{copied && <p role="status">Copied to your clipboard. No message was sent.</p>}</div>}{!loaded ? error ? <button onClick={() => { setError(null); void load().catch(setError); }}>Refresh invitation history</button> : <p role="status">Loading invitation history…</p> : <><h3>Invitation history</h3>{!invitations.length ? <p>No invitations have been recorded.</p> : <ul className="people">{invitations.map(invitation => <li key={invitation.id}><strong>{invitation.email}</strong><span>{invitation.role} · {invitation.state}</span><time dateTime={invitation.expires_at}>Expires {new Date(invitation.expires_at).toLocaleString()}</time>{invitation.state === "pending" && <button disabled={busy} onClick={() => revoke(invitation)}>Revoke invitation for {invitation.email}</button>}</li>)}</ul>}</>}</section>;
}
