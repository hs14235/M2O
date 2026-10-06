import { useEffect, useState } from "react";
import { api, scoped } from "../api";
import type { Participant, User, Workspace } from "../types";
import { Empty, ErrorNotice } from "./Feedback";

export default function Directory({ workspace, user, onDirty }: { workspace: Workspace; user: User; onDirty: (value: boolean) => void }) {
  const [people, setPeople] = useState<Participant[]>([]), [error, setError] = useState<unknown>(null), [busy, setBusy] = useState(false);
  const [name, setName] = useState(""), [role, setRole] = useState(""), [aliases, setAliases] = useState(""), [github, setGithub] = useState(""), [linkedin, setLinkedin] = useState(""), [share, setShare] = useState(false);
  useEffect(() => { onDirty(Boolean(name || role || aliases || github || linkedin || share)); return () => onDirty(false); }, [name, role, aliases, github, linkedin, share, onDirty]);
  async function load(signal?: AbortSignal) { setPeople(await api(scoped(workspace.id, "/participants"), { signal })); }
  useEffect(() => { const controller = new AbortController(); load(controller.signal).catch(e => { if (!controller.signal.aborted) setError(e); }); return () => controller.abort(); }, [workspace.id]);
  async function add(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(null);
    try {
      await api(scoped(workspace.id, "/participants"), { method: "POST", body: JSON.stringify({ name, role, aliases: aliases.split(",").map(v => v.trim()).filter(Boolean), github_login: github || null, linkedin_url: linkedin || null, linked_user_id: share ? user.id : null }) });
      setName(""); setRole(""); setAliases(""); setGithub(""); setLinkedin(""); setShare(false); await load();
    } catch (e) { setError(e); } finally { setBusy(false); }
  }
  return <div className="directory layout">
    <section className="panel"><span className="eyebrow">Participant context</span><h1>Confirmed directory</h1><p>Directory records are supplied and confirmed by workspace members. Similar names remain separate until a person explicitly resolves a transcript mention.</p>
      {people.length === 0 ? <Empty>Add a participant to resolve names and assign outcomes.</Empty> : <ul className="people">{people.map(person => <li key={person.id}><strong>{person.name}</strong><span>{person.role || "Participant"}</span><small>Workspace directory · {person.aliases.length ? "Aliases: " + person.aliases.join(", ") : "No aliases"}</small>{person.github_login && <small>GitHub: {person.github_login}</small>}{person.linkedin_url && <a href={person.linkedin_url} target="_blank" rel="noopener noreferrer">Member-supplied LinkedIn profile</a>}{person.linked_user_id === user.id && <small>Linked to your account</small>}</li>)}</ul>}
    </section>
    <div>{user.is_visitor ? <section className="panel"><h2>Synthetic participant context</h2><p>This demo uses its own prepared directory. Confirm the correct person from a meeting’s People step. Adding real participant details requires an invited private workspace.</p></section> : <section className="panel"><h2>Add confirmed participant</h2><form onSubmit={add}><fieldset disabled={busy || workspace.role === "viewer"}><legend className="sr-only">Participant details</legend>
      <label>Name<input required maxLength={120} value={name} onChange={e => setName(e.target.value)} /></label>
      <label>Role or relevant responsibilities<input maxLength={160} value={role} onChange={e => setRole(e.target.value)} /></label>
      <label>Aliases, separated by commas<input value={aliases} onChange={e => setAliases(e.target.value)} /></label>
      <label>GitHub login<input maxLength={39} value={github} onChange={e => setGithub(e.target.value)} /></label>
      <label>Member-supplied LinkedIn URL<input type="url" value={linkedin} onChange={e => setLinkedin(e.target.value)} placeholder="https://www.linkedin.com/in/…" /></label>
      <label className="check"><input type="checkbox" checked={share} onChange={e => setShare(e.target.checked)} />This is my directory record; link it to my account</label>
      <button className="primary" disabled={!name.trim()}>Confirm and add participant</button>
    </fieldset></form></section>}
    <ErrorNotice error={error} /></div>
  </div>;
}
