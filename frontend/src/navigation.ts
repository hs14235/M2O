import { useCallback, useEffect, useRef, useState } from "react";

export const steps = ["transcript", "people", "review", "share", "calendar"] as const;
export const meetingStages = ["transcript", "people", "review", "calendar"] as const;
export type Step = typeof steps[number];
export type Page = "meetings" | "directory" | "integrations" | "access" | "plan" | "privacy" | "settings" | "audit";
export const settingsSections = ["people", "connections", "privacy", "access", "motion"] as const;
export type SettingsSection = typeof settingsSections[number];
export const handoffStages = ["choose", "configure", "preview", "receipt"] as const;
export type HandoffStage = typeof handoffStages[number];
export type ProviderId = "local" | "github" | "jira" | "slack" | "linkedin";
export interface Route { workspace: string; page: Page; meeting: string | null; step: Step; valid: boolean; handoff?: HandoffStage; provider?: ProviderId; section?: SettingsSection; outcome?: string }

export function parseRoute(path: string): Route {
  const fallback: Route = { workspace: "", page: "meetings", meeting: null, step: "transcript", valid: path === "/" };
  try {
    const [pathname, search = ""] = path.split("?");
    const parts = pathname.split("/").filter(Boolean).map(decodeURIComponent);
    if (parts[0] !== "workspaces" || !parts[1]) return fallback;
    const page = parts[2] as Page;
    if (!["meetings", "directory", "integrations", "access", "plan", "privacy", "settings", "audit"].includes(page)) return fallback;
    if (page === "settings") {
      const section = (parts[3] || "people") as SettingsSection;
      return parts.length <= 4 && settingsSections.includes(section) ? { workspace: parts[1], page, meeting: null, step: "transcript", section, valid: true } : fallback;
    }
    const meeting = parts[3] || null, step = (parts[4] || "transcript") as Step;
    if (parts.length > 5 || !steps.includes(step) || (page !== "meetings" && parts.length !== 3)) return fallback;
    const route: Route = { workspace: parts[1], page, meeting, step, valid: true };
    if (page === "meetings" && meeting && step === "review" && search) {
      const id = new URLSearchParams(search).get("outcome"); if (id && /^[A-Za-z0-9_-]{1,128}$/.test(id)) route.outcome = id;
    }
    if (page === "meetings" && meeting && step === "share" && search) {
      const query = new URLSearchParams(search), stage = query.get("handoff") as HandoffStage, provider = query.get("provider") as ProviderId;
      if (handoffStages.includes(stage)) route.handoff = stage;
      if (["local", "github", "jira", "slack", "linkedin"].includes(provider)) route.provider = provider;
    }
    return route;
  } catch { return fallback; }
}
export function settingsPath(workspace: string, section: SettingsSection = "people") { return routePath(workspace, "settings") + "/" + section; }
export function settingsSection(route: Route): SettingsSection | null {
  return route.page === "settings" ? route.section || "people" : ({ directory: "people", integrations: "connections", privacy: "privacy", access: "access" } as Partial<Record<Page, SettingsSection>>)[route.page] || null;
}
export function primaryPage(route: Route) { return settingsSection(route) ? "settings" : route.page === "audit" ? "audit" : route.page === "plan" ? "plan" : "meetings"; }

export function sharePath(workspace: string, meeting: string, handoff: HandoffStage, provider: ProviderId) {
  return routePath(workspace, "meetings", meeting, "share") + "?" + new URLSearchParams({ handoff, provider }).toString();
}

export function routePath(workspace: string, page: Page = "meetings", meeting?: string | null, step: Step = "transcript") {
  return "/workspaces/" + encodeURIComponent(workspace) + "/" + page + (page === "meetings" && meeting ? "/" + encodeURIComponent(meeting) + "/" + step : "");
}

// Keep a position in our own history entries so a rejected Back/Forward action
// can return to the original entry without adding duplicate entries.
export function useNavigation(mayLeave: () => boolean) {
  const guard = useRef(mayLeave); guard.current = mayLeave;
  const [path, setPath] = useState(window.location.pathname + window.location.search);
  const position = useRef(Number(window.history.state?.mttPosition || 0)), reverting = useRef(false);
  useEffect(() => {
    window.history.replaceState({ ...window.history.state, mttPosition: position.current }, "");
    const pop = () => {
      const next = Number(window.history.state?.mttPosition || 0);
      if (reverting.current) { reverting.current = false; return; }
      if (!guard.current()) {
        const distance = position.current - next;
        if (distance) { reverting.current = true; window.history.go(distance); }
        else window.history.replaceState({ ...window.history.state, mttPosition: position.current }, "", path);
        return;
      }
      position.current = next; setPath(window.location.pathname + window.location.search);
    };
    window.addEventListener("popstate", pop);
    return () => window.removeEventListener("popstate", pop);
  }, [path]);
  const navigate = useCallback((destination: string, replace = false) => {
    if (destination === window.location.pathname + window.location.search || !guard.current()) return;
    position.current += replace ? 0 : 1;
    window.history[replace ? "replaceState" : "pushState"]({ ...window.history.state, mttPosition: position.current }, "", destination);
    setPath(destination);
  }, []);
  return { route: parseRoute(path), path, navigate };
}
