import { useEffect, useState } from "react";
import { openConsent, useOnReturn } from "../consent";
import { api, scoped } from "../api";
import type { Integration, User, Workspace } from "../types";
import { ErrorNotice } from "./Feedback";
import JiraConnection from "./JiraConnection";
import GitHubConnection from "./GitHubConnection";
import SlackConnection from "./SlackConnection";
import GoogleMeetConnection from "./GoogleMeetConnection";
import LinkedInPublishingConnection from "./LinkedInPublishingConnection";
import ProviderRow from "./ProviderRow";

export const integrationStatus: Record<Integration["status"], string> = {
  ready: "Ready",
  configured: "Configured",
  connected: "Connected",
  preview_only: "Preview available",
  unavailable: "Adapter not available",
  needs_configuration: "Setup required",
};

export default function Integrations({
  workspace,
  user,
  refreshUser,
}: {
  workspace: Workspace;
  user: User;
  refreshUser: () => void;
}) {
  // The LinkedIn profile consent finishes in another tab; refresh the account on return.
  useOnReturn(() => {
    if (!user.is_visitor) refreshUser();
  });
  const [catalog, setCatalog] = useState<Integration[]>([]),
    [error, setError] = useState<unknown>(null),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(Boolean(user.is_visitor));
  // Private rows read their own provider status; the shared catalog only describes visitor rows.
  useEffect(() => {
    if (!user.is_visitor) return;
    const controller = new AbortController();
    api<Integration[]>(scoped(workspace.id, "/integrations"), { signal: controller.signal })
      .then(setCatalog)
      .catch((e) => {
        if (!controller.signal.aborted) setError(e);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [workspace.id, user.is_visitor]);
  async function linkedin(disconnect = false) {
    setBusy(true);
    setError(null);
    try {
      if (disconnect) {
        await api("/integrations/linkedin", { method: "DELETE" });
        refreshUser();
      } else {
        await openConsent(async () => {
          const result = await api<{ url: string }>("/integrations/linkedin/connect", { method: "POST" });
          return result.url;
        });
      }
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="connections">
      <h1>Connections</h1>
      <p className="page-hint">Only needed when you deliver reviewed outcomes to a tool.</p>
      <ErrorNotice error={error} />
      {user.capabilities.demo_mode && !user.is_visitor && (
        <p className="notice">
          Demo mode is on: you can preview handoffs, and nothing is sent to these tools.
        </p>
      )}
      <section className="connection-group" aria-labelledby="source-connections">
        <h2 id="source-connections">Meeting sources</h2>
        <div className="provider-list">
          <GoogleMeetConnection workspace={workspace} user={user} />
        </div>
      </section>
      <section className="connection-group" aria-labelledby="delivery-connections">
        <h2 id="delivery-connections">Outcome destinations</h2>
        {loading && <p role="status">Checking available connections…</p>}
        <div className="provider-list">
          {user.is_visitor ? (
            catalog.map((item) => (
              <ProviderRow
                key={item.id}
                id={item.id}
                name={item.name}
                summary={item.description}
                state={item.id === "local" ? "Ready" : "Private use only"}
                tone={item.id === "local" ? "on" : "off"}
              />
            ))
          ) : (
            <>
              <ProviderRow
                id="local"
                name="Local handoff"
                summary="Download reviewed outcomes as Markdown or JSON. No account needed."
                state="Ready"
                tone="on"
              />
              <GitHubConnection key={"github-" + workspace.id} workspace={workspace} user={user} />
              <JiraConnection key={workspace.id} workspace={workspace} />
              <SlackConnection key={"slack-" + workspace.id} workspace={workspace} />
              <LinkedInPublishingConnection key={"linkedin-publishing-" + workspace.id} workspace={workspace}>
                <div className="provider-sub">
                  <h4>Profile for participant context</h4>
                  <p className="muted">
                    Your own basic profile, to help confirm transcript names. It does not look up other
                    people.
                  </p>
                  <div className="actions">
                    {user.linkedin.connected ? (
                      <>
                        <span>Connected as {user.linkedin.profile?.name || "your LinkedIn account"}</span>
                        <button className="quiet" disabled={busy} onClick={() => linkedin(true)}>
                          Disconnect and delete stored profile
                        </button>
                      </>
                    ) : (
                      <button
                        disabled={busy || !user.capabilities.linkedin_configured}
                        onClick={() => linkedin()}
                      >
                        Connect my LinkedIn account
                      </button>
                    )}
                  </div>
                </div>
              </LinkedInPublishingConnection>
            </>
          )}
        </div>
      </section>
      {user.is_visitor && (
        <section className="panel">
          <h2>Explore without connecting live accounts</h2>
          <p>
            This isolated demo offers local reviewed handoffs and supported offline previews. Jira, Slack,
            GitHub and LinkedIn account connections belong to invited private use.
          </p>
        </section>
      )}
    </div>
  );
}
