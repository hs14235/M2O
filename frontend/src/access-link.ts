export type AccessPath = "/invite" | "/recover";
export interface AccessLink { path: AccessPath; token: string }
let captured: AccessLink | null = null;

/** Retain a fragment only through React's initial render, then clear this cache. */
export function captureAccessLink(): AccessLink | null {
  const path = window.location.pathname;
  if (path !== "/invite" && path !== "/recover") return null;
  const token = new URLSearchParams(window.location.hash.slice(1)).get("token");
  if (token) {
    captured = { path, token };
    window.history.replaceState(window.history.state, "", path + window.location.search);
  }
  return captured?.path === path ? captured : null;
}
export function clearCapturedAccessLink() { captured = null; }
export function accessToken(value: string, path: AccessPath) {
  const trimmed = value.trim();
  if (!trimmed.includes("://")) return trimmed;
  const url = new URL(trimmed);
  if (url.origin !== window.location.origin || url.pathname !== path) throw new Error("Use a private M2O link from this installation.");
  return new URLSearchParams(url.hash.slice(1)).get("token") || "";
}
