import { useEffect, useRef, useState } from "react";
import { openConsent, useOnReturn } from "../consent";
import { api, scoped } from "../api";
import type { Workspace } from "../types";
import { ErrorNotice } from "./Feedback";
import ProviderRow, { type ProviderTone } from "./ProviderRow";

interface Status {
  configured: boolean;
  can_manage: boolean;
  state: "disconnected" | "connected" | "reauthorization_required";
  version: number | null;
  destination: {
    resource_id: string;
    name: string;
    url: string;
    project_key: string;
    project_name: string;
  } | null;
}
interface Site {
  id: string;
  name: string;
  url: string;
}

export default function JiraConnection({
  workspace,
  onChanged,
}: {
  workspace: Workspace;
  onChanged?: () => void;
}) {
  const [status, setStatus] = useState<Status | null>(null),
    [sites, setSites] = useState<Site[]>([]);
  const [site, setSite] = useState(""),
    [project, setProject] = useState("");
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(null),
    [notice, setNotice] = useState("");
  const request = useRef<AbortController | null>(null);
  const path = scoped(workspace.id, "/integrations/jira");
  // Consent finishes in another tab; read the status again when this one is back in view.
  useOnReturn(() => {
    api<Status>(path)
      .then(setStatus)
      .catch(() => undefined);
  });
  useEffect(() => {
    const controller = new AbortController();
    api<Status>(path, { signal: controller.signal })
      .then((value) => {
        if (!controller.signal.aborted) {
          setStatus(value);
          setProject(value.destination?.project_key || "");
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e);
      });
    return () => {
      controller.abort();
      request.current?.abort();
    };
  }, [path]);
  async function run(operation: (signal: AbortSignal) => Promise<void>) {
    const controller = new AbortController();
    request.current = controller;
    setBusy(true);
    setError(null);
    setNotice("");
    try {
      await operation(controller.signal);
    } catch (e) {
      if (!controller.signal.aborted) {
        setError(e);
        try {
          const result = await api<Status>(path, { signal: controller.signal });
          if (!controller.signal.aborted) {
            setStatus(result);
            onChanged?.();
          }
        } catch {
          /* Keep the original error if the status request also fails. */
        }
      }
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }
  const connected = status?.state === "connected";
  const [state, tone]: [string, ProviderTone] = !status
    ? ["Checking…", "off"]
    : !status.configured
      ? ["Not set up", "off"]
      : status.state === "reauthorization_required"
        ? ["Reconnect needed", "attention"]
        : !connected
          ? ["Not connected", "ready"]
          : status.destination
            ? ["Connected", "on"]
            : ["Choose a project", "ready"];
  const connect = (
    <button
      className={connected ? undefined : "primary"}
      disabled={busy || !status?.configured || !status.can_manage}
      onClick={() =>
        run((signal) =>
          openConsent(async () => {
            const result = await api<{ url: string }>(path + "/connect", { method: "POST", signal });
            return signal.aborted ? undefined : result.url;
          }),
        )
      }
    >
      {status?.state === "disconnected" ? "Connect Jira" : "Reconnect Jira"}
    </button>
  );
  return (
    <ProviderRow
      id="jira"
      name="Jira"
      summary="Create or update issues from a preview you approve."
      state={state}
      tone={tone}
      action={status && connect}
    >
      <ErrorNotice error={error} />
      {status && !status.configured && (
        <p className="muted">Add the Jira app's client ID and secret to the private configuration.</p>
      )}
      {status && status.configured && !status.can_manage && (
        <p className="muted">Workspace owners connect Jira outside demo mode.</p>
      )}
      {status?.state === "connected" && (
        <p>
          {status.destination ? (
            <>
              Sending to{" "}
              <strong>
                {status.destination.name} / {status.destination.project_key}
              </strong>{" "}
              ({status.destination.project_name})
            </>
          ) : (
            "Account connected. Pick the site and project issues should go to."
          )}
        </p>
      )}
      {status && status.state !== "disconnected" && (
        <div className="actions">
          {status?.state === "connected" && status.can_manage && (
            <button
              disabled={busy}
              onClick={() =>
                run(async (signal) => {
                  const result = await api<Site[]>(path + "/sites", { signal });
                  if (!signal.aborted) {
                    setSites(result);
                    setSite(result[0]?.id || "");
                    setNotice(
                      result.length
                        ? "Select a site and enter its space key."
                        : "No Jira sites granted the required permissions. Check access and reconnect.",
                    );
                  }
                })
              }
            >
              Find authorized Jira sites
            </button>
          )}
          <button
            className="quiet"
            disabled={busy || workspace.role !== "owner"}
            onClick={() =>
              run(async (signal) => {
                await api(path, { method: "DELETE", signal });
                const result = await api<Status>(path, { signal });
                if (!signal.aborted) {
                  setStatus(result);
                  setSites([]);
                  setSite("");
                  setProject("");
                  onChanged?.();
                  setNotice(
                    "Disconnected from this workspace. Other workspaces keep their own access. Revoke the Atlassian grant in your Atlassian connected-app settings if needed.",
                  );
                }
              })
            }
          >
            Disconnect from this workspace
          </button>
        </div>
      )}
      {status?.state === "connected" && status.can_manage && (
        <>
          {sites.length > 0 && (
            <form
              onSubmit={(event) => {
                event.preventDefault();
                void run(async (signal) => {
                  const result = await api<Status>(path + "/destination", {
                    method: "POST",
                    signal,
                    body: JSON.stringify({
                      resource_id: site,
                      project_key: project.trim().toUpperCase(),
                      expected_version: status.version,
                    }),
                  });
                  if (!signal.aborted) {
                    setStatus(result);
                    onChanged?.();
                    setNotice("Destination verified and saved. No issue was created.");
                  }
                });
              }}
            >
              <label htmlFor="jira-site">Authorized Jira site</label>
              <select
                id="jira-site"
                value={site}
                disabled={busy}
                onChange={(event) => setSite(event.target.value)}
              >
                {sites.map((value) => (
                  <option key={value.id} value={value.id}>
                    {value.name} — {value.url}
                  </option>
                ))}
              </select>
              <label htmlFor="jira-project">Space key</label>
              <input
                id="jira-project"
                value={project}
                disabled={busy}
                required
                maxLength={40}
                pattern="[A-Za-z][A-Za-z0-9_]{1,39}"
                onChange={(event) => setProject(event.target.value)}
                autoComplete="off"
              />
              <button disabled={busy || !site || !project.trim()} type="submit">
                Verify and save destination
              </button>
            </form>
          )}
        </>
      )}
      {(busy || notice) && <p role="status">{busy ? "Checking Jira…" : notice}</p>}
    </ProviderRow>
  );
}
