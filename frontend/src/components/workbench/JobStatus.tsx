import type { Job, Role } from "../../types";

const modeNames: Record<string, string> = {
  rules: "Rule-based extraction",
  ollama: "Local AI extraction",
  mixed: "Mixed local AI and rule-based extraction",
};

// The recording is deleted when transcription fails, so every message says what to upload next.
const transcriptionErrors: Record<string, string> = {
  service_413: "The recording is longer or larger than this installation allows. Upload a shorter recording.",
  service_422: "No speech was detected in the recording.",
  TranscriptionUnavailable:
    "Transcription is not installed on this server. Ask the application operator to install it.",
};

function formatDuration(seconds: number) {
  return seconds < 90 ? Math.round(seconds) + " s" : Math.round(seconds / 60) + " min";
}

function failureMessage(job: Job) {
  if (job.kind === "transcribe")
    return (
      transcriptionErrors[job.error_code ?? ""] ??
      "Transcription did not finish. The recording was not kept; you can upload it again."
    );
  return job.kind === "extract"
    ? "Extraction did not finish. You can retry or ask the application operator to check the worker."
    : "The operation did not finish. Check its receipt before trying another delivery.";
}

/**
 * Status of the latest background job. For deliveries, a finished job is not a
 * provider receipt; an uncertain write offers a read-only reconcile, never a resend.
 */
export function JobStatus({ job, role, onReconcile }: { job: Job; role: Role; onReconcile: () => void }) {
  const delivery = job.kind?.includes("publish");
  const transcription = job.kind === "transcribe";
  return (
    <div className={"notice " + (job.state === "failed" ? "error" : "")} role="status">
      <strong>
        {delivery ? "Delivery processing" : transcription ? "Transcription" : "Job"} {job.state}
      </strong>
      {delivery && <span> · Check the provider receipt for its actual result.</span>}
      {transcription && ["queued", "running"].includes(job.state) && (
        <span>
          {" "}
          · Your recording is being transcribed on this machine. Long meetings take several minutes.
        </span>
      )}
      {job.error_code && <span> · {failureMessage(job)}</span>}
      {transcription && job.result?.duration_seconds !== undefined && (
        <span>
          {" "}
          · {formatDuration(job.result.duration_seconds)} of audio transcribed with the {job.result.model}{" "}
          model
        </span>
      )}
      {job.result?.mode && (
        <span>
          {" "}
          · {modeNames[job.result.mode] ?? "Extraction mode: " + job.result.mode} · {job.result.created} new
          outcomes
        </span>
      )}
      {job.result?.coverage && (
        <details>
          <summary>Processing details</summary>
          <p>
            Processed {job.result.coverage.processed_chunks}/{job.result.coverage.total_chunks} chunks.{" "}
            {job.result.coverage.warnings.join(" ")}
          </p>
        </details>
      )}
      {job.result?.results?.map((result, i) => (
        <p key={i}>
          {result.status}
          {result.url && (
            <>
              {" "}
              ·{" "}
              <a href={result.url} target="_blank" rel="noopener noreferrer">
                Open delivered outcome
              </a>
            </>
          )}
        </p>
      ))}
      {job.kind === "publish" &&
        job.result?.state === "uncertain" &&
        ["owner", "reviewer"].includes(role) && (
          <button onClick={onReconcile}>Check uncertain delivery status</button>
        )}
    </div>
  );
}
