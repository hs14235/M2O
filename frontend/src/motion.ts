import { useEffect, useState, type CSSProperties } from "react";

// A step's entrance: three section staggers, then the last group's reveal
// (3 × --stagger-section + --dur-reveal in motion.css), with a frame to spare.
const stepEntrance = 3 * 140 + 320 + 20;

/**
 * Classes for a step screen that reveals its children in reading order when it
 * first appears. Once that is over, .step-entered drops the delays, so content
 * added later (notices, results) reveals at once instead of waiting its turn.
 * Only the delay changes, so finished entrances do not play again.
 */
export function useStepReveal(): string {
  const [entered, setEntered] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setEntered(true), stepEntrance);
    return () => clearTimeout(timer);
  }, []);
  return "reveal-seq step-reveal" + (entered ? " step-entered" : "");
}

/** Position of an element in a .reveal-seq or .stagger group, for delays past the CSS defaults. */
export function stagger(index: number): CSSProperties {
  return { "--i": index } as CSSProperties;
}

/** True unless calm mode or the system reduced-motion setting turned motion off. */
export function prefersMotion(): boolean {
  if (document.documentElement.dataset.motion === "calm") return false;
  return !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}
