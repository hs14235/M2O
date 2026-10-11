export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public requestId?: string,
    public kind: "http" | "network" | "invalid_response" = "http",
  ) {
    super(message);
  }
}

function requestId(value: unknown) {
  return typeof value === "string" && /^[A-Za-z0-9_-]{1,128}$/.test(value) ? value : undefined;
}
function isCancellation(error: unknown, signal?: AbortSignal | null) {
  return (
    signal?.aborted ||
    ((error instanceof Error || error instanceof DOMException) && error.name === "AbortError")
  );
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const csrf = document.cookie
    .split("; ")
    .find((value) => value.startsWith("mtt_csrf="))
    ?.slice(9);
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (csrf) headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  const reading = ["GET", "HEAD"].includes((options.method || "GET").toUpperCase());
  let response: Response;
  try {
    response = await fetch("/api" + path, { ...options, headers, credentials: "same-origin" });
  } catch (error) {
    if (isCancellation(error, options.signal)) throw error;
    throw new ApiError(
      0,
      reading
        ? "The service could not be reached. Check your connection and try loading again."
        : "The connection was interrupted. This change may have been received. Check its current status before trying again.",
      undefined,
      "network",
    );
  }
  if (response.status === 401 && path !== "/auth/login" && path !== "/me")
    window.dispatchEvent(new Event("m2o:session-expired"));
  if (response.ok && response.status === 204) return undefined as T;
  let payload;
  try {
    payload = await response.json();
  } catch (error) {
    if (isCancellation(error, options.signal)) throw error;
    if (response.ok)
      throw new ApiError(
        response.status,
        reading
          ? "The response could not be read. Try loading the current data again."
          : "The request was acknowledged, but its response could not be read. Check its current status before trying again.",
        requestId(response.headers.get("X-Request-ID")),
        "invalid_response",
      );
  }
  if (!response.ok) {
    const message =
      typeof payload?.error === "string" && payload.error
        ? payload.error
        : response.status >= 500
          ? "The service is temporarily unavailable. Try loading again later."
          : "The request failed";
    throw new ApiError(
      response.status,
      message,
      requestId(payload?.request_id) || requestId(response.headers.get("X-Request-ID")),
    );
  }
  return payload as T;
}

export function errorMessage(error: unknown) {
  return error instanceof ApiError
    ? error.message + (error.requestId ? " (request " + error.requestId + ")" : "")
    : error instanceof Error
      ? error.message
      : "Something went wrong";
}

export function scoped(workspace: string, path: string) {
  return "/workspaces/" + encodeURIComponent(workspace) + path;
}
