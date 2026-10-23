import { useEffect, useRef, useState } from "react";
import { openConsent, useOnReturn } from "../consent";
import { api, scoped } from "../api";
import type { Workspace } from "../types";
import { ErrorNotice } from "./Feedback";
import ProviderRow, { type ProviderTone } from "./ProviderRow";
import SlackActions from "./SlackActions";

export interface SlackStatus {
  configured: boolean;
  can_manage: boolean;
  state: string;
  version: number | null;
  account: { team_id: string; team_name: string } | null;
  destination: { channel_id: string; channel_name: string } | null;
  can_create: boolean;
  can_update: boolean;
  can_reconcile: boolean;
  can_link: boolean;
  can_capture_meeting: boolean;
  can_change_my_plan: boolean;
  delivery_reasons: string[];
  interaction_reasons: string[];
}
const reasons: Record<string, string> = {
  needs_configuration: "The operator must configure the Slack app and protected credential storage.",
  demo_mode: "Demo mode allows local work and blocks Slack writes.",
  owner_required: "This connection is managed by a workspace owner.",
  not_connected: "Connect the Slack account before choosing a channel.",
  reauthorization_required: "Reconnect Slack to renew access.",
  missing_scopes: "Reconnect with the app's required channel and message permissions.",
  unverified_destination: "Verify a channel containing the M2O app.",
};

export default function SlackConnection({
  workspace,
  onChanged,
}: {
  workspace: Workspace;
  onChanged?: () => void;
}) {
  const [status, setStatus] = useState<SlackStatus | null>(null),
    [channel, setChannel] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(null),
    [notice, setNotice] = useState("");
  const pending = useRef<AbortController | null>(null),
    path = scoped(workspace.id, "/integrations/slack");
  // Consent finishes in another tab; read the status again when this one is back in view.
  useOnReturn(() => {
    api<SlackStatus>(path)
      .then(setStatus)
      .catch(() => undefined);
  });
  useEffect(() => {
    const controller = new AbortController();
    api<SlackStatus>(path, { signal: controller.signal })
      .then((value) => {
        if (!controller.signal.aborted) {
          setStatus(value);
          setChannel(value.destination?.channel_id || "");
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e);
      });
    return () => {
      controller.abort();
      pending.current?.abort();
    };
  }, [path]);
  async function run(operation: (signal: AbortSignal) => Promise<void>) {
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    setBusy(true);
    setError(null);
    setNotice("");
    try {
      await operation(controller.signal);
    } catch (e) {
      if (!controller.signal.aborted) setError(e);
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }
  const connected = status?.state === "connected";
  const [state, tone]: [string, ProviderTone] = !status
    ? ["Checking…", "off"]
    : !status.configured
      ? ["Not set up", "off"]
      : status.state === "disconnected"
        ? ["Not connected", "ready"]
        : !connected
          ? ["Reconnect needed", "attention"]
          : status.destination
            ? ["Connected", "on"]
            : ["Choose a channel", "ready"];
  return (
    <ProviderRow
      id="slack"
      name="Slack"
      summary="Post or update a reviewed message in one channel you verify."
      state={state}
      tone={tone}
      action={
        status && (
          <button
            className={connected ? undefined : "primary"}
            disabled={busy || !status.configured || !status.can_manage}
            onClick={() =>
              run((signal) =>
                openConsent(async () => {
                  const value = await api<{ url: string }>(path + "/connect", { signal, method: "POST" });
                  return signal.aborted ? undefined : value.url;
                }),
              )
            }
          >
            {status.state === "disconnected" ? "Connect Slack" : "Reconnect Slack"}
          </button>
        )
      }
    >
      <ErrorNotice error={error} />
      {status && (
        <>
          {status.delivery_reasons
            .filter((reason) => reason !== "not_connected")
            .map((reason) => (
              <p className="muted" key={reason}>
                {reasons[reason] || "This Slack connection needs attention before delivery."}
              </p>
            ))}
          {status.account && (
            <p>
              Workspace <strong>{status.account.team_name}</strong>
              {status.destination && (
                <>
                  {" "}
                  · sending to <strong>#{status.destination.channel_name}</strong>
                </>
              )}
            </p>
          )}
          {status.state !== "disconnected" && status.can_manage && (
            <div className="actions">
              <button
                className="quiet"
                disabled={busy}
                onClick={() =>
                  run(async (signal) => {
                    await api(path, { signal, method: "DELETE" });
                    const value = await api<SlackStatus>(path, { signal });
                    if (!signal.aborted) {
                      setStatus(value);
                      setChannel("");
                      setNotice("Disconnected from this workspace. No message was removed.");
                      onChanged?.();
                    }
                  })
                }
              >
                Disconnect Slack from this workspace
              </button>
            </div>
          )}
          {status.state === "connected" && status.can_manage && (
            <details open={!status.destination}>
              <summary>{status.destination ? "Change channel" : "Choose a channel"}</summary>
              <p className="muted">
                Invite M2O to the channel, then copy its Channel ID from the channel details in Slack.
              </p>
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  void run(async (signal) => {
                    const value = await api<SlackStatus>(path + "/destination", {
                      signal,
                      method: "POST",
                      body: JSON.stringify({
                        channel_id: channel.trim().toUpperCase(),
                        expected_version: status.version,
                      }),
                    });
                    if (!signal.aborted) {
                      setStatus(value);
                      setNotice("Channel verified and saved. No Slack message was sent.");
                      onChanged?.();
                    }
                  });
                }}
              >
                <label>
                  Slack channel ID
                  <input
                    required
                    pattern="C[A-Z0-9]{7,63}"
                    maxLength={64}
                    value={channel}
                    disabled={busy}
                    onChange={(event) => setChannel(event.target.value.toUpperCase())}
                    placeholder="C…"
                  />
                </label>
                <button disabled={busy || !channel || !status.version}>Verify Slack channel</button>
              </form>
            </details>
          )}
          {connected && <SlackActions key={status.version} workspace={workspace} />}
        </>
      )}
      {notice && <p role="status">{notice}</p>}
    </ProviderRow>
  );
}
