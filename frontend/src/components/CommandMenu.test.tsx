import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { CommandCenter } from "./CommandMenu";
import type { User, Workspace } from "../types";

const api = vi.hoisted(() => vi.fn());
vi.mock("../api", async (original) => ({ ...(await original<typeof import("../api")>()), api }));

const user: User = {
  id: "u1",
  name: "Avery",
  email: "avery@example.test",
  capabilities: {
    demo_mode: false,
    linkedin_configured: false,
    ollama_model: null,
    embedding_provider: "hash",
    allowed_repos: [],
  },
  linkedin: { connected: false, profile: null },
};
const spaces: Workspace[] = [{ id: "eng", name: "Platform", department: "engineering", role: "owner" }];
let errors: ReturnType<typeof vi.spyOn>;

// jsdom has no modal dialogs: model showModal(), close() and Escape-to-close.
HTMLDialogElement.prototype.showModal = function (this: HTMLDialogElement) {
  this.setAttribute("open", "");
};
HTMLDialogElement.prototype.close = function (this: HTMLDialogElement) {
  if (!this.open) return;
  this.removeAttribute("open");
  this.dispatchEvent(new Event("close"));
};
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape")
    [...document.querySelectorAll<HTMLDialogElement>("dialog[open]")].at(-1)?.close();
});

beforeEach(() => {
  errors = vi.spyOn(console, "error");
  Element.prototype.scrollIntoView = vi.fn();
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
  api.mockReset();
  api.mockResolvedValue({
    meetings: [
      {
        id: "m-42",
        record_id: "r1",
        title: "Release readiness",
        visibility: "workspace",
        version: 1,
        current_revision: 1,
        occurred_on: null,
        timezone: "UTC",
      },
    ],
    next_offset: null,
  });
});
afterEach(() => {
  expect(errors).not.toHaveBeenCalled();
  errors.mockRestore();
  vi.unstubAllGlobals();
});

function setup(overrides: Partial<Parameters<typeof CommandCenter>[0]> = {}) {
  const navigate = vi.fn();
  render(
    <>
      <CommandCenter
        user={user}
        workspace={spaces[0]}
        workspaces={spaces}
        motion={{ calm: false, reduced: false, toggle: vi.fn() }}
        navigate={navigate}
        {...overrides}
      />
      <main id="main" tabIndex={-1} />
    </>,
  );
  return { navigate, trigger: screen.getByRole("button", { name: /Search or jump/ }) };
}

it("opens with Ctrl+K as a labelled dialog with a combobox, and Escape returns focus", async () => {
  const { trigger } = setup();
  trigger.focus();
  const styles = document.querySelectorAll("style").length;
  await userEvent.keyboard("{Control>}k{/Control}");
  // The CSP allows no injected styles; scroll locks with a class instead.
  expect(document.querySelectorAll("style")).toHaveLength(styles);
  expect(document.documentElement).toHaveClass("modal-open");
  const dialog = await screen.findByRole("dialog", { name: "Command menu" });
  expect(dialog).toBeVisible();
  expect(screen.getByRole("combobox")).toHaveFocus();
  expect(screen.getByRole("option", { name: "Meetings" })).toBeInTheDocument();
  await userEvent.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  await waitFor(() => expect(trigger).toHaveFocus());
  expect(document.documentElement).not.toHaveClass("modal-open");
});

it("closes when the backdrop is clicked", async () => {
  const { trigger } = setup();
  await userEvent.click(trigger);
  const dialog = screen.getByRole("dialog", { name: "Command menu" });
  await userEvent.click(dialog);
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(trigger).toHaveFocus();
});

it("filters commands and navigates on Enter, handing focus to the page", async () => {
  const { trigger, navigate } = setup();
  await userEvent.click(trigger);
  await userEvent.type(screen.getByRole("combobox"), "Meetings");
  expect(screen.queryByRole("option", { name: "Audit" })).not.toBeInTheDocument();
  await userEvent.keyboard("{Enter}");
  expect(navigate).toHaveBeenCalledWith("/workspaces/eng/meetings");
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  await waitFor(() => expect(document.getElementById("main")).toHaveFocus());
});

it("searches meetings by title and opens the chosen one", async () => {
  const { trigger, navigate } = setup();
  await userEvent.click(trigger);
  await userEvent.type(screen.getByRole("combobox"), "Release");
  await userEvent.click(await screen.findByRole("option", { name: /Release readiness/ }));
  expect(api).toHaveBeenCalledWith(
    expect.stringContaining("/workspaces/eng/meetings?"),
    expect.objectContaining({ signal: expect.any(AbortSignal) }),
  );
  expect(String(api.mock.calls.at(-1)?.[0])).toContain("q=Release");
  expect(navigate).toHaveBeenCalledWith("/workspaces/eng/meetings/m-42/transcript");
});

it("opens the shortcut list with ? and from the menu", async () => {
  const { trigger } = setup();
  await userEvent.keyboard("?");
  expect(await screen.findByRole("dialog", { name: "Keyboard shortcuts" })).toBeVisible();
  await userEvent.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  await userEvent.click(trigger);
  await userEvent.type(screen.getByRole("combobox"), "shortcuts");
  await userEvent.keyboard("{Enter}");
  expect(await screen.findByRole("dialog", { name: "Keyboard shortcuts" })).toBeVisible();
});

it("leaves out commands the person may not run", async () => {
  const { trigger } = setup({
    user: { ...user, is_visitor: true },
    workspace: { ...spaces[0], role: "editor" },
  });
  await userEvent.click(trigger);
  expect(screen.queryByRole("option", { name: "Audit" })).not.toBeInTheDocument();
  expect(screen.queryByRole("option", { name: "New meeting" })).not.toBeInTheDocument();
  expect(screen.getByRole("option", { name: "My day" })).toBeInTheDocument();
});
