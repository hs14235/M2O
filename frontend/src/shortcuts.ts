import { useEffect, useRef } from "react";

export type Shortcut = "menu" | "help" | "search";

/** Apple platforms use ⌘ for the menu; everything else uses Ctrl (Ctrl+K on a Mac is left alone). */
export function isApplePlatform(nav: Pick<Navigator, "platform" | "userAgent"> = navigator) {
  return /Mac|iPhone|iPad|iPod/i.test(nav.platform || nav.userAgent);
}

/** Label for the menu shortcut, as shown on the trigger and in the shortcut list. */
export function menuShortcutLabel(apple = isApplePlatform()) {
  return apple ? "⌘K" : "Ctrl K";
}

/** True while the user is typing: single-key shortcuts must not fire then. */
export function isTypingTarget(target: EventTarget | null) {
  if (!(target instanceof Element)) return false;
  if (target instanceof HTMLElement && target.isContentEditable) return true;
  return Boolean(target.closest("input, textarea, select, [contenteditable]:not([contenteditable='false'])"));
}

function dialogOpen() {
  // Our modals are native <dialog> elements that stay in the page closed, so only an
  // open one counts. ARIA dialogs from elsewhere count unless marked data-state="closed"
  // (the convention for a dialog still animating out).
  return Boolean(
    document.querySelector(
      "[role='dialog']:not([data-state='closed']), [role='alertdialog']:not([data-state='closed']), dialog[open]",
    ),
  );
}

/**
 * Which shortcut a key press means, if any. ⌘K / Ctrl+K works everywhere, even in a
 * field, because it uses a modifier. `?` and `/` are single keys, so they are ignored
 * while typing, during IME composition, on key repeat, with Ctrl/⌘/Alt, when another
 * handler already used the key, or while a dialog is open.
 */
export function shortcutFor(event: KeyboardEvent, apple = isApplePlatform()): Shortcut | null {
  // Some synthetic keydowns (Chrome autofill, for one) carry no key at all.
  if (typeof event.key !== "string" || event.isComposing || event.keyCode === 229) return null;
  if (event.key.toLowerCase() === "k" && !event.altKey && !event.shiftKey) {
    const modifier = apple ? event.metaKey && !event.ctrlKey : event.ctrlKey && !event.metaKey;
    return modifier ? "menu" : null;
  }
  if (event.key !== "?" && event.key !== "/") return null;
  if (event.repeat || event.ctrlKey || event.metaKey || event.altKey || event.defaultPrevented) return null;
  if (isTypingTarget(event.target) || dialogOpen()) return null;
  return event.key === "?" ? "help" : "search";
}

export function useShortcuts(handlers: Record<Shortcut, () => void>) {
  const current = useRef(handlers);
  current.current = handlers;
  useEffect(() => {
    const apple = isApplePlatform();
    const press = (event: KeyboardEvent) => {
      const shortcut = shortcutFor(event, apple);
      if (!shortcut) return;
      event.preventDefault();
      // Holding ⌘K / Ctrl+K should not flicker the menu open and shut.
      if (!event.repeat) current.current[shortcut]();
    };
    window.addEventListener("keydown", press);
    return () => window.removeEventListener("keydown", press);
  }, []);
}
