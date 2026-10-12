import { meetingStages, type Step } from "../../navigation";
import type { Meeting } from "../../types";

export const stepNames: Record<Step, string> = {
  transcript: "Transcript",
  people: "People",
  review: "Review & Deliver",
  share: "Review & Deliver",
  calendar: "Calendar",
};

/** Meeting title, revision badge and the four-stage stepper. */
export function MeetingHeader({
  meeting,
  step,
  ready,
  onAllMeetings,
  onStep,
}: {
  meeting: Meeting | null;
  step: Step;
  ready: boolean;
  onAllMeetings: () => void;
  onStep: (step: Step) => void;
}) {
  // "share" is a subview of stage 3, so the stepper highlights "review" for it.
  const current = step === "share" ? "review" : step;
  return (
    <>
      <div className="meeting-heading">
        <button className="quiet" onClick={onAllMeetings}>
          All meetings
        </button>
        <span>{meeting?.title || "New meeting"}</span>
        {meeting && <span className="badge">Revision {meeting.current_revision}</span>}
      </div>
      <nav className="stepper" aria-label="Meeting steps">
        <ol>
          {meetingStages.map((value, index) => (
            <li key={value}>
              <button
                aria-current={current === value ? "step" : undefined}
                className={current === value ? "active" : ""}
                disabled={value !== "transcript" && (!meeting || (value !== "people" && !ready))}
                onClick={() => onStep(value)}
              >
                <span aria-hidden="true">{index + 1}</span>
                {stepNames[value]}
              </button>
            </li>
          ))}
        </ol>
      </nav>
    </>
  );
}
