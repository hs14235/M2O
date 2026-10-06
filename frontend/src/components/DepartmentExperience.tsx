import { useEffect, useRef, useState } from "react";
import type { Department, Workspace } from "../types";
import { StudioMedia } from "./StudioMedia";

export const departmentExperience = {
  hr: { name: "People Operations", headline: "Make room for people.", detail: "Turn onboarding conversations into confirmed responsibilities and a thoughtful next step.", motif: "Connection studio", tags: ["Onboarding", "Clear ownership", "Private context"] },
  finance: { name: "Finance Control", headline: "Bring the details into balance.", detail: "Review decisions, resolve dates and turn financial follow-ups into accountable work.", motif: "Control room", tags: ["Verified decisions", "Date clarity", "Review first"] },
  engineering: { name: "Engineering", headline: "Turn discussion into momentum.", detail: "Make blockers visible, confirm the plan and move reviewed work into your team's tools.", motif: "Launch studio", tags: ["Actionable work", "Visible blockers", "Source evidence"] },
} as const;

export function useMotionPreference() {
  const [calm, setCalm] = useState(() => { try { return localStorage.getItem("m2o-calm") === "true"; } catch { return false; } });
  const [reduced, setReduced] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const change = () => setReduced(media.matches);
    media.addEventListener("change", change); return () => media.removeEventListener("change", change);
  }, []);
  useEffect(() => { document.documentElement.dataset.motion = calm || reduced ? "calm" : "full"; }, [calm, reduced]);
  return { calm: calm || reduced, reduced, toggle: () => setCalm(value => { const next = !value; try { localStorage.setItem("m2o-calm", String(next)); } catch { /* The current session preference still applies when storage is unavailable. */ } return next; }) };
}

export function DepartmentSwitch({ workspaces, active, onChange }: { workspaces: Workspace[]; active?: Workspace; onChange: (id: string) => void }) {
  return <div className="department-switch" role="group" aria-label="Department experiences">{(Object.keys(departmentExperience) as Department[]).map(department => {
    const targets = workspaces.filter(w => w.department === department), target = active?.department === department ? active : targets[0];
    return <button key={department} type="button" aria-pressed={active?.department === department} disabled={!target} onClick={() => target && onChange(target.id)}><span className={"department-dot " + department} aria-hidden="true" />{departmentExperience[department].name}</button>;
  })}</div>;
}

export function DepartmentScene({ department, calm }: { department: Department; calm: boolean }) {
  const container = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const node = container.current;
    if (!node) return;
    if (calm) { node.style.setProperty("--scene-scroll", "0px"); return; }
    let frame = 0;
    const update = () => { if (!frame) frame = requestAnimationFrame(() => { frame = 0; node.style.setProperty("--scene-scroll", Math.min(window.scrollY * .06, 24) + "px"); }); };
    window.addEventListener("scroll", update, { passive: true }); update();
    return () => { window.removeEventListener("scroll", update); cancelAnimationFrame(frame); };
  }, [calm, department]);
  return <div ref={container} className={"department-scene scene-" + department} aria-hidden="true"><div className="scene-orbit" /><div className="scene-sphere" /><div className="scene-block" /><div className="scene-chip chip-one" /><div className="scene-chip chip-two" /><span className="scene-spark spark-one" /><span className="scene-spark spark-two" /></div>;
}

export function DepartmentHero({ workspace, calm, compact = false }: { workspace: Workspace; calm: boolean; compact?: boolean }) {
  const experience = departmentExperience[workspace.department];
  return <section className={"department-hero" + (compact ? " compact-hero" : "")} key={workspace.department} aria-label={experience.name + " experience"}><div className="hero-copy"><span className="eyebrow">M2O / {experience.motif}</span><h2>{compact ? experience.name : experience.headline}</h2>{!compact && <><p>{experience.detail}</p><div className="hero-tags">{experience.tags.map(tag => <span key={tag}>{tag}</span>)}</div></>}</div>{compact ? <DepartmentScene department={workspace.department} calm={calm} /> : <StudioMedia department={workspace.department} calm={calm} />}</section>;
}
