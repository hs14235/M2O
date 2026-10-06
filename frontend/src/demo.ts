import type { Department } from "./types";

export const examples: Record<Department, { title: string; text: string; purpose: string }> = {
  engineering: {
    title: "Release readiness",
    purpose: "Track delivery, blockers, decisions and follow-ups.",
    text: "Alex: Action: I will add a regression test for stale approvals by Friday.\nMorgan: Decision: Use PostgreSQL as the source of truth for review revisions.\nTaylor: Blocker: The staging OAuth application has not been approved.\nAlex: Follow-up: Confirm the migration restore drill with the platform team.\nMorgan: Risk: A retry after an uncertain GitHub response could create duplicate issues.\n- [x] Ship the old prototype",
  },
  hr: {
    title: "Onboarding coordination",
    purpose: "Coordinate onboarding and policies with restricted meeting access.",
    text: "Alex: Action: I will prepare the new-hire onboarding checklist by Monday.\nMorgan: Decision: Share onboarding tasks with the People Operations workspace.\nTaylor: Blocker: The equipment request is waiting for manager approval.\nAlex: Follow-up: Confirm the training session dates with the facilitator.\nMorgan: Risk: Personal details should not be included in external issue bodies.\nAction: Do not publish private interview feedback.",
  },
  finance: {
    title: "Month-end controls",
    purpose: "Review close activities, approvals, control risks and ownership.",
    text: "Alex: Action: I will reconcile the synthetic invoice ledger by Friday.\nMorgan: Decision: Require a reviewer before publishing close tasks.\nTaylor: Blocker: The sample purchase order has no confirmed approver.\nAlex: Follow-up: Confirm the close calendar with the finance lead.\nMorgan: Risk: An unresolved relative due date could be interpreted incorrectly.",
  },
};
