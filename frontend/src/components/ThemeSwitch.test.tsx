import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it } from "vitest";
import { ThemeSwitch, savedTheme } from "./ThemeSwitch";

afterEach(() => {
  localStorage.removeItem("m2o-theme");
  delete document.documentElement.dataset.theme;
});

it("applies and remembers an explicit theme, and System clears it", async () => {
  render(<ThemeSwitch />);
  expect(screen.getByRole("radio", { name: "System" })).toHaveAttribute("aria-checked", "true");
  await userEvent.click(screen.getByRole("radio", { name: "Dark" }));
  expect(document.documentElement.dataset.theme).toBe("dark");
  expect(savedTheme()).toBe("dark");
  expect(screen.getByRole("radio", { name: "Dark" })).toHaveAttribute("aria-checked", "true");
  await userEvent.click(screen.getByRole("radio", { name: "System" }));
  expect(document.documentElement.dataset.theme).toBeUndefined();
  expect(savedTheme()).toBe("system");
});
