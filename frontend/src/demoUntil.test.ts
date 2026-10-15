import { expect, it } from "vitest";
import { demoUntil } from "./App";

it("shows only the time when the demo ends today, and the date when it runs past midnight", () => {
  const today = new Date(2026, 9, 15, 20, 0);
  expect(demoUntil(new Date(2026, 9, 15, 22, 30).toISOString(), today)).not.toMatch(/Oct/);
  expect(demoUntil(new Date(2026, 9, 15, 22, 30).toISOString(), today)).toMatch(/10:30/);
  expect(demoUntil(new Date(2026, 9, 16, 0, 15).toISOString(), today)).toMatch(/Oct 16/);
});
