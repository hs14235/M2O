// Reads design tokens from the stylesheet text (import "./theme.css?raw"), so the
// contrast test and the style guide check the values the app actually ships.

function withoutComments(css: string) {
  return css.replace(/\/\*[\s\S]*?\*\//g, "");
}

/** The hex colour tokens declared in one rule, e.g. block(css, ":root"). */
export function block(css: string, selector: string): Record<string, string> {
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

/** Light colours, and dark as declared for an explicit choice and for the system setting. */
export function themes(css: string) {
  return {
    light: block(css, ":root"),
    dark: block(css, ':root[data-theme="dark"]'),
    systemDark: block(css, ':root:not([data-theme="light"])'),
  };
}

/**
 * Every custom property the stylesheet declares, whatever its value, in source
 * order. The `@theme inline` block is left out: it only maps tokens onto
 * Tailwind's names (--color-bg: var(--bg)); see tailwindAliases.
 */
export function allTokens(css: string): string[] {
  const text = withoutComments(css).replace(/@theme inline\s*\{[^}]*\}/g, "");
  return [...new Set([...text.matchAll(/--([\w-]+)\s*:/g)].map((match) => match[1]))];
}

/** The first value declared for a token, as written (the light value for colours). */
export function tokenValue(css: string, name: string): string | undefined {
  return new RegExp("--" + name + ":\\s*([^;]+);").exec(withoutComments(css))?.[1].trim();
}

/** The Tailwind theme names and the token each one reads, from `@theme inline`. */
export function tailwindAliases(css: string): Record<string, string> {
  const body = /@theme inline\s*\{([^}]*)\}/.exec(withoutComments(css))?.[1] ?? "";
  return Object.fromEntries(
    [...body.matchAll(/--([\w-]+):\s*var\(--([\w-]+)\)\s*;/g)].map((match) => [match[1], match[2]]),
  );
}

export function luminance(hex: string) {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
export function contrast(a: string, b: string) {
  const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (high + 0.05) / (low + 0.05);
}

const backgrounds = ["bg", "surface", "surface-2", "hover"];
/** Foreground, background and the WCAG minimum ratio each pairing must meet. */
export const pairs: [string, string, number][] = [
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
