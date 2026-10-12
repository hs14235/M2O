import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { Job } from "../../types";
import { JobStatus } from "./JobStatus";

const transcription = (overrides: Partial<Job>): Job => ({
  id: "audio-job",
  kind: "transcribe",
  state: "failed",
  error_code: null,
  result: null,
  ...overrides,
});

it.each([
  ["service_413", /longer or larger than this installation allows/],
  ["service_422", /No speech was detected/],
  ["TranscriptionUnavailable", /not installed on this server/],
  ["service_500", /recording was not kept; you can upload it again/],
])("explains a failed transcription (%s) without delivery wording", (code, message) => {
  render(<JobStatus job={transcription({ error_code: code })} role="owner" onReconcile={vi.fn()} />);
  expect(screen.getByText(message)).toBeInTheDocument();
  expect(screen.queryByText(/receipt/)).not.toBeInTheDocument();
});

it("reports a finished transcription in seconds or minutes", () => {
  const view = render(
    <JobStatus
      job={transcription({ state: "completed", result: { duration_seconds: 31, model: "small" } })}
      role="owner"
      onReconcile={vi.fn()}
    />,
  );
  expect(screen.getByText(/31 s of audio transcribed with the small model/)).toBeInTheDocument();
  view.rerender(
    <JobStatus
      job={transcription({ state: "completed", result: { duration_seconds: 1800, model: "small" } })}
      role="owner"
      onReconcile={vi.fn()}
    />,
  );
  expect(screen.getByText(/30 min of audio transcribed/)).toBeInTheDocument();
});
