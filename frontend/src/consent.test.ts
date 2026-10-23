import { afterEach, expect, it, vi } from "vitest";
import { openConsent } from "./consent";

afterEach(() => vi.restoreAllMocks());

function fakeTab() {
  return { closed: false, opener: {} as unknown, location: { href: "about:blank" }, close: vi.fn() };
}

it("opens consent in a new tab with its opener cleared", async () => {
  const tab = fakeTab();
  const open = vi.spyOn(window, "open").mockReturnValue(tab as unknown as Window);
  await openConsent(async () => "https://auth.example.test/consent");
  expect(open).toHaveBeenCalledWith("about:blank", "_blank");
  expect(tab.location.href).toBe("https://auth.example.test/consent");
  expect(tab.opener).toBeNull();
});

it("closes the tab when the link cannot be prepared", async () => {
  const tab = fakeTab();
  vi.spyOn(window, "open").mockReturnValue(tab as unknown as Window);
  await expect(
    openConsent(async () => {
      throw new Error("Credential storage unavailable");
    }),
  ).rejects.toThrow("Credential storage unavailable");
  expect(tab.close).toHaveBeenCalled();
});

it("falls back to this tab when new tabs are blocked", async () => {
  const assign = vi.fn();
  vi.spyOn(window, "open").mockReturnValue(null);
  vi.spyOn(window, "location", "get").mockReturnValue({ ...window.location, assign });
  await openConsent(async () => "https://auth.example.test/consent");
  expect(assign).toHaveBeenCalledWith("https://auth.example.test/consent");
});
