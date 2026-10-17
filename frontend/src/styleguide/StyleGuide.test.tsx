import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { catalog } from "./catalog";
import StyleGuide from "./StyleGuide";

beforeEach(() => {
  localStorage.clear();
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })),
  );
});
afterEach(() => vi.unstubAllGlobals());

it("shows every catalogued token on the page", () => {
  render(<StyleGuide />);
  for (const name of Object.keys(catalog))
    expect(screen.getAllByText("--" + name, { selector: "code" }).length, name).toBeGreaterThan(0);
});

it("reports a passing contrast result for every checked pair", () => {
  render(<StyleGuide />);
  const table = screen.getByRole("table", { name: /Contrast of the checked pairs/ });
  expect(table.querySelectorAll("tbody tr")).toHaveLength(22);
  expect(table).not.toHaveTextContent("Fail");
});

it("renders the real components without loading data", () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  render(<StyleGuide />);
  expect(screen.getAllByRole("article")).toHaveLength(5);
  expect(screen.getByRole("alert")).toHaveTextContent("(request req_123)");
  expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  expect(fetch).not.toHaveBeenCalled();
});

it("sets the department tint from the switch", async () => {
  render(<StyleGuide />);
  await userEvent.selectOptions(screen.getByLabelText("Department"), "finance");
  expect(document.documentElement.dataset.department).toBe("finance");
});
