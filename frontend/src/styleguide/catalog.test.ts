import { expect, it } from "vitest";
import themeCss from "../theme.css?raw";
import motionCss from "../motion.css?raw";
import { allTokens, tailwindAliases, tokenValues } from "../design-tokens";
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
  for (const info of Object.values(catalog).filter((entry) => entry.group === "Deprecated aliases")) {
    expect(catalog, String(info.replacement)).toHaveProperty([info.replacement!]);
    expect(catalog[info.replacement!].group).not.toBe("Deprecated aliases");
  }
});

it("reads each token's own value for both themes, not a later or longer namesake", () => {
  const css = `:root { --x-shadow-sm: 1px; --shadow-sm: 2px; --dept: var(--a); --overlay: rgb(1 1 1); }
:root[data-theme="dark"] { --overlay: rgb(0 0 0); }
:root[data-department="hr"] { --dept: var(--b); }`;
  expect(tokenValues(css)).toMatchObject({ "shadow-sm": "2px", dept: "var(--a)", overlay: "rgb(1 1 1)" });
  expect(tokenValues(css, "dark")).toMatchObject({ "shadow-sm": "2px", overlay: "rgb(0 0 0)" });
});
