import { useEffect, useRef, useState, type ReactNode } from "react";

function initial(key: string) { try { return localStorage.getItem(key) !== "closed"; } catch { return true; } }
export function useShellChrome() {
  const [header, setHeader] = useState(() => initial("m2o-header")), [sidebar, setSidebar] = useState(() => initial("m2o-sidebar"));
  function toggle(key: string, setter: React.Dispatch<React.SetStateAction<boolean>>) { setter(value => { const next = !value; try { localStorage.setItem(key, next ? "open" : "closed"); } catch { /* Preference remains usable for this session. */ } return next; }); }
  return { header, sidebar, toggleHeader: () => toggle("m2o-header", setHeader), toggleSidebar: () => toggle("m2o-sidebar", setSidebar) };
}
export function ChromeRegion({ id, expanded, calm, children, side = false }: { id: string; expanded: boolean; calm: boolean; children: ReactNode; side?: boolean }) {
  const root = useRef<HTMLDivElement>(null), [mounted, setMounted] = useState(expanded);
  useEffect(() => {
    const node = root.current;
    if (!expanded && node?.contains(document.activeElement)) document.getElementById("toggle-" + id)?.focus();
    if (node) node.inert = !expanded;
    if (expanded) { setMounted(true); return; }
    if (calm) { setMounted(false); return; }
    const timer = setTimeout(() => setMounted(false), 220); return () => clearTimeout(timer);
  }, [expanded, calm, id]);
  return <div id={id} ref={root} hidden={!mounted && !expanded} aria-hidden={!expanded} className={"chrome-region " + (side ? "chrome-sidebar" : "chrome-header")} data-expanded={expanded}><div className="chrome-inner">{children}</div></div>;
}
export function ChromeControls({ header, sidebar, toggleHeader, toggleSidebar }: ReturnType<typeof useShellChrome>) {
  return <nav className="shell-controls" aria-label="Workspace layout"><button id="toggle-workspace-sidebar" type="button" aria-controls="workspace-sidebar" aria-expanded={sidebar} onClick={toggleSidebar}><span aria-hidden="true">☷</span>{sidebar ? "Hide sidebar" : "Show sidebar"}</button><button id="toggle-workspace-header" type="button" aria-controls="workspace-header" aria-expanded={header} onClick={toggleHeader}><span aria-hidden="true">◒</span>{header ? "Hide header" : "Show header"}</button></nav>;
}
