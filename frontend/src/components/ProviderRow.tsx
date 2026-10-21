import type { ReactNode } from "react";

export type ProviderTone = "on" | "ready" | "attention" | "off";

const marks: Record<string, string> = {
  local: "MD",
  github: "GH",
  jira: "J",
  slack: "S",
  linkedin: "in",
  "google-meet": "M",
};

/** One tool on the Connections page: what it is, where it stands, and its main action on one line. */
export default function ProviderRow({
  id,
  name,
  summary,
  state,
  tone,
  action,
  children,
}: {
  id: string;
  name: string;
  summary: string;
  state: string;
  tone: ProviderTone;
  action?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <article className="provider" data-provider={id} aria-labelledby={id + "-provider-name"}>
      <div className="provider-head">
        <span className="provider-mark" aria-hidden="true">
          {marks[id] || name.slice(0, 1)}
        </span>
        <div className="provider-title">
          <h3 id={id + "-provider-name"}>{name}</h3>
          <p>{summary}</p>
        </div>
        <span className="provider-state" data-tone={tone}>
          {state}
        </span>
        {action && <div className="provider-action">{action}</div>}
      </div>
      {children && <div className="provider-body">{children}</div>}
    </article>
  );
}
