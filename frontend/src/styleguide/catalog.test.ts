import { expect, it } from "vitest";
import themeCss from "../theme.css?raw";
import motionCss from "../motion.css?raw";
import { allTokens, tailwindAliases } from "../design-tokens";
import { catalog } from "./catalog";

const declared = [...new Set([...allTokens(themeCss), ...allTokens(motionCss)])];

it("documents every token the stylesheets declare, and only those", () => {
  expect(declared.filter((name) => !(name in catalog))).toEqual([]);
  expect(Object.keys(catalog).filter((name) => !declared.includes(name))).toEqual([]);
});

it("maps every Tailwind theme name onto a documented token", () => {
  const aliases = tailwindAliases(themeCss);
  expect(Object.keys(aliases).length).toBeGreaterThan(30);
  expect(Object.values(aliases).filter((token) => !(token in catalog))).toEqual([]);
});

it("points every deprecated alias at a current token", () => {
  for (const info of Object.values(catalog).filter((entry) => entry.group === "Deprecated aliases"))
    expect(catalog[info.replacement!]?.group).not.toBe("Deprecated aliases");
});
