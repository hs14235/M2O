import { useEffect, useState } from "react";
import { api } from "../api";
import { accessToken, type AccessPath } from "../access-link";
import type { Role, User } from "../types";
import { ErrorNotice } from "./Feedback";

interface InvitationDetails { workspace_name: string; email: string; role: Role; expires_at: string; requires_sign_in: boolean }
export default function AccessPortal({ path, initialToken, user, onAuthenticated, onSignOut, onAccountReset, onTokenUsed, onContinue }: { path: AccessPath; initialToken: string; user: User | null; onAuthenticated: () => Promise<void>; onSignOut: () => Promise<void>; onAccountReset: () => void; onTokenUsed: () => void; onContinue: (workspace?: string) => void }) {
  const [token, setToken] = useState(initialToken), [info, setInfo] = useState<InvitationDetails | null>(null), [email, setEmail] = useState(""), [name, setName] = useState(""), [password, setPassword] = useState(""), [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false), [error, setError] = useState<unknown>(null), [notice, setNotice] = useState(""), [finished, setFinished] = useState<{ workspace?: string; signIn: boolean } | null>(null);
  useEffect(() => { if (initialToken) { setToken(initialToken); setInfo(null); } }, [initialToken]);
  const mismatched = Boolean(user && (user.is_visitor || !info || user.email.toLowerCase() !== info.email.toLowerCase()));
  async function run(action: () => Promise<void>) {
    setBusy(true); setError(null); setNotice("");
    try { await action(); } catch (e) { setError(e); } finally { setBusy(false); setPassword(""); setConfirm(""); }
  }
  async function inspect(event: React.FormEvent) {
    event.preventDefault(); setInfo(null);
    await run(async () => { const value = accessToken(token, path); const details = await api<InvitationDetails>("/invitations/inspect", { method: "POST", body: JSON.stringify({ token: value }) }); setToken(value); setInfo(details); setEmail(details.email); });
  }
  async function accept(event: React.FormEvent) {
    event.preventDefault(); if (!info) return;
    await run(async () => {
      if (!info.requires_sign_in && password !== confirm) throw new Error("The new passwords must match.");
      const result = await api<{ workspace_id: string; sign_in_required: boolean }>("/invitations/accept", { method: "POST", body: JSON.stringify({ token: accessToken(token, path), email: info.email, ...(!info.requires_sign_in ? { name, password } : {}) }) });
      setToken(""); onTokenUsed(); setFinished({ workspace: result.workspace_id, signIn: result.sign_in_required });
      if (!result.sign_in_required) await onAuthenticated();
    });
  }
  async function signIn(event: React.FormEvent) {
    event.preventDefault();
    await run(async () => { await api("/auth/login", { method: "POST", body: JSON.stringify({ email: info!.email, password }) }); await onAuthenticated(); });
  }
  async function requestRecovery(event: React.FormEvent) {
    event.preventDefault();
    await run(async () => { const result = await api<{ message: string }>("/auth/recovery/request", { method: "POST", body: JSON.stringify({ email }) }); setNotice(result.message); });
  }
  async function reset(event: React.FormEvent) {
    event.preventDefault();
    await run(async () => {
      if (password !== confirm) throw new Error("The new passwords must match.");
      await api("/auth/recovery/reset", { method: "POST", body: JSON.stringify({ token: accessToken(token, path), email, password }) });
      setToken(""); onTokenUsed(); onAccountReset(); setFinished({ signIn: true });
    });
  }
  async function continueFromReceipt() {
    if (finished?.workspace && !finished.signIn) await run(async () => { await onAuthenticated(); onContinue(finished.workspace); });
    else onContinue();
  }
  const newPassword = <><label>New password<input required type="password" minLength={12} maxLength={256} autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} /></label><label>Confirm new password<input required type="password" minLength={12} maxLength={256} autoComplete="new-password" value={confirm} onChange={e => setConfirm(e.target.value)} /></label></>;
  return <main className="login access-portal"><section className="login-story"><span className="eyebrow">M2O · Private access</span><h1>{path === "/invite" ? "A place for your next steps." : "Get back to your workspace."}</h1><p>{path === "/invite" ? "An invitation grants a specific workspace role. You choose your own password; existing accounts keep theirs." : "Recovery is operator assisted on this installation. After identity verification, a private link lets you choose a new password."}</p><button onClick={() => onContinue()}>Return to M2O</button></section><section className="panel login-form"><ErrorNotice error={error} />{notice && <p role="status" className="notice">{notice}</p>}{finished ? <><h2>{path === "/invite" ? "Invitation accepted." : "Password reset."}</h2><p>{finished.signIn ? "Sign in with your own account to continue." : "Your workspace membership is ready."}</p>{path === "/recover" && <p>Previous sessions and access tokens have been revoked.</p>}<button className="primary" disabled={busy} onClick={continueFromReceipt}>{finished.signIn ? "Go to sign in" : "Open workspace"}</button></> : path === "/invite" ? <><h2>Join an invited workspace</h2>{!info ? <form onSubmit={inspect}><fieldset disabled={busy}><legend className="sr-only">Inspect invitation</legend><label>Private invitation link or token<input required type="password" autoComplete="off" value={token} onChange={e => setToken(e.target.value)} /></label><p className="muted">The link token stays in memory. After a refresh, paste the link again.</p><button className="primary">Review invitation</button></fieldset></form> : <><h3>{info.workspace_name}</h3><p>Invited identity: {info.email}<br />Workspace role: {info.role}<br />Expires: <time dateTime={info.expires_at}>{new Date(info.expires_at).toLocaleString()}</time></p>{mismatched ? <><p className="notice">Sign out of the current account before accepting as the invited person.</p><button disabled={busy} onClick={() => run(onSignOut)}>Sign out of current account</button></> : info.requires_sign_in && !user ? <form onSubmit={signIn}><fieldset disabled={busy}><legend className="sr-only">Authenticate invited account</legend><label>Invited email<input type="email" readOnly value={info.email} autoComplete="username" /></label><label>Password<input required type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} /></label><button className="primary">Sign in as invited person</button></fieldset></form> : <form onSubmit={accept}><fieldset disabled={busy}><legend className="sr-only">Accept invitation</legend>{!info.requires_sign_in && <><label>Your name<input required maxLength={120} value={name} onChange={e => setName(e.target.value)} autoComplete="name" /></label>{newPassword}</>}<button className="primary">Accept workspace invitation</button></fieldset></form>}<button className="quiet" disabled={busy} onClick={() => { setInfo(null); setPassword(""); setConfirm(""); }}>Use a different invitation</button></>}</> : <><h2>Recover your account</h2><form onSubmit={requestRecovery}><fieldset disabled={busy}><legend className="sr-only">Recovery guidance</legend><label>Account email<input required type="email" maxLength={254} autoComplete="username" value={email} onChange={e => setEmail(e.target.value)} /></label><p>This form gives private recovery instructions. It does not send an email or verify that an account exists.</p><button>Get recovery instructions</button></fieldset></form><details open={Boolean(initialToken)}><summary>I have an operator-issued recovery link</summary><form onSubmit={reset}><fieldset disabled={busy}><legend className="sr-only">Set new password</legend><label>Private recovery link or token<input required type="password" autoComplete="off" value={token} onChange={e => setToken(e.target.value)} /></label><label>Recovery account email<input required type="email" value={email} onChange={e => setEmail(e.target.value)} autoComplete="username" /></label>{newPassword}<button className="primary">Reset password and revoke previous access</button></fieldset></form></details></>}</section></main>;
}
