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

/**
 * Sends a small token from `from` to the first element matching `target`, so a
 * change visibly lands where it counts (an approval in the review meter, say).
 * Decorative only: it is aria-hidden, and does nothing without motion or a target.
 */
export function flyTo(from: Element | null, target: string, text = "✓") {
  const to = document.querySelector(target);
  if (!from || !to || !prefersMotion() || typeof document.body.animate !== "function") return;
  const a = from.getBoundingClientRect(),
    b = to.getBoundingClientRect();
  const token = document.createElement("span");
  token.className = "fly-token";
  token.textContent = text;
  token.setAttribute("aria-hidden", "true");
  token.style.left = a.left + a.width / 2 + "px";
  token.style.top = a.top + a.height / 2 + "px";
  document.body.append(token);
  const dx = b.left + b.width / 2 - (a.left + a.width / 2),
    dy = b.top + b.height / 2 - (a.top + a.height / 2);
  token
    .animate(
      [
        { transform: "translate(-50%, -50%) scale(1)", opacity: 1 },
        {
          transform: `translate(calc(-50% + ${dx * 0.5}px), calc(-50% + ${dy * 0.5 - 40}px)) scale(1.15)`,
          opacity: 1,
        },
        { transform: `translate(calc(-50% + ${dx}px), calc(-50% + ${dy}px)) scale(0.4)`, opacity: 0.2 },
      ],
      { duration: 620, easing: "cubic-bezier(0.2, 0.7, 0.2, 1)" },
    )
    .finished.catch(() => undefined)
    .finally(() => token.remove());
}

/** True unless calm mode or the system reduced-motion setting turned motion off. */
export function prefersMotion(): boolean {
  if (document.documentElement.dataset.motion === "calm") return false;
  return !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}
