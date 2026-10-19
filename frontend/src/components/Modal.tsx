import { useEffect, useRef, type ReactNode } from "react";
import "./command-menu.css";

/**
 * Remembers what had focus when a dialog opened, so focus can go back there on close.
 * These dialogs also open from shortcuts, so the opener can be any element.
 */
function useOpener(open: boolean) {
  const opener = useRef<HTMLElement | null>(null),
    wasOpen = useRef(false);
  // Read during render: by the time effects run, the dialog has already taken focus.
  if (open && !wasOpen.current)
    opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  wasOpen.current = open;
  return opener;
}

/**
 * A modal on the native <dialog> element: showModal() puts it in the top layer and
 * makes the page inert, Escape closes it, and nothing injects inline styles (the CSP
 * allows none). Content mounts only while open. Clicking the backdrop closes it.
 *
 * On close, focus returns to the opener, or to whatever `onClosed` returns
 * (null means the main region, for commands that changed the page).
 */
export function Modal({
  open,
  onClose,
  labelledBy,
  describedBy,
  className = "",
  onClosed,
  children,
}: {
  open: boolean;
  onClose: () => void;
  labelledBy: string;
  describedBy?: string;
  className?: string;
  onClosed?: () => HTMLElement | null | void;
  children: ReactNode;
}) {
  const dialog = useRef<HTMLDialogElement>(null),
    shown = useRef(false);
  const opener = useOpener(open);
  const closed = useRef(onClosed);
  closed.current = onClosed;
  useEffect(() => {
    const node = dialog.current;
    if (!node) return;
    if (open && !shown.current) {
      shown.current = true;
      if (!node.open) node.showModal();
      document.documentElement.classList.add("modal-open");
      node.querySelector<HTMLElement>("input, button, [tabindex]:not([tabindex='-1'])")?.focus();
    } else if (!open && shown.current) {
      shown.current = false;
      if (node.open) node.close();
      const another = document.querySelector("dialog[open]");
      if (!another) document.documentElement.classList.remove("modal-open");
      const target = closed.current?.();
      const element = target === undefined ? opener.current : target;
      opener.current = null;
      // Leave focus alone if another modal has just taken it.
      if (!another) (element?.isConnected ? element : document.getElementById("main"))?.focus();
    }
  }, [open, opener]);
  useEffect(
    () => () => {
      if (!shown.current) return;
      dialog.current?.close();
      if (!document.querySelector("dialog[open]")) document.documentElement.classList.remove("modal-open");
    },
    [],
  );
  return (
    <dialog
      ref={dialog}
      aria-labelledby={labelledBy}
      aria-describedby={describedBy}
      // Escape (or the browser) closed it: bring React state in line.
      onClose={() => open && onClose()}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      className={
        "m2o-modal fixed inset-x-0 top-[12vh] mx-auto mt-0 w-[min(640px,calc(100vw-32px))] max-w-none overflow-hidden rounded-lg border border-border bg-surface p-0 text-text shadow-lg outline-none open:animate-[settle_var(--dur-2)_var(--ease-out)] " +
        className
      }
    >
      {open && children}
    </dialog>
  );
}
