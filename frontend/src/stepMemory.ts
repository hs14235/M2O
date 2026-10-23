// Unfinished choices inside a step (outcomes ticked for sharing, a person picked but not
// yet confirmed), so leaving a workspace and coming back finds them as they were. Session
// storage: this tab only, cleared when it closes, IDs only. Storage can be missing or
// throw (private windows, blocked site data); the choices then last until a reload.
const memory = new Map<string, string>();
const key = (workspace: string, name: string) => "m2o-step:" + workspace + ":" + name;

export function recall(workspace: string, name: string): unknown {
  const stored = key(workspace, name);
  let value: string | null;
  try {
    value = sessionStorage.getItem(stored);
  } catch {
    value = memory.get(stored) ?? null; // Storage unavailable: the in-memory copy stands in.
  }
  try {
    return value === null ? undefined : JSON.parse(value);
  } catch {
    return undefined;
  }
}

/** Remembers a choice; an empty or undefined value forgets it. */
export function remember(workspace: string, name: string, value: unknown) {
  const stored = key(workspace, name),
    empty = value === undefined || value === "" || (Array.isArray(value) && value.length === 0);
  if (empty) memory.delete(stored);
  else memory.set(stored, JSON.stringify(value));
  try {
    if (empty) sessionStorage.removeItem(stored);
    else sessionStorage.setItem(stored, JSON.stringify(value));
  } catch {
    /* The in-memory copy stands in. */
  }
}
