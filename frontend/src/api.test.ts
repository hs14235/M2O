import { afterEach, expect, it, vi } from "vitest";
import { api, ApiError } from "./api";

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });
it("announces lost authenticated authority while preserving the API rejection", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: "Session has ended" }), { status: 401 })));
  const event = vi.spyOn(window, "dispatchEvent");
  await expect(api("/workspaces/synthetic/plan")).rejects.toBeInstanceOf(ApiError);
  expect(event).toHaveBeenCalledWith(expect.objectContaining({ type: "m2o:session-expired" }));
});
it("does not treat rejected sign-in credentials as expiry of an existing authenticated session", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: "Invalid credentials" }), { status: 401 })));
  const event = vi.spyOn(window, "dispatchEvent");
  await expect(api("/auth/login", { method: "POST", body: JSON.stringify({ email: "synthetic@example.test", password: "Synthetic-test-value" }) })).rejects.toThrow("Invalid credentials");
  expect(event).not.toHaveBeenCalled();
});
