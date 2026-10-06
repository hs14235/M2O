import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it } from "vitest";
import { ChromeControls, ChromeRegion, useShellChrome } from "./ShellChrome";

beforeEach(() => { localStorage.removeItem("m2o-header"); localStorage.removeItem("m2o-sidebar"); });
function Shell() { const chrome = useShellChrome(); return <><ChromeControls {...chrome} /><ChromeRegion id="workspace-header" expanded={chrome.header} calm><button>Account action</button></ChromeRegion><ChromeRegion id="workspace-sidebar" expanded={chrome.sidebar} calm side><a href="/meetings">Meetings</a></ChromeRegion></>; }
it("keeps reopening controls available when both regions are collapsed and persists the preference", async () => {
  const view = render(<Shell />);
  await userEvent.click(screen.getByRole("button", { name: "Hide sidebar" }));
  await userEvent.click(screen.getByRole("button", { name: "Hide header" }));
  expect(screen.queryByRole("button", { name: "Account action" })).toBeNull();
  expect(screen.queryByRole("link", { name: "Meetings" })).toBeNull();
  expect(screen.getByRole("button", { name: "Show header" })).toHaveAttribute("aria-expanded", "false");
  view.unmount(); render(<Shell />);
  expect(screen.getByRole("button", { name: "Show sidebar" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Show header" }));
  expect(screen.getByRole("button", { name: "Account action" })).toBeInTheDocument();
});
it("restores focus to its reopening control when a focused region closes", async () => {
  const view = render(<><button id="toggle-workspace-header">Show header</button><ChromeRegion id="workspace-header" expanded calm><button>Account action</button></ChromeRegion></>);
  act(() => screen.getByRole("button", { name: "Account action" }).focus());
  view.rerender(<><button id="toggle-workspace-header">Show header</button><ChromeRegion id="workspace-header" expanded={false} calm><button>Account action</button></ChromeRegion></>);
  await waitFor(() => expect(screen.getByRole("button", { name: "Show header" })).toHaveFocus());
  expect(document.getElementById("workspace-header")).toHaveAttribute("aria-hidden", "true");
  expect(screen.queryByRole("button", { name: "Account action" })).toBeNull();
});
