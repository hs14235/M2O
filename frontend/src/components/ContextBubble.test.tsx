import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { ContextBubble } from "./ContextBubble";

const run = vi.fn();
const actions = [{ id: "source", label: "Review source", detail: "Keep the transcript in context", run }];
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); run.mockClear(); });
it("keeps hidden tools out of keyboard navigation, supports click, and restores focus on Escape", async () => {
  render(<ContextBubble label="Review tools" hint="Next: choose a handoff" actions={actions} />);
  const trigger = screen.getByRole("button", { name: "Review tools" });
  expect(trigger).toHaveAttribute("aria-expanded", "false");
  expect(screen.queryByRole("button", { name: /Review source/ })).toBeNull();
  await userEvent.click(trigger); await userEvent.tab();
  expect(screen.getByRole("button", { name: /Review source/ })).toHaveFocus();
  await userEvent.keyboard("{Escape}");
  expect(trigger).toHaveFocus(); expect(trigger).toHaveAttribute("aria-expanded", "false");
  expect(run).not.toHaveBeenCalled();
});
it("lets keyboard users enter the tools with ArrowDown and executes only the selected action", async () => {
  render(<ContextBubble label="Review tools" hint="Next: choose a handoff" actions={actions} />);
  screen.getByRole("button", { name: "Review tools" }).focus();
  await userEvent.keyboard("{ArrowDown}");
  await waitFor(() => expect(screen.getByRole("button", { name: /Review source/ })).toHaveFocus());
  await userEvent.keyboard("{Enter}");
  expect(run).toHaveBeenCalledOnce();
  expect(screen.queryByRole("button", { name: /Review source/ })).toBeNull();
});
it("supports touch without triggering a hover action and closes on outside interaction", async () => {
  render(<><ContextBubble label="Review tools" hint="Next" actions={actions} /><button>Outside</button></>);
  const trigger = screen.getByRole("button", { name: "Review tools" });
  fireEvent.pointerEnter(trigger, { pointerType: "touch" });
  expect(trigger).toHaveAttribute("aria-expanded", "false");
  await userEvent.click(trigger); await userEvent.click(screen.getByRole("button", { name: "Outside" }));
  expect(trigger).toHaveAttribute("aria-expanded", "false");
  expect(run).not.toHaveBeenCalled();
});
it("omits the bubble on pages with no secondary actions", () => {
  const view = render(<ContextBubble label="Review tools" hint="Next" actions={[]} />);
  expect(view.container).toBeEmptyDOMElement();
});
it("keeps fine-pointer content open on hover and suppresses reopening after Escape until exit", async () => {
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: true })));
  const pointer = userEvent.setup();
  render(<ContextBubble label="Review tools" hint="Next" actions={actions} />);
  const trigger = screen.getByRole("button", { name: "Review tools" });
  await pointer.hover(trigger);
  const action = screen.getByRole("button", { name: /Review source/ });
  await pointer.hover(action);
  expect(trigger).toHaveAttribute("aria-expanded", "true");
  await pointer.hover(trigger);
  await pointer.keyboard("{Escape}");
  expect(trigger).toHaveAttribute("aria-expanded", "false");
  await pointer.hover(trigger);
  expect(trigger).toHaveAttribute("aria-expanded", "false");
  await pointer.unhover(trigger); await pointer.hover(trigger);
  expect(trigger).toHaveAttribute("aria-expanded", "true");
  expect(run).not.toHaveBeenCalled();
});
