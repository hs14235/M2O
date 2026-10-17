import { useId } from "react";
import { menuShortcutLabel } from "../shortcuts";
import { Modal } from "./Modal";

export const kbdClass =
  "inline-flex min-w-6 items-center justify-center rounded-sm border border-border bg-surface-2 px-1.5 font-mono text-xs text-text-2";

export function ShortcutHelp({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const title = useId(),
    description = useId();
  const rows: [string, string][] = [
    [menuShortcutLabel(), "Open or close the command menu"],
    ["/", "Search meetings"],
    ["?", "Show keyboard shortcuts"],
    ["↑ ↓", "Move through menu results"],
    ["Enter", "Run the selected command"],
    ["Esc", "Close the menu or this list"],
  ];
  return (
    <Modal open={open} onClose={() => onOpenChange(false)} labelledBy={title} describedBy={description}>
      <div className="p-5">
        <h2 id={title} className="m-0 text-base font-semibold">
          Keyboard shortcuts
        </h2>
        <p id={description} className="mt-1 mb-4 text-sm text-text-2">
          Single-key shortcuts pause while you type in a field.
        </p>
        <dl className="m-0 grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-2 text-sm">
          {rows.map(([keys, action]) => (
            <div key={action} className="contents">
              <dt>
                <kbd className={kbdClass}>{keys}</kbd>
              </dt>
              <dd className="m-0 text-text-2">{action}</dd>
            </div>
          ))}
        </dl>
        <div className="mt-5 flex justify-end">
          <button type="button" onClick={() => onOpenChange(false)}>
            Close
          </button>
        </div>
      </div>
    </Modal>
  );
}
