import { useEffect, useState } from "react";
import { openConsent, useOnReturn } from "../consent";
import { api, scoped } from "../api";
import type { GitHubStatus, User, Workspace } from "../types";
import type { ProviderTone } from "./ProviderRow";

type Provider = "local" | "github" | "jira" | "slack" | "linkedin";
interface Connection {
  configured: boolean;
  can_manage?: boolean;
  can_connect?: boolean;
  state: string;
  destination?: unknown;
}
interface Tool {
  id: Provider;
  name: string;
  state: string;
  tone: ProviderTone;
  /** "connect" starts the provider's own consent; "manage" opens Connections. */
  action?: { label: string; kind: "connect" | "manage"; path?: string };
}

const names: Record<Provider, string> = {
  local: "Local",
  github: "GitHub",
  jira: "Jira",
  slack: "Slack",
  linkedin: "LinkedIn",
};
const marks: Record<Provider, string> = { local: "MD", github: "GH", jira: "J", slack: "S", linkedin: "in" };

function oauthTool(id: Provider, value: Connection | null, connect: string, choose: string): Tool {
  const name = names[id];
  if (!value) return { id, name, state: "Unavailable", tone: "off" };
  if (!value.configured) return { id, name, state: "Not set up", tone: "off" };
  if (value.state === "connected")
    return value.destination === null
      ? { id, name, state: choose, tone: "ready", action: { label: "Choose", kind: "manage" } }
      : { id, name, state: "Connected", tone: "on" };
  const allowed = value.can_manage ?? value.can_connect ?? false;
  return {
    id,
    name,
    state: value.state === "reauthorization_required" ? "Reconnect" : "Not connected",
    tone: value.state === "reauthorization_required" ? "attention" : "ready",
    action: allowed ? { label: "Connect", kind: "connect", path: connect } : undefined,
  };
}

/**
 * The delivery tools at a glance in the sidebar: one line each with its state and the
 * next step. Connect starts the same consent as Settings → Connections.
 */
export default function SidebarTools({
  workspace,
  user,
  onManage,
}: {
  workspace: Workspace;
  user: User;
  onManage: () => void;
}) {
  const [revision, setRevision] = useState(0);
  // Connecting happens in another tab; read the tools again when this one is back in view.
  useOnReturn(() => setRevision((value) => value + 1));
  const [tools, setTools] = useState<Tool[] | null>(null),
    [busy, setBusy] = useState<Provider | null>(null),
    [failed, setFailed] = useState<Provider | null>(null);
  useEffect(() => {
    if (user.is_visitor) {
      setTools(
        (Object.keys(names) as Provider[]).map((id) =>
          id === "local"
            ? { id, name: names[id], state: "Ready", tone: "on" }
            : { id, name: names[id], state: "Private use", tone: "off" },
        ),
      );
      return;
    }
    const controller = new AbortController(),
      read = <T,>(path: string) =>
        api<T>(scoped(workspace.id, path), { signal: controller.signal }).catch(() => null);
    void Promise.all([
      read<GitHubStatus>("/integrations/github"),
      read<Connection>("/integrations/jira"),
      read<Connection>("/integrations/slack"),
      read<Connection>("/integrations/linkedin/publishing"),
    ]).then(([github, jira, slack, linkedin]) => {
      if (controller.signal.aborted) return;
      setTools([
        { id: "local", name: names.local, state: "Ready", tone: "on" },
        !github
          ? { id: "github", name: names.github, state: "Unavailable", tone: "off" }
          : !github.configured
            ? { id: "github", name: names.github, state: "Not set up", tone: "off" }
            : github.destination
              ? { id: "github", name: names.github, state: "Connected", tone: "on" }
              : {
                  id: "github",
                  name: names.github,
                  state: "Pick repo",
                  tone: "ready",
                  action: { label: "Choose", kind: "manage" },
                },
        oauthTool("jira", jira, "/integrations/jira/connect", "Pick project"),
        oauthTool("slack", slack, "/integrations/slack/connect", "Pick channel"),
        oauthTool(
          "linkedin",
          linkedin && { ...linkedin, destination: undefined },
          "/integrations/linkedin/publishing/connect",
          "",
        ),
      ]);
    });
    return () => controller.abort();
  }, [workspace.id, user.is_visitor, revision]);
  async function run(tool: Tool) {
    if (!tool.action) return;
    if (tool.action.kind === "manage" || !tool.action.path) return onManage();
    setBusy(tool.id);
    setFailed(null);
    const path = tool.action.path;
    try {
      await openConsent(async () => {
        const result = await api<{ url: string }>(scoped(workspace.id, path), { method: "POST" });
        return result.url;
      });
    } catch {
      setFailed(tool.id);
    } finally {
      setBusy((current) => (current === tool.id ? null : current));
    }
  }
  const live = tools?.filter((tool) => tool.tone === "on").length ?? 0;
  return (
    <section className="sidebar-tools" aria-labelledby="sidebar-tools-heading">
      <div className="sidebar-tools-head">
        <h2 id="sidebar-tools-heading">Tools</h2>
        {tools && (
          <span className="sidebar-tools-count">
            {live}/{tools.length} live
          </span>
        )}
      </div>
      {!tools ? (
        <p className="muted" role="status">
          Checking tools…
        </p>
      ) : (
        <ul>
          {tools.map((tool) => (
            <li key={tool.id} data-provider={tool.id === "local" ? "local" : tool.id}>
              <span className="tool-mark" aria-hidden="true">
                {marks[tool.id]}
              </span>
              <span className="tool-text">
                <strong>{tool.name}</strong>
                <span className="tool-state" data-tone={tool.tone}>
                  {failed === tool.id ? "Try again" : tool.state}
                </span>
              </span>
              {tool.action && (
                <button
                  type="button"
                  className="tool-action"
                  data-kind={tool.action.kind}
                  disabled={busy === tool.id || user.capabilities.demo_mode}
                  aria-label={tool.action.label + " " + tool.name + " from the sidebar"}
                  title={tool.action.label + " " + tool.name}
                  onClick={() => void run(tool)}
                >
                  <span aria-hidden="true">
                    {busy === tool.id ? "…" : tool.action.kind === "connect" ? "+" : "→"}
                  </span>
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      <button type="button" className="sidebar-tools-manage quiet" onClick={onManage}>
        All connections
      </button>
      {!user.is_visitor && (
        <p className="sidebar-tools-role">
          Your role: <strong>{workspace.role}</strong>
        </p>
      )}
    </section>
  );
}
