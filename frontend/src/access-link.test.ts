import { afterEach, expect, it } from "vitest";
import { accessToken, captureAccessLink, clearCapturedAccessLink } from "./access-link";

afterEach(() => { clearCapturedAccessLink(); window.history.replaceState({}, "", "/"); });
it("removes a private fragment before requests and preserves it through initial StrictMode reads", () => {
  const token = "a".repeat(43);
  window.history.replaceState({}, "", "/invite#token=" + token);
  expect(captureAccessLink()).toEqual({ path: "/invite", token });
  expect(window.location.hash).toBe("");
  expect(captureAccessLink()).toEqual({ path: "/invite", token });
  clearCapturedAccessLink(); expect(captureAccessLink()).toBeNull();
  expect(localStorage.getItem("token")).toBeNull();
});
it("accepts tokens or same-installation fragment links and rejects another origin", () => {
  expect(accessToken(window.location.origin + "/recover#token=synthetic", "/recover")).toBe("synthetic");
  expect(accessToken("  synthetic  ", "/invite")).toBe("synthetic");
  expect(() => accessToken("https://elsewhere.example/invite#token=synthetic", "/invite")).toThrow("this installation");
});
