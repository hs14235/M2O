import { useEffect, useId, useRef, useState } from "react";

export interface ContextAction { id: string; label: string; detail?: string; run: () => void; disabled?: boolean }

/** Secondary page tools. Primary saves and approvals stay in the main workflow. */
export function ContextBubble({ label, hint, actions }: { label: string; hint: string; actions: ContextAction[] }) {
  const id = useId(), root = useRef<HTMLDivElement>(null), trigger = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const pinned = useRef(false), suppressHover = useRef(false), timer = useRef<ReturnType<typeof setTimeout>>();
  const stopTimer = () => { clearTimeout(timer.current); };
  const close = (restoreFocus = false) => {
    stopTimer(); pinned.current = false; setOpen(false);
    if (restoreFocus) trigger.current?.focus();
  };
  useEffect(() => {
    if (!open) return;
    const escape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      const inside = Boolean(root.current?.contains(document.activeElement));
      suppressHover.current = true; close(inside);
      if (inside) event.preventDefault();
    };
    const outside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) close(); };
    document.addEventListener("keydown", escape); document.addEventListener("pointerdown", outside);
    return () => { document.removeEventListener("keydown", escape); document.removeEventListener("pointerdown", outside); };
  }, [open]);
  useEffect(() => () => stopTimer(), []);
  if (!actions.length) return null;
  return <div ref={root} className="context-bubble" data-open={open} onPointerEnter={event => {
    stopTimer();
    if (event.pointerType === "mouse" && !suppressHover.current && window.matchMedia?.("(hover: hover) and (pointer: fine)").matches) setOpen(true);
  }} onPointerLeave={() => {
    suppressHover.current = false;
    if (!pinned.current && !root.current?.contains(document.activeElement)) timer.current = setTimeout(() => close(), 220);
  }} onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) close(); }}>
    <button ref={trigger} type="button" className="bubble-trigger" aria-expanded={open} aria-controls={id} onClick={() => {
      if (open && pinned.current) close(); else { stopTimer(); pinned.current = true; setOpen(true); }
    }} onKeyDown={event => {
      if (event.key !== "ArrowDown") return;
      event.preventDefault(); pinned.current = true; setOpen(true);
      requestAnimationFrame(() => root.current?.querySelector<HTMLButtonElement>(".bubble-options button:not(:disabled)")?.focus());
    }}><span className="bubble-glyph" aria-hidden="true"><i /><i /><i /></span><span>{label}</span></button>
    <div id={id} hidden={!open} className="bubble-panel">
      <p className="eyebrow">{label}</p><p className="bubble-hint">{hint}</p>
      <nav className="bubble-options" aria-label={label}>{actions.map(action => <button type="button" key={action.id} disabled={action.disabled} onClick={() => { close(); action.run(); }}><strong>{action.label}</strong>{action.detail && <span>{action.detail}</span>}<span className="bubble-arrow" aria-hidden="true">↗</span></button>)}</nav>
      <button type="button" className="quiet bubble-close" onClick={() => { suppressHover.current = true; close(true); }}>Close tools</button>
    </div>
  </div>;
}
