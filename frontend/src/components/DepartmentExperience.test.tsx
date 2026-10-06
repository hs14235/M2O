import { act, render, renderHook, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { DepartmentSwitch, useMotionPreference } from "./DepartmentExperience";
import type { Workspace } from "../types";

const spaces: Workspace[] = [{ id: "people", department: "hr", name: "People", role: "owner" }, { id: "engineering", department: "engineering", name: "Engineering", role: "editor" }];
beforeEach(() => { localStorage.clear(); vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }))); });
afterEach(() => vi.unstubAllGlobals());

it("only switches to accessible department workspaces", async () => {
  const change = vi.fn(); render(<DepartmentSwitch workspaces={spaces} active={spaces[0]} onChange={change} />);
  expect(screen.getByRole("button", { name: "People Operations" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByRole("button", { name: "Finance Control" })).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "Engineering" }));
  expect(change).toHaveBeenCalledWith("engineering");
});

it("persists calm mode and respects the system reduced-motion preference", () => {
  const hook = renderHook(useMotionPreference);
  act(() => hook.result.current.toggle());
  expect(hook.result.current.calm).toBe(true);
  expect(localStorage.getItem("m2o-calm")).toBe("true");
  expect(document.documentElement.dataset.motion).toBe("calm");
  hook.unmount();
  localStorage.clear();
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
  const reduced = renderHook(useMotionPreference);
  expect(reduced.result.current.calm).toBe(true);
  expect(reduced.result.current.reduced).toBe(true);
});
