import { ViewTransition } from "react";
import type { Kind, Outcome } from "../../types";
import { kindNames } from "../OutcomeCard";
import { evidenceLines, momentName } from "./signatureMoment";
import "../../signature.css";

const order: Kind[] = ["action", "decision", "blocker", "follow_up", "risk"];
const kindColor: Record<Kind, string> = {
  action: "text-k-action",
  decision: "text-k-decision",
  blocker: "text-k-blocker",
  follow_up: "text-k-follow",
  risk: "text-k-risk",
};

/** Outcomes in the order Review lists them. */
export function sortDrafts(outcomes: readonly Outcome[]): Outcome[] {
  return [...outcomes].sort(
    (a, b) => order.indexOf(a.kind) - order.indexOf(b.kind) || a.id.localeCompare(b.id),
  );
}

/**
 * The end state of the signature moment: one compact card per outcome, each naming
 * the line it came from and linking to its review. A card paired with a transcript
 * line shares that line's view-transition-name, so the line morphs into it; the
 * other cards arrive with the list stagger.
 */
export function DraftOutcomes({
  outcomes,
  lines,
  pairs,
  hrefFor,
  onOpen,
}: {
  outcomes: readonly Outcome[];
  lines: readonly string[];
  pairs: ReadonlyMap<number, string>;
  hrefFor: (id: string) => string;
  onOpen?: (id: string) => void;
}) {
  const pairedLine = new Map([...pairs].map(([line, name]) => [name, line]));
  const drafts = outcomes.every((item) => item.status === "draft");
  return (
    <div className="grid gap-3">
      <div role="status" className="reveal">
        <h2 className="m-0 text-base font-semibold text-text">
          {outcomes.length} {drafts ? "draft " : ""}outcome{outcomes.length === 1 ? "" : "s"} found
        </h2>
      </div>
      <ul className="stagger m-0 grid list-none gap-2 p-0 sm:grid-cols-2">
        {outcomes.map((item) => {
          const name = momentName(item.id),
            evidence = item.evidence[0],
            line =
              pairedLine.get(name) ??
              (evidence ? (evidenceLines(lines, evidence)[0] ?? evidence.start_line) : undefined);
          const source = [
            line !== undefined ? "line " + line : "",
            evidence?.speaker || item.assignee_hint || "",
            drafts ? "" : item.status,
          ].filter(Boolean);
          const card = (
            <li key={item.id} className={pairedLine.has(name) ? "animate-none" : undefined}>
              <a
                href={hrefFor(item.id)}
                onClick={(event) => {
                  if (
                    !onOpen ||
                    event.button !== 0 ||
                    event.metaKey ||
                    event.ctrlKey ||
                    event.shiftKey ||
                    event.altKey
                  )
                    return;
                  event.preventDefault();
                  onOpen(item.id);
                }}
                className="grid h-full gap-1 rounded-md border border-border bg-surface px-3.5 py-2.5 text-text no-underline shadow-sm hover:border-border-strong hover:bg-hover"
              >
                <span className={"text-xs font-semibold tracking-wide uppercase " + kindColor[item.kind]}>
                  {kindNames[item.kind]}
                </span>
                <strong className="text-sm leading-snug font-semibold">{item.title}</strong>
                {source.length > 0 && <span className="text-xs text-text-3">{source.join(" · ")}</span>}
              </a>
            </li>
          );
          return pairedLine.has(name) ? (
            <ViewTransition key={item.id} name={name} share="outcome-morph" default="none">
              {card}
            </ViewTransition>
          ) : (
            card
          );
        })}
      </ul>
    </div>
  );
}
