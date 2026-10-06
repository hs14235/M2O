import { useEffect, useState } from "react";
import { api, scoped } from "../api";
import type { Role, Workspace } from "../types";
import { ErrorNotice } from "./Feedback";
import Invitations from "./Invitations";

export default function Administration({ workspace }: { workspace: Workspace }) {
  const [members, setMembers] = useState<{ id: string; name: string; email: string; role: Role }[]>([]);
  const [error, setError] = useState<unknown>(null), [busy, setBusy] = useState(false);
  async function load(signal?: AbortSignal) {
    const people = workspace.role === "owner" ? await api<typeof members>(scoped(workspace.id, "/members"), { signal }) : []; if (!signal?.aborted) setMembers(people);
  }
  useEffect(() => { const controller = new AbortController(); load(controller.signal).catch(e => { if (!controller.signal.aborted) setError(e); }); return () => controller.abort(); }, [workspace.id]);
  async function change(id: string, role: Role) {
    setBusy(true); setError(null);
    try { await api(scoped(workspace.id, "/members/" + id), { method: "PATCH", body: JSON.stringify({ role }) }); await load(); } catch (e) { setError(e); } finally { setBusy(false); }
  }
  return <div className="layout"><section className="panel"><h1>Workspace access</h1><p>Owners manage members. Reviewers approve outcomes and publication. Editors import and review drafts. Viewers read permitted meetings. Restricted meetings are visible to their creator, owners and reviewers.</p>
    {workspace.role === "owner" && <><ul className="people">{members.map(member => <li key={member.id}><strong>{member.name}</strong><span>{member.email}</span><label>Role for {member.name}<select disabled={busy} value={member.role} onChange={e => change(member.id, e.target.value as Role)}>{["owner", "reviewer", "editor", "viewer"].map(role => <option key={role}>{role}</option>)}</select></label></li>)}</ul><Invitations workspace={workspace} /></>}
    <ErrorNotice error={error} /></section></div>;
}
