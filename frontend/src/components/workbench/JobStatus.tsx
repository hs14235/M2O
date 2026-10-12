import type { Job, Role } from "../../types";

const modeNames: Record<string, string> = {
  rules: "Rule-based extraction",
  ollama: "Local AI extraction",
  mixed: "Mixed local AI and rule-based extraction",
};

/**
 * Status of the latest background job. For deliveries, a finished job is not a
 * provider receipt; an uncertain write offers a read-only reconcile, never a resend.
 */
export function JobStatus({ job, role, onReconcile }: { job: Job; role: Role; onReconcile: () => void }) {
  const delivery = job.kind?.includes("publish");
  return (
    <div className={"notice " + (job.state === "failed" ? "error" : "")} role="status">
      <strong>
        {delivery ? "Delivery processing" : "Job"} {job.state}
      </strong>
      {delivery && <span> · Check the provider receipt for its actual result.</span>}
      {job.error_code && (
        <span>
          {" "}
          ·{" "}
          {job.kind === "extract"
            ? "Extraction did not finish. You can retry or ask the application operator to check the worker."
            : "The operation did not finish. Check its receipt before trying another delivery."}
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
