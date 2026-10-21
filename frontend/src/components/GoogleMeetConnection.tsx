import { useEffect, useState } from "react";
import { api, scoped } from "../api";
import type { GoogleMeetStatus, User, Workspace } from "../types";
import { ErrorNotice } from "./Feedback";
import ProviderRow, { type ProviderTone } from "./ProviderRow";

export default function GoogleMeetConnection({ workspace, user }: { workspace: Workspace; user: User }) {
  const [status, setStatus] = useState<GoogleMeetStatus | null>(null),
    [error, setError] = useState<unknown>(null),
    [busy, setBusy] = useState(false),
    [refresh, setRefresh] = useState(0),
    [notice, setNotice] = useState("");
  const eligible = !user.is_visitor && workspace.role !== "viewer" && !user.capabilities.demo_mode;
  useEffect(() => {
    if (!eligible) return;
    const controller = new AbortController();
    api<GoogleMeetStatus>(scoped(workspace.id, "/integrations/google-meet"), { signal: controller.signal })
      .then((value) => {
        if (!controller.signal.aborted) setStatus(value);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e);
      });
    return () => controller.abort();
  }, [workspace.id, eligible, refresh]);
  async function connect() {
    setBusy(true);
    setError(null);
    try {
      const value = await api<{ url: string }>(scoped(workspace.id, "/integrations/google-meet/connect"), {
        method: "POST",
      });
      window.location.assign(value.url);
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  }
  async function disconnect() {
    setBusy(true);
    setError(null);
    try {
      await api(scoped(workspace.id, "/integrations/google-meet"), { method: "DELETE" });
      setNotice(
        "Your local Google Meet connection was removed. Google's account consent remains under your control.",
      );
      setStatus(null);
      setRefresh((value) => value + 1);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  const [state, tone]: [string, ProviderTone] = !eligible
    ? ["Private accounts", "off"]
    : !status
      ? [error ? "Unavailable" : "Checking…", "off"]
      : status.setup_required
        ? ["Not set up", "off"]
        : status.can_import
          ? ["Connected", "on"]
          : status.state === "reauthorization_required"
            ? ["Reconnect needed", "attention"]
            : ["Not connected", "ready"];
  return (
    <ProviderRow
      id="google-meet"
      name="Google Meet"
      summary="Import the latest meeting's transcript, then review it before saving."
      state={state}
      tone={tone}
      action={
        eligible &&
        status &&
        !status.setup_required &&
        (status.can_import ? (
          <button className="quiet" disabled={busy} onClick={disconnect}>
            Disconnect my Google Meet account
          </button>
        ) : (
          <button className="primary" disabled={busy || !status.configured} onClick={connect}>
            {status.state === "reauthorization_required"
              ? "Reconnect my Google Meet account"
              : "Connect my Google Meet account"}
          </button>
        ))
      }
    >
      <ErrorNotice error={error} />
      {notice && <p role="status">{notice}</p>}
      {!eligible && (
        <p className="muted">
          Needs an invited private contributor account. Synthetic demos use their prepared examples.
        </p>
      )}
      {status?.setup_required && (
        <details>
          <summary>What setup needs</summary>
          <p>
            A Google Cloud OAuth app with the Google Meet REST API enabled, the meetings.space.readonly scope
            and this installation's callback. Meetings must already produce transcripts; connecting cannot
            create a missing one. Client credentials belong in private backend configuration.
          </p>
        </details>
      )}
      {status?.can_import && (
        <p className="muted">Import an existing transcript from a meeting's Transcript step.</p>
      )}
      {eligible && status && !status.setup_required && (
        <details>
          <summary>Import boundaries</summary>
          <p>
            Only the latest accessible conference is checked. An active meeting, absent transcript, or
            processing artifact has its own empty state; M2O does not silently import an older meeting. API
            entries can differ from an edited Google Docs transcript.
          </p>
        </details>
      )}
    </ProviderRow>
  );
}
