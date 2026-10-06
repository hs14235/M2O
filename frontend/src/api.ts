export class ApiError extends Error {
  constructor(public status: number, message: string, public requestId?: string) { super(message); }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const csrf = document.cookie.split("; ").find(value => value.startsWith("mtt_csrf="))?.slice(9);
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (csrf) headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  const response = await fetch("/api" + path, { ...options, headers, credentials: "same-origin" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && path !== "/auth/login" && path !== "/me") window.dispatchEvent(new Event("m2o:session-expired"));
    throw new ApiError(response.status, payload.error || "The request failed", payload.request_id);
  }
  return payload as T;
}

export function errorMessage(error: unknown) {
  return error instanceof ApiError ? error.message + (error.requestId ? " (request " + error.requestId + ")" : "") : error instanceof Error ? error.message : "Something went wrong";
}

export function scoped(workspace: string, path: string) {
  return "/workspaces/" + encodeURIComponent(workspace) + path;
}
