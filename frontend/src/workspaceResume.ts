// Where each workspace was left, so switching back resumes that page and step.
// Per account and per browser; paths hold only IDs. Storage can be missing or throw
// (private windows, blocked site data), in which case switching opens the home page.
const key = (user: string) => "m2o-resume:" + user;

function read(user: string): Record<string, string> {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(key(user)) || "{}");
    return value && typeof value === "object" ? (value as Record<string, string>) : {};
  } catch {
    return {};
  }
}

/** Records the page open in a workspace; anything outside that workspace is ignored. */
export function rememberPath(user: string, workspace: string, path: string) {
  if (!path.startsWith("/workspaces/" + workspace)) return;
  try {
    localStorage.setItem(key(user), JSON.stringify({ ...read(user), [workspace]: path }));
  } catch {
    /* Without storage, switching simply opens the workspace home. */
  }
}

/** The page last open in a workspace, if any. */
export function resumePath(user: string, workspace: string): string | null {
  const path = read(user)[workspace];
  return typeof path === "string" && path.startsWith("/workspaces/" + workspace) ? path : null;
}
