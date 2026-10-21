import { configure, fireEvent, getConfig, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from "vitest";
import { CommandCenter } from "./CommandCenter";
import type { User, Workspace } from "../types";

// The menu body is a lazy chunk. A full parallel run (or a dev server alongside) can
// delay its import past Testing Library's 1 s default, so this file waits up to 5 s.
let previousTimeout = 1000;
beforeAll(() => {
  previousTimeout = getConfig().asyncUtilTimeout;
  configure({ asyncUtilTimeout: 5000 });
});
afterAll(() => configure({ asyncUtilTimeout: previousTimeout }));

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

function setup(overrides: Partial<Parameters<typeof CommandCenter>[0]> = {}, headerHidden = false) {
  const navigate = vi.fn();
  render(
    <>
      {/* Like the collapsed header's ChromeRegion: hidden and inert. */}
      <div hidden={headerHidden} inert={headerHidden}>
        <CommandCenter
          user={user}
          workspace={spaces[0]}
          workspaces={spaces}
          motion={{ calm: false, reduced: false, toggle: vi.fn() }}
          navigate={navigate}
          {...overrides}
        />
      </div>
      <main id="main" tabIndex={-1} />
    </>,
  );
  return { navigate, trigger: screen.getByRole("button", { name: /Search or jump/, hidden: true }) };
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
  // The menu body is a lazy chunk; under a full parallel run it can take past the 1 s default.
  await waitFor(() => expect(screen.getByRole("combobox")).toHaveFocus(), { timeout: 5000 });
  expect(await screen.findByRole("option", { name: "Meetings" }, { timeout: 5000 })).toBeInTheDocument();
  await userEvent.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  await waitFor(() => expect(trigger).toHaveFocus());
  expect(document.documentElement).not.toHaveClass("modal-open");
});

it("closes when the backdrop is clicked", async () => {
  const { trigger } = setup();
  await userEvent.click(trigger);
  const dialog = await screen.findByRole("dialog", { name: "Command menu" });
  await userEvent.click(dialog);
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(trigger).toHaveFocus();
});

it("filters commands and navigates on Enter, handing focus to the page", async () => {
  const { trigger, navigate } = setup();
  await userEvent.click(trigger);
  await userEvent.type(await screen.findByRole("combobox"), "Meetings");
  expect(screen.queryByRole("option", { name: "Audit" })).not.toBeInTheDocument();
  await userEvent.keyboard("{Enter}");
  expect(navigate).toHaveBeenCalledWith("/workspaces/eng/meetings");
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  await waitFor(() => expect(document.getElementById("main")).toHaveFocus());
});

it("searches meetings by title and opens the chosen one", async () => {
  const { trigger, navigate } = setup();
  await userEvent.click(trigger);
  await userEvent.type(await screen.findByRole("combobox"), "Release");
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
  await userEvent.type(await screen.findByRole("combobox"), "shortcuts");
  await userEvent.keyboard("{Enter}");
  expect(await screen.findByRole("dialog", { name: "Keyboard shortcuts" })).toBeVisible();
});

it("leaves out commands the person may not run", async () => {
  const { trigger } = setup({
    user: { ...user, is_visitor: true },
    workspace: { ...spaces[0], role: "editor" },
  });
  await userEvent.click(trigger);
  await screen.findByRole("combobox");
  expect(screen.queryByRole("option", { name: "Audit" })).not.toBeInTheDocument();
  expect(screen.queryByRole("option", { name: "New meeting" })).not.toBeInTheDocument();
  expect(screen.getByRole("option", { name: "My day" })).toBeInTheDocument();
});

const meeting = (id: string, title: string) => ({
  id,
  record_id: "r-" + id,
  title,
  visibility: "workspace",
  version: 1,
  current_revision: 1,
  occurred_on: null,
  timezone: "UTC",
});

it("opens a visible menu with Ctrl+K while the header is collapsed", async () => {
  setup({}, true);
  await userEvent.keyboard("{Control>}k{/Control}");
  const dialog = await screen.findByRole("dialog", { name: "Command menu" });
  expect(dialog.closest("[hidden], [inert]")).toBeNull();
  expect(dialog).toBeVisible();
  await waitFor(async () => expect(await screen.findByRole("combobox")).toHaveFocus());
});

it("does not close when a drag starts in the panel and ends on the backdrop", async () => {
  const { trigger } = setup();
  await userEvent.click(trigger);
  const dialog = await screen.findByRole("dialog", { name: "Command menu" });
  const field = await screen.findByRole("combobox");
  fireEvent.pointerDown(field);
  fireEvent.click(dialog);
  expect(dialog).toHaveAttribute("open");
  fireEvent.pointerDown(dialog);
  fireEvent.click(dialog);
  await waitFor(() => expect(dialog).not.toHaveAttribute("open"));
});

it("returns focus to the original opener when the menu replaces the shortcut list", async () => {
  const { trigger } = setup();
  trigger.focus();
  await userEvent.keyboard("?");
  const help = await screen.findByRole("dialog", { name: "Keyboard shortcuts" });
  expect(screen.getByRole("button", { name: "Close" })).toHaveFocus();
  await userEvent.keyboard("{Control>}k{/Control}");
  await waitFor(async () => expect(await screen.findByRole("combobox")).toHaveFocus());
  expect(help).not.toHaveAttribute("open");
  await userEvent.keyboard("{Escape}");
  await waitFor(() => expect(trigger).toHaveFocus());
});

it("never offers meeting results from an older query", async () => {
  let resolveNext!: (value: unknown) => void;
  api.mockReset();
  api
    .mockResolvedValueOnce({ meetings: [meeting("m-42", "Release readiness")], next_offset: null })
    .mockImplementationOnce(() => new Promise((resolve) => (resolveNext = resolve)));
  const { trigger, navigate } = setup();
  await userEvent.click(trigger);
  const field = await screen.findByRole("combobox");
  await userEvent.type(field, "Release");
  expect(await screen.findByRole("option", { name: /Release readiness/ })).toBeInTheDocument();
  await userEvent.type(field, " notes");
  // The old result disappears at once, before the newer search answers.
  expect(screen.queryByRole("option", { name: /Release readiness/ })).not.toBeInTheDocument();
  expect(screen.getByText("Searching meetings…")).toBeInTheDocument();
  await userEvent.keyboard("{Enter}");
  expect(navigate).not.toHaveBeenCalledWith(expect.stringContaining("m-42"));
  await waitFor(() => expect(api).toHaveBeenCalledTimes(2));
  resolveNext({ meetings: [meeting("m-7", "Release notes")], next_offset: null });
  expect(await screen.findByRole("option", { name: /Release notes/ })).toBeInTheDocument();
});

it("hides a failed search once the query changes", async () => {
  api.mockReset();
  api.mockRejectedValueOnce(new Error("offline")).mockImplementation(() => new Promise(() => {}));
  const { trigger } = setup();
  await userEvent.click(trigger);
  const field = await screen.findByRole("combobox");
  await userEvent.type(field, "Budget");
  expect(await screen.findByText("Meeting search failed.")).toBeInTheDocument();
  await userEvent.type(field, " review");
  expect(screen.queryByText("Meeting search failed.")).not.toBeInTheDocument();
  expect(screen.getByText("Searching meetings…")).toBeInTheDocument();
});
