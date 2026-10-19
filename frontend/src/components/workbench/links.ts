import type { MouseEvent } from "react";
import { routePath } from "../../navigation";

/** The Review step opened on one outcome (ReviewStep reads ?outcome=). */
export function reviewOutcomePath(workspaceId: string, meetingId: string, outcomeId: string): string {
  return (
    routePath(workspaceId, "meetings", meetingId, "review") +
    "?" +
    new URLSearchParams({ outcome: outcomeId })
  );
}

/** A primary click without modifiers, which the app handles; others keep the browser's link behavior. */
export function isPlainClick(event: MouseEvent): boolean {
  return event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey;
}
