import { Command } from "cmdk";
import { useEffect, useMemo, useState } from "react";
import { filterCommands, type Command as MenuCommand, type CommandGroup } from "../commands";
import type { MeetingSummary } from "../types";
import { kbdClass } from "./ShortcutHelp";
import { useMeetingSearch } from "./workbench/useMeetingSearch";

// The command menu's contents, loaded on demand (see CommandCenter) so cmdk stays out
// of the first page load.

const groups: CommandGroup[] = ["Go to", "Create", "Workspace", "Appearance", "Help"];
const groupClass =
  "px-1 pb-1 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:pt-2 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-text-3";
const itemClass =
  "flex min-h-9 cursor-pointer items-center gap-2 rounded-sm px-2 text-sm text-text transition-colors duration-[var(--dur-1)] data-[selected=true]:bg-hover";

/**
 * Live meeting titles for the current query. Results (and failures) show only for the
 * query they answer, so nothing stale can be chosen while a newer query is pending.
 * Unmounting (closing the menu) aborts the request.
 */
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
  const [result, setResult] = useState<{ status: "done" | "failed"; query: string } | null>(null);
  useEffect(() => setSearch(query), [query, setSearch]);
  // Search again only when the debounced query (and so `list`) changes.
  useEffect(() => {
    const current = search.trim();
    if (!current) {
      reset();
      return;
    }
    const controller = new AbortController();
    list(0, controller.signal)
      .then(() => {
        if (!controller.signal.aborted) setResult({ status: "done", query: current });
      })
      .catch(() => {
        if (!controller.signal.aborted) setResult({ status: "failed", query: current });
      });
    return () => controller.abort();
  }, [list]);
  const active = query.trim();
  if (!active) return null;
  const fresh = result?.query === active ? result.status : null;
  return (
    <Command.Group heading="Meetings" className={groupClass}>
      {!fresh && (
        <Command.Loading label="Searching meetings">
          <p className="m-0 px-2 py-2 text-sm text-text-2">Searching meetings…</p>
        </Command.Loading>
      )}
      {fresh === "failed" && <p className="m-0 px-2 py-2 text-sm text-text-2">Meeting search failed.</p>}
      {fresh === "done" &&
        meetings.map((meeting) => (
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
      {fresh === "done" && !meetings.length && (
        <p className="m-0 px-2 py-2 text-sm text-text-2">No permitted meetings match.</p>
      )}
    </Command.Group>
  );
}

export default function CommandMenuContent({
  commands,
  workspaceId,
  onRun,
  onOpenMeeting,
}: {
  commands: MenuCommand[];
  workspaceId?: string;
  onRun: (command: MenuCommand) => void;
  onOpenMeeting: (meeting: MeetingSummary) => void;
}) {
  const [query, setQuery] = useState("");
  const matches = useMemo(() => filterCommands(commands, query), [commands, query]);
  return (
    <Command label="Search commands and meetings" shouldFilter={false} loop>
      <Command.Input
        // The contents can arrive after the dialog opened, so the field takes focus itself.
        autoFocus
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
                  onSelect={() => onRun(command)}
                  className={itemClass}
                >
                  {command.label}
                </Command.Item>
              ))}
            </Command.Group>
          ) : null;
        })}
        {workspaceId && <MeetingResults workspaceId={workspaceId} query={query} onOpen={onOpenMeeting} />}
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
  );
}
