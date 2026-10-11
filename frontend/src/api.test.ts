import { afterEach, expect, it, vi } from "vitest";
import { api, ApiError } from "./api";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
it("announces lost authenticated authority while preserving the API rejection", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: "Session has ended" }), { status: 401 })),
  );
  const event = vi.spyOn(window, "dispatchEvent");
  await expect(api("/workspaces/synthetic/plan")).rejects.toBeInstanceOf(ApiError);
  expect(event).toHaveBeenCalledWith(expect.objectContaining({ type: "m2o:session-expired" }));
});
it("does not treat rejected sign-in credentials as expiry of an existing authenticated session", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ error: "Invalid credentials" }), { status: 401 })),
  );
  const event = vi.spyOn(window, "dispatchEvent");
  await expect(
    api("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email: "synthetic@example.test", password: "Synthetic-test-value" }),
    }),
  ).rejects.toThrow("Invalid credentials");
  expect(event).not.toHaveBeenCalled();
});

it("normalizes unreachable reads without exposing raw browser error details", async () => {
  const fetch = vi.fn().mockRejectedValue(new TypeError("Private URL canary"));
  vi.stubGlobal("fetch", fetch);
  await expect(api("/workspaces/synthetic/plan")).rejects.toThrow("The service could not be reached");
  expect(fetch).toHaveBeenCalledOnce();
});

it("marks an interrupted write as needing inspection and never resubmits it", async () => {
  const fetch = vi.fn().mockRejectedValue(new TypeError("Private request canary"));
  vi.stubGlobal("fetch", fetch);
  await expect(api("/workspaces/synthetic/index", { method: "POST", body: "{}" })).rejects.toThrow(
    "This change may have been received",
  );
  expect(fetch).toHaveBeenCalledOnce();
});

it("preserves cancellation rather than turning it into a network error", async () => {
  const error = new DOMException("Cancelled", "AbortError");
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(error));
  await expect(api("/workspaces/synthetic/plan")).rejects.toBe(error);
});

it("does not return a successful empty snapshot for an unreadable accepted response", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(
        new Response("Gateway canary", { status: 202, headers: { "X-Request-ID": "safe-request" } }),
      ),
  );
  await expect(api("/workspaces/synthetic/index", { method: "POST", body: "{}" })).rejects.toMatchObject({
    status: 202,
    requestId: "safe-request",
    message: expect.stringContaining("acknowledged"),
  });
});

it("uses a safe fallback and header request ID for a non-JSON service failure", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response("<html>Private gateway canary</html>", {
        status: 503,
        headers: { "X-Request-ID": "safe-request" },
      }),
    ),
  );
  await expect(api("/workspaces/synthetic/plan")).rejects.toMatchObject({
    status: 503,
    requestId: "safe-request",
    message: "The service is temporarily unavailable. Try loading again later.",
  });
});

it("accepts an explicit no-content acknowledgement", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
  await expect(api("/auth/logout", { method: "POST" })).resolves.toBeUndefined();
});

it("announces expiry even when the rejection body is not JSON", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("Private gateway canary", { status: 401 })));
  const event = vi.spyOn(window, "dispatchEvent");
  await expect(api("/workspaces/synthetic/plan")).rejects.toBeInstanceOf(ApiError);
  expect(event).toHaveBeenCalledWith(expect.objectContaining({ type: "m2o:session-expired" }));
});
