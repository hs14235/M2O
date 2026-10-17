import { departmentExperience, departmentTarget } from "./components/DepartmentExperience";
import type { ThemeChoice } from "./components/ThemeSwitch";
import { canAudit, routePath, settingsLabels, settingsPath, visibleSettingsSections } from "./navigation";
import type { Department, User, Workspace } from "./types";

export type CommandGroup = "Go to" | "Workspace" | "Create" | "Appearance" | "Help";
export interface Command {
  id: string;
  group: CommandGroup;
  label: string;
  keywords: string[];
  /** Commands that change the page let the new page take focus when the menu closes. */
  navigates: boolean;
  run: () => void;
}
export interface CommandContext {
  user: User;
  workspace?: Workspace;
  workspaces: Workspace[];
  motion: { calm: boolean; reduced: boolean; toggle: () => void };
  navigate: (path: string) => void;
  chooseTheme: (choice: ThemeChoice) => void;
  openHelp: () => void;
}

/**
 * Every command the current person may run, built from the same permission rules as
 * the visible UI. A command the UI would disable is left out rather than shown disabled.
 */
export function buildCommands(context: CommandContext): Command[] {
  const { user, workspace, workspaces, motion, navigate } = context;
  const commands: Command[] = [];
  const go = (id: string, group: CommandGroup, label: string, path: string, keywords: string[] = []) =>
    commands.push({ id, group, label, keywords, navigates: true, run: () => navigate(path) });
  if (workspace) {
    go("go-plan", "Go to", "My day", routePath(workspace.id, "plan"), ["plan", "today", "personal"]);
    go("go-meetings", "Go to", "Meetings", routePath(workspace.id), ["home", "list", "transcripts"]);
    if (canAudit(workspace))
      go("go-audit", "Go to", "Audit", routePath(workspace.id, "audit"), ["history", "events", "log"]);
    for (const section of visibleSettingsSections(user))
      go(
        "settings-" + section,
        "Go to",
        "Settings: " + settingsLabels[section],
        settingsPath(workspace.id, section),
        ["settings", "preferences", section],
      );
    if (workspace.role !== "viewer" && !user.is_visitor)
      go("new-meeting", "Create", "New meeting", routePath(workspace.id, "meetings", "new", "transcript"), [
        "create",
        "transcript",
        "add",
      ]);
  }
  // One entry per destination: other departments go to the workspace the sidebar's
  // department switch would; any remaining workspaces are listed by name.
  const targets = new Set<string>();
  for (const department of Object.keys(departmentExperience) as Department[]) {
    if (department === workspace?.department) continue;
    const target = departmentTarget(workspaces, workspace, department);
    if (!target) continue;
    targets.add(target.id);
    go(
      "department-" + department,
      "Workspace",
      "Switch department: " + departmentExperience[department].name,
      routePath(target.id),
      ["department", "workspace", department, target.name],
    );
  }
  for (const value of workspaces)
    if (value.id !== workspace?.id && !targets.has(value.id))
      go("workspace-" + value.id, "Workspace", "Switch workspace: " + value.name, routePath(value.id), [
        "workspace",
      ]);
  for (const [choice, name] of [
    ["system", "System"],
    ["light", "Light"],
    ["dark", "Dark"],
  ] as const)
    commands.push({
      id: "theme-" + choice,
      group: "Appearance",
      label: "Theme: " + name,
      keywords: ["theme", "appearance", "color", "mode"],
      navigates: false,
      run: () => context.chooseTheme(choice),
    });
  // The system reduced-motion setting already keeps motion off, so there is nothing to toggle.
  if (!motion.reduced)
    commands.push({
      id: "calm",
      group: "Appearance",
      label: motion.calm ? "Turn calm mode off" : "Turn calm mode on",
      keywords: ["calm", "motion", "animation", "reduce"],
      navigates: false,
      run: motion.toggle,
    });
  commands.push({
    id: "help",
    group: "Help",
    label: "Keyboard shortcuts",
    keywords: ["help", "keys", "hotkeys", "?"],
    navigates: false,
    run: context.openHelp,
  });
  return commands;
}

/** Case-insensitive match: every word of the query must appear in the label or keywords. */
export function filterCommands(commands: Command[], query: string) {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return commands;
  return commands.filter((command) => {
    const text = [command.label, ...command.keywords].join(" ").toLowerCase();
    return words.every((word) => text.includes(word));
  });
}
