import { useEffect, useRef, useState } from "react";
import { api, scoped } from "../api";
import type { GitHubStatus, User, Workspace } from "../types";
import { ErrorNotice } from "./Feedback";
import ProviderRow, { type ProviderTone } from "./ProviderRow";

export default function GitHubConnection({
  workspace,
  user,
  onChanged,
}: {
  workspace: Workspace;
  user: User;
  onChanged?: () => void;
}) {
  const [status, setStatus] = useState<GitHubStatus | null>(null),
    [repo, setRepo] = useState(""),
    [error, setError] = useState<unknown>(null),
    [busy, setBusy] = useState(false),
    [notice, setNotice] = useState("");
  const pending = useRef<AbortController | null>(null),
    path = scoped(workspace.id, "/integrations/github");
  useEffect(() => {
    const controller = new AbortController();
    api<GitHubStatus>(path, { signal: controller.signal })
      .then((value) => {
        if (!controller.signal.aborted) {
          setStatus(value);
          setRepo(value.destination?.repo || "");
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
  async function bind(event: React.FormEvent) {
    event.preventDefault();
    if (!status) return;
    const controller = new AbortController();
    pending.current?.abort();
    pending.current = controller;
    setBusy(true);
    setError(null);
    setNotice("");
    try {
      const value = await api<GitHubStatus>(path + "/destination", {
        signal: controller.signal,
        method: "POST",
        body: JSON.stringify({ repo, expected_version: status.destination?.version || 0 }),
      });
      if (!controller.signal.aborted) {
        setStatus(value);
        setNotice(
          "Repository binding saved for this workspace. No issue was created. Existing previews require regeneration.",
        );
        onChanged?.();
      }
    } catch (e) {
      if (!controller.signal.aborted) setError(e);
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }
  const [state, tone]: [string, ProviderTone] = !status
    ? ["Checking…", "off"]
    : !status.configured
      ? ["Not set up", "off"]
      : status.destination
        ? ["Connected", "on"]
        : ["Choose a repository", "ready"];
  return (
    <ProviderRow
      id="github"
      name="GitHub"
      summary="Open issues from a preview you approve. Uses the private access token, no sign-in."
      state={state}
      tone={tone}
    >
      <ErrorNotice error={error} />
      {status && !status.configured && (
        <p className="muted">Add a GitHub token and an allowed repository to the private configuration.</p>
      )}
      {status?.destination && (
        <p>
          Sending to <strong>{status.destination.repo}</strong>
        </p>
      )}
      {status?.configured && status.can_manage && (
        <details open={!status.destination}>
          <summary>{status.destination ? "Change repository" : "Choose a repository"}</summary>
          <form className="provider-form" onSubmit={bind}>
            <fieldset disabled={busy}>
              <legend className="sr-only">Workspace GitHub binding</legend>
              <label>
                Repository
                <select required value={repo} onChange={(event) => setRepo(event.target.value)}>
                  <option value="">Choose an allowed repository</option>
                  {user.capabilities.allowed_repos.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>
              <button
                className={status.destination ? undefined : "primary"}
                disabled={!repo || repo === status.destination?.repo}
              >
                Save workspace repository
              </button>
            </fieldset>
          </form>
        </details>
      )}
      {status?.configured && !status.can_manage && (
        <p className="muted">Workspace owners choose the repository outside demo mode.</p>
      )}
      {notice && <p role="status">{notice}</p>}
    </ProviderRow>
  );
}
