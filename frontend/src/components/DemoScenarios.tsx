import { useEffect, useState } from "react";
import { api, scoped } from "../api";
import type { DemoCatalog, DemoScenario, Workspace } from "../types";
import { ErrorNotice } from "./Feedback";

export default function DemoScenarios({ workspace, disabled, onLoaded }: { workspace: Workspace; disabled: boolean; onLoaded: (result: { meeting_id: string; job_id: string | null }) => void }) {
  const [catalog, setCatalog] = useState<DemoCatalog | null>(null), [error, setError] = useState<unknown>(null), [busy, setBusy] = useState(false), [reload, setReload] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    api<DemoCatalog>("/demo/scenarios", { signal: controller.signal }).then(value => { if (!controller.signal.aborted) setCatalog(value); }).catch(e => { if (!controller.signal.aborted) setError(e); });
    return () => controller.abort();
  }, [reload]);
  async function load(scenario: DemoScenario) {
    setBusy(true); setError(null);
    try { onLoaded(await api(scoped(workspace.id, "/demo/load"), { method: "POST", body: JSON.stringify({ fixture_id: scenario.id }) })); }
    catch (e) { setError(e); } finally { setBusy(false); }
  }
  return <section className="panel demo-scenarios" aria-labelledby="demo-scenarios-heading"><h2 id="demo-scenarios-heading">Choose a synthetic conversation</h2><p>Follow an example through People, Review, Share and My day. Loading the same example returns its existing meeting and keeps your reviews.</p><ErrorNotice error={error} />{!catalog ? error ? <button onClick={() => { setError(null); setReload(value => value + 1); }}>Try loading examples again</button> : <p role="status">Loading available examples…</p> : !catalog.enabled ? <p>New example loading is disabled on this installation.</p> : <div className="scenario-grid">{catalog.scenarios.filter(item => item.department === null || item.department === workspace.department).map(item => <article key={item.id}><span className="eyebrow">{item.id === "no-outcomes" ? "No-action case" : "Department example"}</span><h3>{item.title}</h3><p>{item.id === "no-outcomes" ? "An update with no work to manufacture. An empty result can be the right result." : "Confirm names, review evidence and make a tangible plan."}</p><details><summary>Read the synthetic transcript</summary><pre className="payload-text">{item.transcript}</pre></details><button className="primary" disabled={disabled || busy} onClick={() => load(item)}>Open {item.title}</button></article>)}</div>}</section>;
}
