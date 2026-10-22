import { afterEach, expect, it, vi } from "vitest";
import { rememberPath, resumePath } from "./workspaceResume";

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

it("resumes each workspace's last page, per account", () => {
  rememberPath("u1", "w1", "/workspaces/w1/meetings/m1/review");
  rememberPath("u1", "w2", "/workspaces/w2/plan");
  expect(resumePath("u1", "w1")).toBe("/workspaces/w1/meetings/m1/review");
  expect(resumePath("u1", "w2")).toBe("/workspaces/w2/plan");
  expect(resumePath("u2", "w1")).toBeNull();
});

it("ignores paths from another workspace and survives missing storage", () => {
  rememberPath("u1", "w1", "/workspaces/w2/plan");
  expect(resumePath("u1", "w1")).toBeNull();
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  expect(() => rememberPath("u1", "w1", "/workspaces/w1/plan")).not.toThrow();
  expect(resumePath("u1", "w1")).toBeNull();
});
