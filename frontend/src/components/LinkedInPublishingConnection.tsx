import { type ReactNode, useEffect, useRef, useState } from "react";
import { api, scoped } from "../api";
import type { Workspace } from "../types";
import { ErrorNotice } from "./Feedback";
import type { LinkedInPublishingStatus } from "./LinkedInPublisher";
import ProviderRow, { type ProviderTone } from "./ProviderRow";

/**
 * Separate consent for posting as yourself. It never reuses the profile-context
 * connection, and disconnecting deletes the stored token without a LinkedIn request.
 */
export default function LinkedInPublishingConnection({
  workspace,
  children,
}: {
  workspace: Workspace;
  children?: ReactNode;
}) {
  const [status, setStatus] = useState<LinkedInPublishingStatus | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(null),
    [revision, setRevision] = useState(0);
  const pending = useRef<AbortController | null>(null),
    path = scoped(workspace.id, "/integrations/linkedin/publishing");
  useEffect(() => {
    const controller = new AbortController();
    api<LinkedInPublishingStatus>(path, { signal: controller.signal })
      .then((value) => {
        if (!controller.signal.aborted) setStatus(value);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e);
      });
    return () => {
      controller.abort();
      pending.current?.abort();
    };
  }, [path, revision]);
  async function run(operation: (signal: AbortSignal) => Promise<void>) {
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    setBusy(true);
    setError(null);
    try {
      await operation(controller.signal);
    } catch (e) {
      if (!controller.signal.aborted) setError(e);
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }
  const connect = () =>
    run(async (signal) => {
      const result = await api<{ url: string }>(path + "/connect", { signal, method: "POST" });
      if (!signal.aborted) window.location.assign(result.url);
    });
  const disconnect = () =>
    run(async (signal) => {
      await api(path, { signal, method: "DELETE" });
      if (!signal.aborted) setRevision((value) => value + 1);
    });
  const [state, tone]: [string, ProviderTone] = !status
    ? [error ? "Unavailable" : "Checking…", "off"]
    : !status.configured
      ? ["Not set up", "off"]
      : status.state === "connected"
        ? ["Connected", "on"]
        : status.state === "reauthorization_required"
          ? ["Reconnect needed", "attention"]
          : ["Not connected", "ready"];
  return (
    <ProviderRow
      id="linkedin"
      name="LinkedIn"
      summary="Post reviewed outcomes as yourself, only after you approve the exact text and audience."
      state={state}
      tone={tone}
      action={
        status?.configured && status.state !== "connected" ? (
          <button className="primary" disabled={busy || !status.can_connect} onClick={connect}>
            {status.state === "reauthorization_required"
              ? "Reconnect LinkedIn posting"
              : "Connect LinkedIn posting"}
          </button>
        ) : undefined
      }
    >
      <ErrorNotice error={error} />
      {status && !status.configured && (
        <p className="muted">
          An approved LinkedIn app with Share on LinkedIn must be configured by the application operator
          first.
        </p>
      )}
      {status?.state === "connected" && (
        <div className="actions">
          <span>
            Posting connected
            {status.expires_at && <> · access expires {new Date(status.expires_at).toLocaleDateString()}</>}
          </span>
          <button className="quiet" disabled={busy} onClick={disconnect}>
            Disconnect posting and delete the stored token
          </button>
        </div>
      )}
      {status?.configured && !status.can_connect && status.state !== "connected" && (
        <p className="muted">Workspace owners and reviewers can connect posting.</p>
      )}
      {children}
    </ProviderRow>
  );
}
