import type { CSSProperties } from "react";

/** Position of an element in a .reveal-seq or .stagger group, for delays past the CSS defaults. */
export function stagger(index: number): CSSProperties {
  return { "--i": index } as CSSProperties;
}

/** True unless calm mode or the system reduced-motion setting turned motion off. */
export function prefersMotion(): boolean {
  if (document.documentElement.dataset.motion === "calm") return false;
  return !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}
