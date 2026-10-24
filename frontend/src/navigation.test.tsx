import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import {
  meetingStages,
  failedConnection,
  parseRoute,
  rootDestination,
  primaryPage,
  routePath,
  settingsPath,
  settingsSection,
  sharePath,
  useNavigation,
} from "./navigation";

beforeEach(() => window.history.replaceState({ mttPosition: 0 }, "", "/"));
it("exposes four meeting stages while retaining both legacy Step 3 subview addresses", () => {
  expect(meetingStages).toEqual(["transcript", "people", "review", "calendar"]);
  for (const step of ["review", "share", "calendar"] as const)
    expect(parseRoute(routePath("space", "meetings", "weekly", step))).toMatchObject({ valid: true, step });
  expect(parseRoute("/workspaces/space/meetings/weekly/review?outcome=decision")).toMatchObject({
    outcome: "decision",
  });
});
it("round trips real workspace, meeting and step URLs and rejects unknown pages", () => {
  expect(parseRoute(routePath("space", "meetings", "weekly", "review"))).toEqual({
    workspace: "space",
    page: "meetings",
    meeting: "weekly",
    step: "review",
    valid: true,
  });
  expect(parseRoute("/workspaces/space/integrations").page).toBe("integrations");
  expect(parseRoute("/workspaces/space/meetings/weekly/unknown").valid).toBe(false);
  expect(parseRoute("/workspaces/space/access/extra").valid).toBe(false);
  expect(parseRoute("/%ZZ").valid).toBe(false);
});
it("keeps staged handoffs addressable without treating query data as a path", () => {
  expect(parseRoute(sharePath("space", "weekly", "receipt", "jira"))).toMatchObject({
    valid: true,
    step: "share",
    handoff: "receipt",
    provider: "jira",
  });
  expect(parseRoute("/workspaces/space/meetings/weekly/share?handoff=unsafe&provider=unknown")).toEqual({
    workspace: "space",
    page: "meetings",
    meeting: "weekly",
    step: "share",
    valid: true,
  });
});
it("preserves the page when a dirty navigation is rejected", () => {
  const guard = vi.fn(() => false),
    hook = renderHook(() => useNavigation(guard));
  act(() => hook.result.current.navigate("/workspaces/space/meetings"));
  expect(window.location.pathname).toBe("/");
  expect(guard).toHaveBeenCalledOnce();
});
it("supports browser Back and restores the original history entry when rejected", async () => {
  const guard = vi.fn(() => true),
    hook = renderHook(() => useNavigation(guard));
  act(() => hook.result.current.navigate("/workspaces/space/meetings/weekly/transcript"));
  act(() => hook.result.current.navigate("/workspaces/space/meetings/weekly/people"));
  guard.mockReturnValue(false);
  act(() => window.history.back());
  await waitFor(() => expect(guard).toHaveBeenCalledTimes(3));
  await waitFor(() => expect(window.location.pathname).toMatch(/people$/));
  expect(hook.result.current.route.step).toBe("people");
  guard.mockReturnValue(true);
  act(() => window.history.back());
  await waitFor(() => expect(hook.result.current.route.step).toBe("transcript"));
});
it("uses browser Back and Forward between handoff stages on the same page", async () => {
  const hook = renderHook(() => useNavigation(() => true));
  act(() => hook.result.current.navigate(sharePath("space", "weekly", "configure", "jira")));
  act(() => hook.result.current.navigate(sharePath("space", "weekly", "preview", "jira")));
  act(() => window.history.back());
  await waitFor(() => expect(hook.result.current.route.handoff).toBe("configure"));
  act(() => window.history.forward());
  await waitFor(() => expect(hook.result.current.route.handoff).toBe("preview"));
  expect(hook.result.current.route.provider).toBe("jira");
});
it("addresses settings sections and keeps legacy settings URLs mapped to the same primary destination", () => {
  expect(parseRoute(settingsPath("scope", "connections"))).toMatchObject({
    page: "settings",
    section: "connections",
    valid: true,
  });
  expect(parseRoute("/workspaces/scope/settings/unknown").valid).toBe(false);
  for (const [page, section] of [
    ["directory", "people"],
    ["integrations", "connections"],
    ["privacy", "privacy"],
    ["access", "access"],
  ]) {
    const route = parseRoute("/workspaces/scope/" + page);
    expect(primaryPage(route)).toBe("settings");
    expect(settingsSection(route)).toBe(section);
  }
  expect(primaryPage(parseRoute("/workspaces/scope/audit"))).toBe("audit");
});

it("treats the site root as valid with or without a query", () => {
  // The LinkedIn profile sign-in returns to /?linkedin=connected.
  for (const path of ["/", "/?linkedin=connected", "/?linkedin=cancelled"]) {
    expect(parseRoute(path)).toMatchObject({ valid: true, workspace: "" });
  }
  expect(parseRoute("/unknown").valid).toBe(false);
});

it("sends provider sign-ins that return to the root to Connections", () => {
  expect(rootDestination("", "space")).toBe("/workspaces/space/meetings");
  expect(rootDestination("linkedin=connected", "space")).toBe("/workspaces/space/settings/connections");
  expect(rootDestination("connection_failed=slack", "space")).toBe(
    "/workspaces/space/settings/connections?connection_failed=slack",
  );
  // Unknown or built-in names are ignored rather than echoed.
  expect(rootDestination("connection_failed=toString", "space")).toBe("/workspaces/space/meetings");
  expect(failedConnection("/workspaces/space/settings/connections?connection_failed=jira")).toBe("Jira");
  expect(failedConnection("/x?connection_failed=constructor")).toBeNull();
  expect(failedConnection("/x?connection_failed=%3Cb%3E")).toBeNull();
});
