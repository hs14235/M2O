import { describe, expect, it } from "vitest";
import css from "./theme.css?raw";
import { contrast, pairs, themes } from "./design-tokens";

// Contrast is checked from the token values themselves, so a colour change that
// breaks WCAG fails here before any screen is rendered. vitest.config.ts lets this
// stylesheet load as text (Vitest empties CSS imports by default).

// Dark is declared twice: for the system setting and for an explicit choice.
const { light, dark, systemDark } = themes(css);

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
