import { useEffect, useRef, useState } from "react";
import type { Department } from "../types";

/** Decorative authored motion, with a complete static presentation by default. */
export function StudioMedia({ department, calm }: { department: Department; calm: boolean }) {
  const root = useRef<HTMLDivElement>(null), video = useRef<HTMLVideoElement>(null);
  const [visible, setVisible] = useState(false), [foreground, setForeground] = useState(!document.hidden);
  const [paused, setPaused] = useState(() => { try { return localStorage.getItem("m2o-studio-paused") === "true" || !window.IntersectionObserver; } catch { return !window.IntersectionObserver; } }), [failed, setFailed] = useState(false), [playing, setPlaying] = useState(false), [loaded, setLoaded] = useState(false), [optIn, setOptIn] = useState(false);
  const saveData = Boolean((navigator as Navigator & { connection?: { saveData?: boolean } }).connection?.saveData);
  const allowed = !calm && (!saveData || optIn), active = allowed && visible && foreground && !paused && !failed;
  useEffect(() => { setFailed(false); setPlaying(false); setLoaded(false); }, [department]);
  useEffect(() => { try { localStorage.setItem("m2o-studio-paused", String(paused)); } catch { /* Session state remains usable when browser storage is unavailable. */ } }, [paused]);
  useEffect(() => {
    if (!root.current || !window.IntersectionObserver) return;
    const observer = new IntersectionObserver(entries => setVisible(entries.some(entry => entry.isIntersecting && entry.intersectionRatio > .1)), { threshold: [0, .1] });
    observer.observe(root.current); return () => observer.disconnect();
  }, []);
  useEffect(() => {
    const change = () => setForeground(!document.hidden);
    document.addEventListener("visibilitychange", change); return () => document.removeEventListener("visibilitychange", change);
  }, []);
  useEffect(() => { if (active) setLoaded(true); if (calm) { setLoaded(false); setPlaying(false); } }, [active, calm, department]);
  useEffect(() => {
    const node = video.current; if (!node) return;
    let cancelled = false;
    if (active && loaded) node.play()?.catch(() => { if (!cancelled) { setFailed(true); setPlaying(false); } });
    else node.pause();
    return () => { cancelled = true; node.pause(); };
  }, [active, loaded, department]);
  useEffect(() => {
    const node = root.current; if (!node) return;
    if (!allowed) { node.style.setProperty("--studio-shift", "0px"); return; }
    let frame = 0;
    const update = () => { if (!frame) frame = requestAnimationFrame(() => { frame = 0; node.style.setProperty("--studio-shift", Math.max(-8, Math.min(8, (node.getBoundingClientRect().top - 180) * .02)) + "px"); }); };
    window.addEventListener("scroll", update, { passive: true }); update();
    return () => { window.removeEventListener("scroll", update); cancelAnimationFrame(frame); };
  }, [allowed]);
  return <div ref={root} className="studio-media" data-playing={playing && allowed}>
    <div className="studio-visual" aria-hidden="true"><img src={"/scenes/" + department + ".webp"} width={640} height={480} alt="" decoding="async" /><video ref={video} width={640} height={480} muted loop playsInline preload="none" tabIndex={-1} src={loaded && allowed ? "/scenes/" + department + ".mp4" : undefined} poster={"/scenes/" + department + ".webp"} onPlaying={() => setPlaying(true)} onError={() => { setFailed(true); setPlaying(false); }} /></div>
    {calm ? <span className="studio-control">Studio motion paused</span> : failed ? <span className="studio-control">Static studio scene</span> : <button type="button" className="studio-control" aria-pressed={paused || (saveData && !optIn)} onClick={() => { if (!window.IntersectionObserver) setVisible(true); if (saveData && !optIn) { setOptIn(true); setPaused(false); } else setPaused(value => !value); }}>{paused || (saveData && !optIn) ? "Play studio motion" : "Pause studio motion"}</button>}
  </div>;
}
