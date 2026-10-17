import { useState, ViewTransition, type Ref } from "react";

const preview = 60;

/**
 * The transcript as numbered lines (blank lines keep their numbers but are not shown).
 * Long transcripts start with the first 60 lines. During the signature moment the
 * evidence lines are highlighted, and each line in `names` carries the
 * view-transition-name its draft card takes over.
 */
export function TranscriptLines({
  lines,
  highlight,
  names,
  regionRef,
}: {
  lines: readonly string[];
  highlight?: ReadonlySet<number>;
  names?: ReadonlyMap<number, string>;
  regionRef?: Ref<HTMLDivElement>;
}) {
  const [all, setAll] = useState(false);
  const rows = lines.flatMap((text, i) => (text.trim() ? [{ n: i + 1, text }] : []));
  if (!rows.length) return null;
  const shown = all ? rows : rows.slice(0, preview);
  return (
    <div className="grid gap-2">
      <div
        ref={regionRef}
        role="region"
        aria-label="Transcript lines"
        tabIndex={0}
        className="max-h-[26rem] overflow-y-auto rounded-md border border-border bg-surface-2 py-1.5"
      >
        <ol className="m-0 list-none p-0">
          {shown.map(({ n, text }) => {
            const row = (
              <li
                key={n}
                data-line={n}
                data-evidence={highlight?.has(n) || undefined}
                className="grid grid-cols-[3.5ch_1fr] gap-3 px-3 py-0.5 text-sm leading-6 text-text-2 transition-colors duration-[var(--dur-2)] [contain-intrinsic-size:auto_1.75rem] [content-visibility:auto] data-[evidence]:bg-accent-soft data-[evidence]:text-text"
              >
                <span className="text-right font-mono text-xs leading-6 text-text-3 tabular-nums">{n}</span>
                <span className="min-w-0 break-words">{text}</span>
              </li>
            );
            const name = names?.get(n);
            return name ? (
              <ViewTransition key={n} name={name} share="outcome-morph" default="none">
                {row}
              </ViewTransition>
            ) : (
              row
            );
          })}
        </ol>
      </div>
      {rows.length > shown.length && (
        <button type="button" className="justify-self-start" onClick={() => setAll(true)}>
          Show all {rows.length} lines
        </button>
      )}
    </div>
  );
}
