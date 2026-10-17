import { lazy, Suspense, useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { buildCommands, type Command as MenuCommand } from "../commands";
import { routePath } from "../navigation";
import { isApplePlatform, menuShortcutLabel, useShortcuts } from "../shortcuts";
import type { User, Workspace } from "../types";
import { Modal } from "./Modal";
import { kbdClass, ShortcutHelp } from "./ShortcutHelp";
import { chooseTheme } from "./ThemeSwitch";

// cmdk and the menu contents load on first open, or once the browser is idle.
const loadContent = () => import("./CommandMenu");
const CommandMenuContent = lazy(loadContent);

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
  // What closing should do with focus: return it to the opener, hand it to the new
  // page, or return it and then run a follow-up (such as opening the shortcut list).
  const closing = useRef<{ navigated: boolean; after?: () => void }>({ navigated: false });
  const title = useId();
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
        // Follow-ups such as the shortcut list open once focus is back.
        if (after) setTimeout(after, 0);
        // A new page owns focus (App also focuses #main on route changes).
        return navigated ? null : undefined;
      }}
    >
      <h2 id={title} className="sr-only">
        Command menu
      </h2>
      <Suspense fallback={<p className="m-0 px-4 py-3 text-sm text-text-2">Loading…</p>}>
        <CommandMenuContent
          commands={commands}
          workspaceId={workspaceId}
          onRun={run}
          onOpenMeeting={(meeting) => {
            if (!workspaceId) return;
            closing.current = { navigated: true };
            onOpenChange(false);
            navigate(routePath(workspaceId, "meetings", meeting.id));
          }}
        />
      </Suspense>
    </Modal>
  );
}

/**
 * The signed-in shell's keyboard layer: the "Search or jump…" trigger, the command
 * menu, the shortcut list, and the ⌘K / Ctrl+K, `?` and `/` shortcuts. The trigger
 * renders in place (the header); the dialogs render into <body>, so a collapsed,
 * hidden and inert header cannot hide them.
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
  // useMotionPreference returns a new toggle each render; keep the command list stable.
  const { calm, reduced } = motion;
  const toggleRef = useRef(motion.toggle);
  toggleRef.current = motion.toggle;
  const toggle = useCallback(() => toggleRef.current(), []);
  const commands = useMemo(
    () =>
      buildCommands({
        user,
        workspace,
        workspaces,
        motion: { calm, reduced, toggle },
        navigate,
        chooseTheme,
        openHelp: () => setHelp(true),
      }),
    [user, workspace, workspaces, calm, reduced, toggle, navigate],
  );
  useEffect(() => {
    const idle = window.requestIdleCallback ?? ((callback: () => void) => window.setTimeout(callback, 2000));
    idle(() => void loadContent());
  }, []);
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
      {createPortal(
        <>
          <CommandMenu
            open={menu}
            onOpenChange={setMenu}
            commands={commands}
            workspaceId={workspace?.id}
            navigate={navigate}
          />
          <ShortcutHelp open={help} onOpenChange={setHelp} />
        </>,
        document.body,
      )}
    </>
  );
}
