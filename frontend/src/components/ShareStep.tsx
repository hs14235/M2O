import { useEffect, useRef, useState } from "react";
import { api, scoped } from "../api";
import { handoffStages, type HandoffStage, type ProviderId } from "../navigation";
import type { ExportArtifact, Integration, Meeting, User, Workspace } from "../types";
import { Empty, ErrorNotice } from "./Feedback";
import { Publisher } from "./Publisher";
import { JiraPublisher } from "./JiraPublisher";
import { integrationStatus } from "./Integrations";
import { PayloadInspection } from "./ExactPayload";
import { SlackPublisher } from "./SlackPublisher";

const stageNames: Record<HandoffStage, string> = { choose: "Choose", configure: "Prepare", preview: "Exact preview", receipt: "Receipt" };
const stageHints: Record<HandoffStage, string> = { choose: "Select approved outcomes and their next destination.", configure: "Set the destination details. The next page shows exactly what will be handed over.", preview: "Check the stored content before downloading or approving a delivery.", receipt: "Check the result, then make room for your personal plan." };

export function ShareStep({ meeting, workspace, user, selected, onSelect, onJob, onBack, onConnections, stage: routeStage, provider, onStage, onPlan, onCalendar }: { meeting: Meeting; workspace: Workspace; user: User; selected: string[]; onSelect: (id: string, checked: boolean) => void; onJob: (id: string) => void; onBack: () => void; onConnections: () => void; stage?: HandoffStage; provider?: ProviderId; onStage?: (stage: HandoffStage, provider: ProviderId) => void; onPlan?: () => void; onCalendar?: () => void }) {
  const [catalog, setCatalog] = useState<Integration[]>([]), [localDestination, setLocalDestination] = useState<ProviderId>("local"), [localStage, setLocalStage] = useState<HandoffStage>("choose");
  const [format, setFormat] = useState<"markdown" | "json">("markdown"), [evidence, setEvidence] = useState(false), [artifact, setArtifact] = useState<{ key: string; value: ExportArtifact } | null>(null), [downloadRequested, setDownloadRequested] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState<unknown>(null);
  const stage = routeStage || localStage, destination = provider || localDestination;
  function go(next: HandoffStage, target = destination) { setLocalStage(next); setLocalDestination(target); onStage?.(next, target); }
  const key = JSON.stringify([workspace.id, meeting.id, selected, meeting.current_revision, meeting.tasks.map(item => [item.id, item.version, item.status]), format, evidence]), currentKey = useRef(key), request = useRef<AbortController | null>(null); currentKey.current = key;
  useEffect(() => { const controller = new AbortController(); api<Integration[]>(scoped(workspace.id, "/integrations"), { signal: controller.signal }).then(value => { if (!controller.signal.aborted) setCatalog(value); }).catch(e => { if (!controller.signal.aborted) setError(e); }); return () => { controller.abort(); request.current?.abort(); }; }, [workspace.id]);
  const approved = meeting.tasks.filter(item => item.status === "approved"), limit = destination === "jira" ? 1 : destination === "slack" ? 10 : 30;
  const eligible = selected.length > 0 && selected.length <= limit && selected.every(id => approved.some(item => item.id === id));
  const available = catalog.find(item => item.id === destination)?.can_preview === true;
  const prepared = artifact?.key === key ? artifact.value : null;
  async function prepare() {
    request.current?.abort(); const controller = new AbortController(); request.current = controller; const requestedKey = key;
    setBusy(true); setError(null); setArtifact(null); setDownloadRequested(false);
    try {
      const value = await api<ExportArtifact>(scoped(workspace.id, "/meetings/" + meeting.id + "/export"), { signal: controller.signal, method: "POST", body: JSON.stringify({ format, expected_revision: meeting.current_revision, versions: Object.fromEntries(selected.map(id => [id, approved.find(item => item.id === id)!.version])), include_evidence: evidence }) });
      if (!controller.signal.aborted && currentKey.current === requestedKey) { setArtifact({ key: requestedKey, value }); go("preview"); }
    } catch (e) { if (!controller.signal.aborted) setError(e); } finally { if (!controller.signal.aborted) setBusy(false); }
  }
  function download(value: ExportArtifact) {
    const url = URL.createObjectURL(new Blob([value.content], { type: value.media_type + ";charset=utf-8" }));
    const link = document.createElement("a"); link.href = url; link.download = value.filename; link.click(); setTimeout(() => URL.revokeObjectURL(url), 0);
    setDownloadRequested(true); go("receipt");
  }
  return <section className="step-panel share-workflow"><span className="eyebrow">Step 3 of 4 · Deliver · {stageNames[stage]}</span><h1>{stage === "choose" ? "Choose the next home." : stage === "configure" ? "Make the handoff yours." : stage === "preview" ? "See exactly what leaves." : "Know where it landed."}</h1><p>{stageHints[stage]}</p>
    <ol className="handoff-stages" aria-label="Handoff stages">{handoffStages.map((value, i) => <li key={value} aria-current={stage === value ? "step" : undefined}><span aria-hidden="true">{i + 1}</span>{stageNames[value]}</li>)}</ol>
    {stage === "choose" && <><section className="panel"><h2>Select reviewed outcomes</h2>{approved.length ? <fieldset disabled={busy}><legend className="sr-only">Approved outcomes</legend>{approved.map(item => <label className="check" key={item.id}><input type="checkbox" checked={selected.includes(item.id)} disabled={!selected.includes(item.id) && selected.length >= limit} onChange={e => onSelect(item.id, e.target.checked)} />{item.title}</label>)}<p className="muted">{selected.length} selected · {destination === "jira" ? "one outcome per Jira delivery" : "up to " + limit + " per handoff"}</p>{selected.length > limit && <p className="notice">Reduce the selection to {limit} reviewed outcome{limit === 1 ? "" : "s"} for this handoff.</p>}</fieldset> : <Empty>Approve an outcome in Review to include it in a handoff.</Empty>}</section>
      <section className="panel"><h2>Where should these go?</h2><div className="destination-options">{catalog.map(item => <label key={item.id} className={"destination-option " + (destination === item.id ? "active" : "")}><input type="radio" name="destination" value={item.id} checked={destination === item.id} disabled={!item.can_preview || busy} onChange={() => { go("choose", item.id); setError(null); }} /><span><strong>{item.name}</strong><small>{integrationStatus[item.status]}</small><small>{item.description}</small></span></label>)}</div><button className="quiet" onClick={onConnections}>Manage connections</button></section><div className="step-actions"><button className="primary" disabled={!eligible || !available || busy} onClick={() => go("configure")}>Continue to preparation</button></div></>}
    {stage !== "choose" && <p className="handoff-context"><strong>{catalog.find(item => item.id === destination)?.name || destination}</strong> · {selected.length} selected · transcript revision {meeting.current_revision}</p>}
    <ErrorNotice error={error} />
    {destination === "local" && stage === "configure" && <section className="panel"><h2>Prepare a local handoff</h2><p>No external account needed. Only the selected, current approved versions are included.</p><label>File format<select value={format} disabled={busy} onChange={e => setFormat(e.target.value as typeof format)}><option value="markdown">Readable summary (Markdown)</option><option value="json">Structured outcomes (JSON)</option></select></label><label className="check"><input type="checkbox" checked={evidence} disabled={busy} onChange={e => setEvidence(e.target.checked)} />Include transcript evidence</label><button className="primary" disabled={!eligible || busy} onClick={prepare}>Prepare handoff</button></section>}
    {destination === "local" && stage === "preview" && <section className="panel"><h2>Review your local file</h2>{prepared ? <><p role="status">Handoff ready · {selected.length} reviewed outcomes</p><pre className="payload-text">{prepared.content}</pre><PayloadInspection payload={{ filename: prepared.filename, media_type: prepared.media_type, content: prepared.content }} hash={prepared.snapshot_hash} /><button className="primary" onClick={() => download(prepared)}>Download handoff</button></> : <Empty>This browser session has no current prepared file. Return to preparation to generate the approved versions again.</Empty>}</section>}
    {destination === "local" && stage === "receipt" && <section className="panel receipt-panel"><h2>{downloadRequested && prepared ? "Your handoff is ready to carry." : "Prepare a file for this session."}</h2><p>{downloadRequested && prepared ? "The download was requested. Your browser controls where the file is saved." : "A refresh does not prove that a file was saved. Return to preparation to generate a current handoff."}</p>{downloadRequested && prepared && <><p><strong>{prepared.filename}</strong> · {selected.length} reviewed outcomes</p><button onClick={() => download(prepared)}>Download again</button></>}{onCalendar && <button className="primary" onClick={onCalendar}>View outcome calendar</button>}{onPlan && <button onClick={onPlan}>Continue to My day</button>}</section>}
    {destination === "github" && <Publisher workspace={workspace} user={user} meetingId={meeting.id} selected={selected} items={meeting.tasks} onJob={onJob} publicationEnabled={catalog.some(item => item.id === "github" && item.can_publish)} stage={stage} onStage={go} visibility={meeting.visibility} />}
    {destination === "jira" && <div hidden={stage === "choose"}><JiraPublisher workspace={workspace} meetingId={meeting.id} selected={selected} items={meeting.tasks} onJob={onJob} stage={stage} onStage={go} /></div>}
    {destination === "slack" && <SlackPublisher workspace={workspace} meeting={meeting} selected={selected} stage={stage} onStage={go} onJob={onJob} />}
    {stage !== "choose" && destination === "linkedin" && <Empty>{catalog.find(item => item.id === destination)?.description || "Check Connections for this provider's available capabilities."}<button onClick={onConnections}>Open connections</button></Empty>}
    <div className="step-actions">{stage !== "choose" && <button disabled={busy} onClick={() => go(stage === "configure" ? "choose" : "configure")}>{stage === "configure" ? "Back to selection" : "Back to preparation"}</button>}{stage === "configure" && destination !== "local" && <button onClick={() => go("receipt")}>View delivery history</button>}<button onClick={onBack}>Back to review</button></div>
  </section>;
}
