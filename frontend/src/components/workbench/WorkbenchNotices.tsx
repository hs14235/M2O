import type { Job } from "../../types";
import { ErrorNotice } from "../Feedback";

/**
 * Recovery notices. Each offers a read-only next step: none of them resubmits a
 * save or a job, because the original request may already have been accepted.
 */
export function WorkbenchNotices({
  acceptedSave,
  meetingReadFailed,
  jobReadError,
  job,
  busy,
  loading,
  jobReading,
  onLoadSaved,
  onReloadMeeting,
  onReadJobAgain,
}: {
  acceptedSave: boolean;
  meetingReadFailed: boolean;
  jobReadError: unknown;
  job: Job | null;
  busy: boolean;
  loading: boolean;
  jobReading: boolean;
  onLoadSaved: () => void;
  onReloadMeeting: () => void;
  onReadJobAgain: () => void;
}) {
  return (
    <>
      {acceptedSave && (
        <section className="notice" role="status">
          <p>
            Your transcript save was accepted. Read the saved transcript before continuing; another save is
            not needed.
          </p>
          <button disabled={busy || loading} onClick={onLoadSaved}>
            Load saved transcript
          </button>
        </section>
      )}
      {meetingReadFailed && !acceptedSave && (
        <section className="notice">
          <p>The current meeting could not be loaded. Stored work has not been resubmitted.</p>
          <button disabled={busy || loading} onClick={onReloadMeeting}>
            Load current meeting
          </button>
        </section>
      )}
      {Boolean(jobReadError) && (
        <section className="notice">
          <p>
            Job status could not be refreshed.{" "}
            {job ? "The last confirmed status is " + job.state + "." : "Its current status is unknown."}{" "}
            Reading status does not submit the work again.
          </p>
          <ErrorNotice error={jobReadError} />
          <button disabled={jobReading || busy} onClick={onReadJobAgain}>
            Read job status again
          </button>
        </section>
      )}
    </>
  );
}
