import { useEffect, useState } from "react";
import { api, scoped } from "../../api";
import type { Job, Meeting } from "../../types";

/**
 * Polls a background job every 1.2 s while it is queued or running, then reloads
 * the meeting once it settles. A failed status read is reported separately and
 * never resubmits the job; `readAgain` retries only the read.
 */
export function useJobPolling({
  workspaceId,
  jobId,
  active,
  loadMeeting,
}: {
  workspaceId: string;
  jobId: string | null;
  active: string;
  loadMeeting: (id: string, preserveTranscript?: boolean) => Promise<Meeting | undefined>;
}) {
  const [job, setJob] = useState<Job | null>(null);
  const [jobReadError, setJobReadError] = useState<unknown>(null),
    [jobReading, setJobReading] = useState(false),
    [jobRefresh, setJobRefresh] = useState(0);
  useEffect(() => {
    if (!jobId) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    setJobReadError(null);
    async function poll() {
      setJobReading(true);
      try {
        const state = await api<Job>(scoped(workspaceId, "/jobs/" + jobId), { signal: controller.signal });
        if (controller.signal.aborted) return;
        setJob(state);
        if (["queued", "running"].includes(state.state)) timer = setTimeout(poll, 1200);
        else if (active && active !== "new") await loadMeeting(active, true);
      } catch (e) {
        if (!controller.signal.aborted) setJobReadError(e);
      } finally {
        if (!controller.signal.aborted) setJobReading(false);
      }
    }
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [jobId, workspaceId, active, loadMeeting, jobRefresh]);
  const readAgain = () => setJobRefresh((value) => value + 1);
  return { job, setJob, jobReadError, setJobReadError, jobReading, readAgain };
}
