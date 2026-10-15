import { useEffect, useRef, useState } from "react";
import { api, scoped } from "../api";
import type { HandoffStage } from "../navigation";
import type { Meeting, Workspace } from "../types";
import { ErrorNotice } from "./Feedback";
import { PayloadInspection } from "./ExactPayload";

export interface LinkedInPublishingStatus {
  configured: boolean;
  state: "connected" | "reauthorization_required" | "not_connected";
  author: string | null;
  expires_at: string | null;
  can_connect: boolean;
  can_publish: boolean;
  can_draft: boolean;
}
interface LinkedInDraft {
  id: string;
  version: number;
}
interface LinkedInPreview {
  id: string;
  audience: "CONNECTIONS" | "PUBLIC";
  payload: { commentary: string; visibility: string };
  payload_hash: string;
  expires_at: string;
}
interface LinkedInReceipt {
  operation_id: string;
  state: string;
  created_at: string;
  result: { status: string; post_id?: string; error?: string } | null;
}

export const audienceNames: Record<LinkedInPreview["audience"], string> = {
  CONNECTIONS: "Your connections only",
  PUBLIC: "Anyone on or off LinkedIn",
};

/** The member post a reviewer starts from; they edit it before anything is shared. */
export function defaultPostText(meeting: Meeting, selected: string[]) {
  const titles = meeting.tasks.filter((item) => selected.includes(item.id)).map((item) => "• " + item.title);
  return [`Next steps from "${meeting.title}":`, "", ...titles].join("\n");
}

export function postUrl(postId: string) {
  return "https://www.linkedin.com/feed/update/" + encodeURIComponent(postId) + "/";
}

/**
 * Member post from reviewed outcomes. The reviewer edits the text, confirms it may be
 * shared, then approves the exact stored preview, including its audience. A queued job
 * is not a post; only a receipt with a post ID links to LinkedIn.
 */
export function LinkedInPublisher({
  workspace,
  meeting,
  selected,
  stage,
  onStage,
  onJob,
  onConnections,
}: {
  workspace: Workspace;
  meeting: Meeting;
  selected: string[];
  stage: HandoffStage;
  onStage: (stage: HandoffStage) => void;
  onJob: (id: string) => void;
  onConnections: () => void;
}) {
  const [status, setStatus] = useState<LinkedInPublishingStatus | null>(null),
    [text, setText] = useState(() => defaultPostText(meeting, selected)),
    [edited, setEdited] = useState(false),
    [disclosure, setDisclosure] = useState(false);
  const [preview, setPreview] = useState<{ key: string; value: LinkedInPreview } | null>(null),
    [receipts, setReceipts] = useState<LinkedInReceipt[]>([]),
    [loaded, setLoaded] = useState(false),
    [refreshKey, setRefreshKey] = useState(0),
    [receiptError, setReceiptError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(null),
    request = useRef<AbortController | null>(null);
  const key = JSON.stringify([
    workspace.id,
    meeting.id,
    meeting.current_revision,
    selected,
    meeting.tasks.map((item) => [item.id, item.version, item.status]),
    text,
    disclosure,
  ]);
  const currentKey = useRef(key);
  currentKey.current = key;
  const currentStage = useRef(stage),
    stageEpoch = useRef(0);
  if (currentStage.current !== stage) {
    currentStage.current = stage;
    stageEpoch.current += 1;
  }
  const stored =
    preview?.key === key && Date.parse(preview.value.expires_at) > Date.now() ? preview.value : null;
  const pending = receipts.some((receipt) => ["queued", "sending"].includes(receipt.state));
  const eligible =
    selected.length > 0 &&
    selected.length <= 30 &&
    selected.every((id) => meeting.tasks.some((item) => item.id === id && item.status === "approved"));
  const length = text.length,
    validText = text.trim().length > 0 && length <= 3000;
  // Follow the outcome selection until the reviewer starts editing the text.
  const suggested = defaultPostText(meeting, selected);
  useEffect(() => {
    if (!edited) setText(suggested);
  }, [suggested, edited]);
  useEffect(() => {
    const controller = new AbortController();
    api<LinkedInPublishingStatus>(scoped(workspace.id, "/integrations/linkedin/publishing"), {
      signal: controller.signal,
    })
      .then((value) => {
        if (!controller.signal.aborted) setStatus(value);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e);
      });
    return () => {
      controller.abort();
      request.current?.abort();
    };
  }, [workspace.id]);
  useEffect(() => {
    const controller = new AbortController();
    async function refresh() {
      try {
        const value = await api<LinkedInReceipt[]>(
          scoped(workspace.id, "/meetings/" + meeting.id + "/deliveries/linkedin"),
          { signal: controller.signal },
        );
        if (!controller.signal.aborted) {
          setReceipts(value);
          setLoaded(true);
          setReceiptError(null);
        }
      } catch (e) {
        if (!controller.signal.aborted) setReceiptError(e);
      }
    }
    void refresh();
    const timer = pending ? setInterval(() => void refresh(), 3000) : undefined;
    return () => {
      controller.abort();
      clearInterval(timer);
    };
  }, [workspace.id, meeting.id, refreshKey, pending, stage]);
  useEffect(() => {
    if (!preview) return;
    const timer = setTimeout(
      () => setPreview(null),
      Math.max(0, Date.parse(preview.value.expires_at) - Date.now()),
    );
    return () => clearTimeout(timer);
  }, [preview]);
  async function run(operation: (signal: AbortSignal) => Promise<void>) {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
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
  async function prepare() {
    const requestedEpoch = stageEpoch.current;
    if (!eligible || !validText || !disclosure) return;
    const requested = key;
    setPreview(null);
    await run(async (signal) => {
      const draft = await api<LinkedInDraft>(
        scoped(workspace.id, "/meetings/" + meeting.id + "/linkedin/drafts"),
        {
          signal,
          method: "POST",
          body: JSON.stringify({
            kind: "post",
            text,
            versions: Object.fromEntries(
              selected.map((id) => [id, meeting.tasks.find((item) => item.id === id)!.version]),
            ),
          }),
        },
      );
      const value = await api<LinkedInPreview>(
        scoped(workspace.id, "/meetings/" + meeting.id + "/linkedin/preview"),
        {
          signal,
          method: "POST",
          body: JSON.stringify({
            draft_id: draft.id,
            expected_draft_version: draft.version,
            disclosure_confirmed: true,
          }),
        },
      );
      if (!signal.aborted && currentKey.current === requested && stageEpoch.current === requestedEpoch) {
        setPreview({ key: requested, value });
        onStage("preview");
      }
    });
  }
  async function approve() {
    const requestedEpoch = stageEpoch.current;
    if (!stored) return;
    await run(async (signal) => {
      const value = await api<{ job_id: string | null }>(
        scoped(workspace.id, "/linkedin/proposals/" + stored.id + "/approve"),
        { signal, method: "POST", body: JSON.stringify({ payload_hash: stored.payload_hash }) },
      );
      if (!signal.aborted) {
        setPreview(null);
        setRefreshKey((count) => count + 1);
        if (value.job_id) onJob(value.job_id);
        if (stageEpoch.current === requestedEpoch) onStage("receipt");
      }
    });
  }
  return (
    <section hidden={stage === "choose"} className="panel publisher" aria-labelledby="linkedin-publish-title">
      <span className="eyebrow">LinkedIn post</span>
      <h2 id="linkedin-publish-title">
        {stage === "preview"
          ? "Review the exact post."
          : stage === "receipt"
            ? "Your LinkedIn posts from this meeting."
            : "Share what the meeting decided."}
      </h2>
      <ErrorNotice error={error} />
      {stage === "configure" && status && !status.can_publish && (
        <div className="notice">
          <p>
            {!status.configured
              ? "LinkedIn posting is not set up on this installation. You can still copy the text below."
              : status.state === "reauthorization_required"
                ? "Your LinkedIn publishing access expired or changed. Reconnect it in Connections."
                : "Connect LinkedIn publishing in Connections first. Owners and reviewers can post."}
          </p>
          <button type="button" onClick={onConnections}>
            Open connections
          </button>
        </div>
      )}
      {stage === "configure" && (
        <fieldset disabled={busy}>
          <legend className="sr-only">Prepare LinkedIn post</legend>
          <label>
            Post text
            <textarea
              rows={8}
              maxLength={3000}
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                setEdited(true);
              }}
            />
          </label>
          <p className="muted" aria-live="polite">
            {length} / 3000 characters
          </p>
          <label className="check">
            <input type="checkbox" checked={disclosure} onChange={(e) => setDisclosure(e.target.checked)} />I
            reviewed this text for private names, figures and details, and approve sharing it on LinkedIn
          </label>
          <p className="muted">
            Preparing the preview saves a draft and does not post. The preview shows who will see the post.
          </p>
          <button
            className="primary"
            disabled={!status?.can_publish || !eligible || !validText || !disclosure}
            onClick={prepare}
          >
            Generate exact LinkedIn preview
          </button>
        </fieldset>
      )}
      {stage === "preview" &&
        (stored ? (
          <div className="preview">
            <p role="status">
              Audience: <strong>{audienceNames[stored.audience]}</strong> · expires{" "}
              {new Date(stored.expires_at).toLocaleTimeString()}
            </p>
            <article className="exact-payload">
              <h3>Stored post text</h3>
              <pre className="payload-text">{stored.payload.commentary}</pre>
              <PayloadInspection payload={stored.payload} hash={stored.payload_hash} />
            </article>
            <button className="primary" disabled={busy || !status?.can_publish} onClick={approve}>
              Approve exact preview and post to LinkedIn
            </button>
          </div>
        ) : (
          <p className="notice">
            There is no current preview in this browser session. Return to preparation after a refresh, expiry
            or source change.
          </p>
        ))}
      {stage === "receipt" && (
        <section aria-label="LinkedIn post receipts">
          {Boolean(receiptError) && (
            <>
              <ErrorNotice error={receiptError} />
              <p>Post history could not be refreshed. A failed read does not mean a post was not made.</p>
              <button
                onClick={() => {
                  setReceiptError(null);
                  setRefreshKey((count) => count + 1);
                }}
              >
                Refresh LinkedIn receipts
              </button>
            </>
          )}
          {!loaded
            ? !receiptError && <p role="status">Loading recorded posts…</p>
            : !receipts.length
              ? !receiptError && <p>No recorded LinkedIn post is available for this meeting.</p>
              : receipts.map((receipt) => (
                  <article className="preview" key={receipt.operation_id}>
                    <h3>{new Date(receipt.created_at).toLocaleString()}</h3>
                    <p role="status">
                      {receipt.state}
                      {receipt.result ? " · " + receipt.result.status : ""}
                    </p>
                    {receipt.result?.post_id && (
                      <a href={postUrl(receipt.result.post_id)} target="_blank" rel="noopener noreferrer">
                        Open the post on LinkedIn
                      </a>
                    )}
                    {receipt.result?.error && <p>{receipt.result.error}</p>}
                    {receipt.state === "uncertain" && (
                      <p className="notice">
                        LinkedIn did not confirm this post. Check your LinkedIn activity before posting again;
                        M2O never resends it automatically.
                      </p>
                    )}
                  </article>
                ))}
        </section>
      )}
    </section>
  );
}
