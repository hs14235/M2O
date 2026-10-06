import { useEffect, useRef, useState } from "react";
import { api, scoped } from "../api";
import type { GitHubStatus, User, Workspace } from "../types";
import { ErrorNotice } from "./Feedback";

export default function GitHubConnection({ workspace, user, onChanged }: { workspace: Workspace; user: User; onChanged: () => void }) {
  const [status, setStatus] = useState<GitHubStatus | null>(null), [repo, setRepo] = useState(""), [error, setError] = useState<unknown>(null), [busy, setBusy] = useState(false), [notice, setNotice] = useState("");
  const pending = useRef<AbortController | null>(null), path = scoped(workspace.id, "/integrations/github");
  useEffect(() => {
    const controller = new AbortController();
    api<GitHubStatus>(path, { signal: controller.signal }).then(value => { if (!controller.signal.aborted) { setStatus(value); setRepo(value.destination?.repo || ""); } }).catch(e => { if (!controller.signal.aborted) setError(e); });
    return () => { controller.abort(); pending.current?.abort(); };
  }, [path]);
  async function bind(event: React.FormEvent) {
    event.preventDefault(); if (!status) return;
    const controller = new AbortController(); pending.current?.abort(); pending.current = controller; setBusy(true); setError(null); setNotice("");
    try {
      const value = await api<GitHubStatus>(path + "/destination", { signal: controller.signal, method: "POST", body: JSON.stringify({ repo, expected_version: status.destination?.version || 0 }) });
      if (!controller.signal.aborted) { setStatus(value); setNotice("Repository binding saved for this workspace. No issue was created. Existing previews require regeneration."); onChanged(); }
    } catch (e) { if (!controller.signal.aborted) setError(e); } finally { if (!controller.signal.aborted) setBusy(false); }
  }
  return <section className="panel" aria-labelledby="github-account-heading"><span className="eyebrow">GitHub destination</span><h2 id="github-account-heading">Bind a repository to this workspace.</h2><p>The operator's allowed repositories set the outer limit. This workspace also needs its own explicit binding.</p><ErrorNotice error={error} />{!status ? <p role="status">Checking GitHub configuration…</p> : <>{status.destination ? <p className="notice">Workspace destination: <strong>{status.destination.repo}</strong> · binding v{status.destination.version}</p> : <p>No repository is bound to this workspace.</p>}{!status.configured && <p className="muted">The operator must configure GitHub credentials and an allowed repository before publication.</p>}{status.can_manage && <form onSubmit={bind}><fieldset disabled={busy || !status.configured}><legend className="sr-only">Workspace GitHub binding</legend><label>Allowed GitHub repository<select required value={repo} onChange={event => setRepo(event.target.value)}><option value="">Choose an allowed repository</option>{user.capabilities.allowed_repos.map(value => <option key={value} value={value}>{value}</option>)}</select></label><button disabled={!repo || repo === status.destination?.repo}>Save workspace repository</button></fieldset></form>}{!status.can_manage && <p className="muted">Repository bindings are managed by workspace owners outside demo mode.</p>}</>}{notice && <p role="status">{notice}</p>}</section>;
}
