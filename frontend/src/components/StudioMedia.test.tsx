import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { StudioMedia } from "./StudioMedia";

let observe: (entries: { isIntersecting: boolean; intersectionRatio: number }[]) => void;
beforeEach(() => {
  localStorage.removeItem("m2o-studio-paused");
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  vi.stubGlobal("IntersectionObserver", class { constructor(callback: typeof observe) { observe = callback; } observe() {} disconnect() {} });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
it("retains the static poster and attaches video only when visible with motion allowed", async () => {
  const view = render(<StudioMedia department="hr" calm={false} />);
  const video = view.container.querySelector("video")!;
  expect(video).not.toHaveAttribute("src");
  expect(view.container.querySelector("img")).toHaveAttribute("src", "/scenes/hr.webp");
  act(() => observe([{ isIntersecting: true, intersectionRatio: .8 }]));
  await waitFor(() => expect(video).toHaveAttribute("src", "/scenes/hr.mp4"));
  expect(HTMLMediaElement.prototype.play).toHaveBeenCalled();
  view.rerender(<StudioMedia department="hr" calm />);
  await waitFor(() => expect(video).not.toHaveAttribute("src"));
  expect(screen.getByText("Studio motion paused")).toBeInTheDocument();
});
it("pauses offscreen and lets the user pause without losing the presentation", async () => {
  const view = render(<StudioMedia department="engineering" calm={false} />);
  act(() => observe([{ isIntersecting: true, intersectionRatio: 1 }]));
  await waitFor(() => expect(HTMLMediaElement.prototype.play).toHaveBeenCalled());
  await userEvent.click(screen.getByRole("button", { name: "Pause studio motion" }));
  expect(screen.getByRole("button", { name: "Play studio motion" })).toHaveAttribute("aria-pressed", "true");
  expect(view.container.querySelector("img")).toBeInTheDocument();
  act(() => observe([{ isIntersecting: false, intersectionRatio: 0 }]));
  expect(HTMLMediaElement.prototype.pause).toHaveBeenCalled();
});
it("degrades to a poster if the browser rejects playback", async () => {
  vi.spyOn(HTMLMediaElement.prototype, "play").mockRejectedValue(new Error("Playback rejected"));
  const view = render(<StudioMedia department="finance" calm={false} />);
  act(() => observe([{ isIntersecting: true, intersectionRatio: 1 }]));
  expect(await screen.findByText("Static studio scene")).toBeInTheDocument();
  expect(view.container.querySelector("img")).toHaveAttribute("src", "/scenes/finance.webp");
});
it("pauses playback when the browser tab becomes hidden", async () => {
  render(<StudioMedia department="hr" calm={false} />);
  act(() => observe([{ isIntersecting: true, intersectionRatio: 1 }]));
  await waitFor(() => expect(HTMLMediaElement.prototype.play).toHaveBeenCalled());
  const pause = vi.mocked(HTMLMediaElement.prototype.pause); pause.mockClear();
  vi.spyOn(document, "hidden", "get").mockReturnValue(true);
  fireEvent(document, new Event("visibilitychange"));
  expect(pause).toHaveBeenCalled();
});
it("keeps an intentional pause after a department scene remount", async () => {
  const view = render(<StudioMedia department="hr" calm={false} />);
  act(() => observe([{ isIntersecting: true, intersectionRatio: 1 }]));
  await userEvent.click(screen.getByRole("button", { name: "Pause studio motion" }));
  view.unmount(); vi.mocked(HTMLMediaElement.prototype.play).mockClear();
  const next = render(<StudioMedia department="finance" calm={false} />);
  act(() => observe([{ isIntersecting: true, intersectionRatio: 1 }]));
  expect(screen.getByRole("button", { name: "Play studio motion" })).toBeInTheDocument();
  expect(next.container.querySelector("video")).not.toHaveAttribute("src");
  expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled();
});
it("recovers from a failed scene when the department changes", async () => {
  vi.mocked(HTMLMediaElement.prototype.play).mockRejectedValueOnce(new Error("Unavailable scene"));
  const view = render(<StudioMedia department="hr" calm={false} />);
  act(() => observe([{ isIntersecting: true, intersectionRatio: 1 }]));
  await screen.findByText("Static studio scene");
  view.rerender(<StudioMedia department="engineering" calm={false} />);
  await waitFor(() => expect(view.container.querySelector("video")).toHaveAttribute("src", "/scenes/engineering.mp4"));
  expect(screen.queryByText("Static studio scene")).toBeNull();
  expect(screen.getByRole("button", { name: "Pause studio motion" })).toBeInTheDocument();
});
