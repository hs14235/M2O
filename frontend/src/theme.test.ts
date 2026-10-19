import { describe, expect, it } from "vitest";
import css from "./theme.css?raw";

// Contrast is checked from the token values themselves, so a colour change that
// breaks WCAG fails here before any screen is rendered. vitest.config.ts lets this
// one stylesheet load as text (Vitest empties CSS imports by default).

function block(selector: string) {
  const start = css.indexOf(selector + " {");
  if (start < 0) throw new Error("Missing " + selector);
  const body = css.slice(css.indexOf("{", start) + 1, css.indexOf("}", start));
  return Object.fromEntries(
    [...body.matchAll(/--([\w-]+):\s*(#[0-9a-f]{6})\s*;/gi)].map((match) => [
      match[1],
      match[2].toLowerCase(),
    ]),
  );
}

const light = block(":root");
// Dark is declared twice: for the system setting and for an explicit choice.
const dark = block(':root[data-theme="dark"]');
const systemDark = block(':root:not([data-theme="light"])');

function luminance(hex: string) {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function contrast(a: string, b: string) {
  const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (high + 0.05) / (low + 0.05);
}

const backgrounds = ["bg", "surface", "surface-2", "hover"];
const pairs: [string, string, number][] = [
  ...["text", "text-2", "text-3"].flatMap((fg) =>
    backgrounds.map((bg) => [fg, bg, 4.5] as [string, string, number]),
  ),
  ["accent-fg", "accent", 4.5],
  ["accent-fg", "accent-hover", 4.5],
  ["danger-fg", "danger", 4.5],
  ["danger-fg", "danger-hover", 4.5],
  ["success", "success-soft", 4.5],
  ["accent", "surface", 4.5],
  // Form field outlines are non-text UI and need 3:1 (WCAG 1.4.11).
  ...backgrounds.map((bg) => ["border-control", bg, 3] as [string, string, number]),
];

describe("theme tokens", () => {
  it("declares the same dark values for the system setting and the explicit choice", () => {
    expect(systemDark).toEqual(dark);
  });

  for (const [name, tokens] of [
    ["light", light],
    ["dark", dark],
  ] as const) {
    it.each(pairs)(`${name}: %s on %s meets %s:1`, (fg, bg, minimum) => {
      expect(tokens[fg], fg).toBeDefined();
      expect(tokens[bg], bg).toBeDefined();
      expect(contrast(tokens[fg], tokens[bg])).toBeGreaterThanOrEqual(minimum);
    });
  }
});
