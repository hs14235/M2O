import { describe, expect, it, vi } from "vitest";
import { buildCommands, filterCommands, type CommandContext } from "./commands";
import { departmentTarget } from "./components/DepartmentExperience";
import type { Role, User, Workspace } from "./types";

const member: User = {
  id: "u1",
  name: "Avery",
  email: "avery@example.test",
  capabilities: {
    demo_mode: false,
    linkedin_configured: false,
    ollama_model: null,
    embedding_provider: "hash",
    allowed_repos: [],
  },
  linkedin: { connected: false, profile: null },
};
const spaces: Workspace[] = [
  { id: "eng", name: "Platform", department: "engineering", role: "owner" },
  { id: "eng-2", name: "Mobile", department: "engineering", role: "editor" },
  { id: "people", name: "People team", department: "hr", role: "viewer" },
];

function context(overrides: Partial<CommandContext> = {}): CommandContext {
  return {
    user: member,
    workspace: spaces[0],
    workspaces: spaces,
    motion: { calm: false, reduced: false, toggle: vi.fn() },
    navigate: vi.fn(),
    chooseTheme: vi.fn(),
    openHelp: vi.fn(),
    ...overrides,
  };
}
const withRole = (role: Role) => ({ ...spaces[0], role });
const labels = (overrides: Partial<CommandContext> = {}) =>
  buildCommands(context(overrides)).map((c) => c.label);

describe("filterCommands", () => {
  const commands = buildCommands(context());
  it("returns every command for an empty or blank query", () => {
    expect(filterCommands(commands, "")).toHaveLength(commands.length);
    expect(filterCommands(commands, "   ")).toHaveLength(commands.length);
  });
  it("matches labels case-insensitively", () => {
    expect(filterCommands(commands, "MEETINGS").map((c) => c.label)).toContain("Meetings");
  });
  it("matches keywords and requires every word", () => {
    expect(filterCommands(commands, "history").map((c) => c.label)).toEqual(["Audit"]);
    expect(filterCommands(commands, "theme dark").map((c) => c.label)).toEqual(["Theme: Dark"]);
    expect(filterCommands(commands, "no such command")).toEqual([]);
  });
});

describe("buildCommands permissions", () => {
  it("offers Audit only to owners and reviewers", () => {
    expect(labels({ workspace: withRole("owner") })).toContain("Audit");
    expect(labels({ workspace: withRole("reviewer") })).toContain("Audit");
    expect(labels({ workspace: withRole("editor") })).not.toContain("Audit");
    expect(labels({ workspace: withRole("viewer") })).not.toContain("Audit");
  });
  it("offers New meeting to editors but not to viewers or demo visitors", () => {
    expect(labels({ workspace: withRole("editor") })).toContain("New meeting");
    expect(labels({ workspace: withRole("viewer") })).not.toContain("New meeting");
    expect(labels({ user: { ...member, is_visitor: true } })).not.toContain("New meeting");
  });
  it("limits demo visitors to the settings sections the page shows them", () => {
    const visitor = labels({ user: { ...member, is_visitor: true } }).filter((l) =>
      l.startsWith("Settings:"),
    );
    expect(visitor).toEqual(["Settings: People", "Settings: Connections", "Settings: Motion & layout"]);
    expect(labels().filter((l) => l.startsWith("Settings:"))).toHaveLength(5);
  });
  it("hides the calm toggle when the system already reduces motion", () => {
    expect(labels()).toContain("Turn calm mode on");
    expect(labels({ motion: { calm: true, reduced: false, toggle: vi.fn() } })).toContain(
      "Turn calm mode off",
    );
    const reduced = labels({ motion: { calm: true, reduced: true, toggle: vi.fn() } });
    expect(reduced.some((l) => l.includes("calm"))).toBe(false);
  });
  it("leaves out page commands when no workspace is open", () => {
    const none = labels({ workspace: undefined });
    expect(none).not.toContain("Meetings");
    expect(none).toContain("Theme: Light");
  });
});

describe("navigation and actions", () => {
  it("navigates to the page path and runs non-navigation actions", () => {
    const ctx = context();
    const commands = buildCommands(ctx);
    commands.find((c) => c.label === "Meetings")!.run();
    expect(ctx.navigate).toHaveBeenCalledWith("/workspaces/eng/meetings");
    commands.find((c) => c.label === "New meeting")!.run();
    expect(ctx.navigate).toHaveBeenCalledWith("/workspaces/eng/meetings/new/transcript");
    commands.find((c) => c.label === "Settings: Privacy & data")!.run();
    expect(ctx.navigate).toHaveBeenCalledWith("/workspaces/eng/settings/privacy");
    commands.find((c) => c.label === "Theme: Dark")!.run();
    expect(ctx.chooseTheme).toHaveBeenCalledWith("dark");
    commands.find((c) => c.label === "Keyboard shortcuts")!.run();
    expect(ctx.openHelp).toHaveBeenCalled();
  });
  it("lists each other workspace once: by department where it is the department's target, else by name", () => {
    const switches = labels().filter((l) => l.startsWith("Switch"));
    expect(switches).toEqual(["Switch department: People Operations", "Switch workspace: Mobile"]);
    // The department entry is still found by the workspace's name.
    expect(filterCommands(buildCommands(context()), "people team").map((c) => c.label)).toEqual([
      "Switch department: People Operations",
    ]);
  });
  it("never offers two commands with the same destination", () => {
    for (const ctx of [context(), context({ workspace: spaces[2] }), context({ workspace: undefined })]) {
      const paths: string[] = [];
      for (const command of buildCommands(ctx).filter((c) => c.navigates)) {
        (ctx.navigate as ReturnType<typeof vi.fn>).mockClear();
        command.run();
        paths.push(String((ctx.navigate as ReturnType<typeof vi.fn>).mock.calls[0][0]));
      }
      expect(new Set(paths).size).toBe(paths.length);
    }
  });
  it("uses the sidebar's department rule: active workspace if it matches, else the first", () => {
    expect(departmentTarget(spaces, spaces[1], "engineering")?.id).toBe("eng-2");
    expect(departmentTarget(spaces, spaces[2], "engineering")?.id).toBe("eng");
    expect(departmentTarget(spaces, spaces[0], "finance")).toBeUndefined();
    const departments = labels().filter((l) => l.startsWith("Switch department:"));
    expect(departments).toEqual(["Switch department: People Operations"]);
  });
});
