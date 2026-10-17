import { ViewTransition } from "react";
import type { Kind, Outcome } from "../../types";
import { kindNames } from "../OutcomeCard";
import { isPlainClick } from "./links";
import { evidenceLines, momentName } from "./signatureMoment";
import "../../signature.css";

const kindColor: Record<Kind, string> = {
  action: "text-k-action",
  decision: "text-k-decision",
  blocker: "text-k-blocker",
  follow_up: "text-k-follow",
  risk: "text-k-risk",
};

/**
 * The end state of the signature moment: one compact card per outcome, each naming
 * the line its evidence starts on and linking to its review. A card whose name is in
 * `paired` shares a transcript line's view-transition-name, so that line morphs into
 * it; the other cards arrive with the list stagger.
 */
export function DraftOutcomes({
  outcomes,
  lines,
  paired,
  hrefFor,
  onOpen,
}: {
  outcomes: readonly Outcome[];
  lines: readonly string[];
  paired: ReadonlySet<string>;
  hrefFor: (id: string) => string;
  onOpen?: (id: string) => void;
}) {
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
            line = evidence ? (evidenceLines(lines, evidence)[0] ?? evidence.start_line) : undefined;
          const source = [
            line !== undefined ? "line " + line : "",
            evidence?.speaker || item.assignee_hint || "",
            drafts ? "" : item.status,
          ].filter(Boolean);
          const card = (
            <li key={item.id} className={paired.has(name) ? "animate-none" : undefined}>
              <a
                href={hrefFor(item.id)}
                onClick={(event) => {
                  if (!onOpen || !isPlainClick(event)) return;
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
          return paired.has(name) ? (
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
