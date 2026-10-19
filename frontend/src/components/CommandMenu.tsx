import { Command } from "cmdk";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { buildCommands, filterCommands, type Command as MenuCommand, type CommandGroup } from "../commands";
import { routePath } from "../navigation";
import { isApplePlatform, menuShortcutLabel, useShortcuts } from "../shortcuts";
import type { MeetingSummary, User, Workspace } from "../types";
import { chooseTheme } from "./ThemeSwitch";
import { Modal } from "./Modal";
import { kbdClass, ShortcutHelp } from "./ShortcutHelp";
import { useMeetingSearch } from "./workbench/useMeetingSearch";

const groups: CommandGroup[] = ["Go to", "Create", "Workspace", "Appearance", "Help"];
const groupClass =
  "px-1 pb-1 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:pt-2 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-text-3";
const itemClass =
  "flex min-h-9 cursor-pointer items-center gap-2 rounded-sm px-2 text-sm text-text transition-colors duration-[var(--dur-1)] data-[selected=true]:bg-hover";

/** Live meeting titles for the current query. Unmounting (closing the menu) aborts the request. */
function MeetingResults({
  workspaceId,
  query,
  onOpen,
}: {
  workspaceId: string;
  query: string;
  onOpen: (meeting: MeetingSummary) => void;
}) {
  const { meetings, search, setSearch, list, reset } = useMeetingSearch(workspaceId);
  const [state, setState] = useState<"searching" | "done" | "failed">("done"),
    [searchedFor, setSearchedFor] = useState("");
  useEffect(() => setSearch(query), [query, setSearch]);
  const active = search.trim();
  // Search again only when the debounced query (and so `list`) changes.
  useEffect(() => {
    const current = search.trim();
    if (!current) {
      reset();
      return;
    }
    const controller = new AbortController();
    setState("searching");
    list(0, controller.signal)
      .then(() => {
        if (controller.signal.aborted) return;
        setSearchedFor(current);
        setState("done");
      })
      .catch(() => {
        if (!controller.signal.aborted) setState("failed");
      });
    return () => controller.abort();
  }, [list]);
  if (!active) return null;
  const settled = state === "done" && searchedFor === active;
  return (
    <Command.Group heading="Meetings" className={groupClass}>
      {!settled && state !== "failed" && !meetings.length && (
        <Command.Loading label="Searching meetings">
          <p className="m-0 px-2 py-2 text-sm text-text-2">Searching meetings…</p>
        </Command.Loading>
      )}
      {state === "failed" && <p className="m-0 px-2 py-2 text-sm text-text-2">Meeting search failed.</p>}
      {meetings.map((meeting) => (
        <Command.Item
          key={meeting.id}
          value={"meeting-" + meeting.id}
          onSelect={() => onOpen(meeting)}
          className={itemClass}
        >
          <span className="truncate">{meeting.title}</span>
          <span className="ml-auto shrink-0 font-mono text-xs text-text-3">{meeting.id}</span>
        </Command.Item>
      ))}
      {settled && !meetings.length && (
        <p className="m-0 px-2 py-2 text-sm text-text-2">No permitted meetings match.</p>
      )}
    </Command.Group>
  );
}

export function CommandMenu({
  open,
  onOpenChange,
  commands,
  workspaceId,
  navigate,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  commands: MenuCommand[];
  workspaceId?: string;
  navigate: (path: string) => void;
}) {
  const [query, setQuery] = useState("");
  // What closing should do with focus: return it to the opener, hand it to the new
  // page, or return it and then run a follow-up (such as opening the shortcut list).
  const closing = useRef<{ navigated: boolean; after?: () => void }>({ navigated: false });
  const title = useId();
  const matches = useMemo(() => filterCommands(commands, query), [commands, query]);
  function run(command: MenuCommand) {
    closing.current =
      command.id === "help" ? { navigated: false, after: command.run } : { navigated: command.navigates };
    onOpenChange(false);
    if (command.id !== "help") command.run();
  }
  return (
    <Modal
      open={open}
      onClose={() => onOpenChange(false)}
      labelledBy={title}
      onClosed={() => {
        const { navigated, after } = closing.current;
        closing.current = { navigated: false };
        setQuery("");
        // Follow-ups such as the shortcut list open once focus is back.
        if (after) setTimeout(after, 0);
        // A new page owns focus (App also focuses #main on route changes).
        return navigated ? null : undefined;
      }}
    >
      <h2 id={title} className="sr-only">
        Command menu
      </h2>
      <Command label="Search commands and meetings" shouldFilter={false} loop>
        <Command.Input
          value={query}
          onValueChange={setQuery}
          placeholder="Search or jump to…"
          className="h-12 w-full rounded-none border-0 border-b border-border bg-transparent px-4 text-base text-text shadow-none outline-none placeholder:text-text-3 focus:shadow-none"
        />
        <Command.List className="max-h-[min(420px,60vh)] overflow-y-auto overscroll-contain py-1">
          {groups.map((group) => {
            const items = matches.filter((command) => command.group === group);
            return items.length ? (
              <Command.Group key={group} heading={group} className={groupClass}>
                {items.map((command) => (
                  <Command.Item
                    key={command.id}
                    value={command.id}
                    keywords={command.keywords}
                    onSelect={() => run(command)}
                    className={itemClass}
                  >
                    {command.label}
                  </Command.Item>
                ))}
              </Command.Group>
            ) : null;
          })}
          {workspaceId && (
            <MeetingResults
              workspaceId={workspaceId}
              query={query}
              onOpen={(meeting) => {
                closing.current = { navigated: true };
                onOpenChange(false);
                navigate(routePath(workspaceId, "meetings", meeting.id));
              }}
            />
          )}
          {!matches.length && !(workspaceId && query.trim()) && (
            <p className="m-0 px-4 py-3 text-sm text-text-2">No matching commands.</p>
          )}
        </Command.List>
        <p className="m-0 flex flex-wrap gap-x-4 gap-y-1 border-t border-border px-4 py-2 text-xs text-text-3">
          <span>
            <kbd className={kbdClass}>↑</kbd> <kbd className={kbdClass}>↓</kbd> move
          </span>
          <span>
            <kbd className={kbdClass}>Enter</kbd> select
          </span>
          <span>
            <kbd className={kbdClass}>Esc</kbd> close
          </span>
        </p>
      </Command>
    </Modal>
  );
}

/**
 * The signed-in shell's keyboard layer: the "Search or jump…" trigger, the command
 * menu, the shortcut list, and the ⌘K / Ctrl+K, `?` and `/` shortcuts.
 */
export function CommandCenter({
  user,
  workspace,
  workspaces,
  motion,
  navigate,
}: {
  user: User;
  workspace?: Workspace;
  workspaces: Workspace[];
  motion: { calm: boolean; reduced: boolean; toggle: () => void };
  navigate: (path: string) => void;
}) {
  const [menu, setMenu] = useState(false),
    [help, setHelp] = useState(false);
  const commands = useMemo(
    () =>
      buildCommands({
        user,
        workspace,
        workspaces,
        motion,
        navigate,
        chooseTheme,
        openHelp: () => setHelp(true),
      }),
    [user, workspace, workspaces, motion, navigate],
  );
  useShortcuts({
    menu: () => {
      setHelp(false);
      setMenu((value) => !value);
    },
    help: () => setHelp(true),
    search: () => {
      const field = document.querySelector<HTMLInputElement>(".meeting-list input[type='search']");
      if (field) field.focus();
      else setMenu(true);
    },
  });
  return (
    <>
      <button
        type="button"
        aria-haspopup="dialog"
        aria-label="Search or jump…"
        aria-keyshortcuts={isApplePlatform() ? "Meta+K" : "Control+K"}
        onClick={() => setMenu(true)}
        // A phone's header row has no room for it (Sign out would be pushed off), and the
        // menu is keyboard-first; every command is also reachable from the page itself.
        className="inline-flex items-center gap-2 text-text-2 max-sm:hidden"
      >
        <span>Search or jump…</span>
        <kbd className={kbdClass} aria-hidden="true">
          {menuShortcutLabel()}
        </kbd>
      </button>
      <CommandMenu
        open={menu}
        onOpenChange={setMenu}
        commands={commands}
        workspaceId={workspace?.id}
        navigate={navigate}
      />
      <ShortcutHelp open={help} onOpenChange={setHelp} />
    </>
  );
}
