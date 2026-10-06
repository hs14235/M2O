import { useEffect, useState } from "react";
import { api } from "../api";
import type { DemoCatalog } from "../types";
import { ErrorNotice } from "./Feedback";

export default function DemoEntry({ onStarted }: { onStarted: () => Promise<void> }) {
  const [catalog, setCatalog] = useState<DemoCatalog | null>(null), [error, setError] = useState<unknown>(null), [busy, setBusy] = useState(false), [reload, setReload] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    api<DemoCatalog>("/demo/scenarios", { signal: controller.signal }).then(value => { if (!controller.signal.aborted) setCatalog(value); }).catch(e => { if (!controller.signal.aborted) setError(e); });
    return () => controller.abort();
  }, [reload]);
  async function start() {
    setBusy(true); setError(null);
    try { await api("/demo/start", { method: "POST" }); await onStarted(); }
    catch (e) { setError(e); } finally { setBusy(false); }
  }
  return <section className="demo-entry" aria-labelledby="demo-entry-heading"><span className="eyebrow">Take M2O for a spin</span><h2 id="demo-entry-heading">Your own little outcome studio.</h2><p>Explore Engineering, People Operations and Finance with approved synthetic examples. Each visitor gets separate temporary workspaces.</p><p className="muted">Real transcript uploads and external sends are disabled in the demo. Private use requires an invitation.</p><ErrorNotice error={error} />{!catalog ? error ? <button onClick={() => { setError(null); setReload(value => value + 1); }}>Check demo availability again</button> : <p role="status">Checking demo availability…</p> : catalog.enabled ? <button className="primary" disabled={busy} onClick={start}>{busy ? "Opening your studio…" : "Explore the isolated demo"}</button> : <p>Visitor demos are disabled on this installation. Use your invited private account below.</p>}</section>;
}
