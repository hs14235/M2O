import { useEffect, useRef, useState } from "react";
import { api, scoped } from "../api";
import type { Workspace } from "../types";
import { ErrorNotice } from "./Feedback";
import type { LinkedInPublishingStatus } from "./LinkedInPublisher";

/**
 * Separate consent for posting as yourself. It never reuses the profile-context
 * connection, and disconnecting deletes the stored token without a LinkedIn request.
 */
export default function LinkedInPublishingConnection({ workspace }: { workspace: Workspace }) {
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
  return (
    <section className="panel" aria-labelledby="linkedin-publishing-title">
      <span className="eyebrow">Outcome destination</span>
      <h2 id="linkedin-publishing-title">LinkedIn posting</h2>
      <p>
        Post reviewed outcomes to your own LinkedIn account. Every post needs an exact preview that you
        approve, and the preview shows who will see it. M2O never posts on its own.
      </p>
      <ErrorNotice error={error} />
      {!status ? (
        !error && <p role="status">Checking LinkedIn posting…</p>
      ) : !status.configured ? (
        <p className="muted">
          An approved LinkedIn app with Share on LinkedIn must be configured by the application operator
          first.
        </p>
      ) : status.state === "connected" ? (
        <>
          <p className="notice">
            Posting connected
            {status.expires_at && <> · access expires {new Date(status.expires_at).toLocaleDateString()}</>}
          </p>
          <button disabled={busy} onClick={disconnect}>
            Disconnect posting and delete the stored token
          </button>
        </>
      ) : (
        <>
          {status.state === "reauthorization_required" && (
            <p className="notice">
              Your LinkedIn posting access expired or changed. Reconnect to post again.
            </p>
          )}
          <button className="primary" disabled={busy || !status.can_connect} onClick={connect}>
            {status.state === "reauthorization_required"
              ? "Reconnect LinkedIn posting"
              : "Connect LinkedIn posting"}
          </button>
          {!status.can_connect && (
            <p className="muted">Workspace owners and reviewers can connect posting.</p>
          )}
        </>
      )}
    </section>
  );
}
