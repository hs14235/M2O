"""Approved synthetic inputs, shared by the visitor API and extraction checks."""

FIXTURES = {
    "engineering": {
        "department": "engineering",
        "title": "Release readiness",
        "transcript": """Alex: Action: I will add a regression test for stale approvals by Friday.
Morgan: Decision: Use PostgreSQL as the source of truth for review revisions.
Taylor: Blocker: The staging OAuth application has not been approved.
Alex: Follow-up: Confirm the migration restore drill with the platform team.
Morgan: Risk: A retry after an uncertain GitHub response could create duplicate issues.
- [x] Ship the old prototype""",
    },
    "hr": {
        "department": "hr",
        "title": "Onboarding coordination",
        "transcript": """Alex: Action: I will prepare the new-hire onboarding checklist by Monday.
Morgan: Decision: Share onboarding tasks with the People Operations workspace.
Taylor: Blocker: The equipment request is waiting for manager approval.
Alex: Follow-up: Confirm the training session dates with the facilitator.
Morgan: Risk: Personal details should not be included in external issue bodies.
Action: Do not publish private interview feedback.""",
    },
    "finance": {
        "department": "finance",
        "title": "Month-end controls",
        "transcript": """Alex: Action: I will reconcile the synthetic invoice ledger by Friday.
Morgan: Decision: Require a reviewer before publishing close tasks.
Taylor: Blocker: The sample purchase order has no confirmed approver.
Alex: Follow-up: Confirm the close calendar with the finance lead.
Morgan: Risk: An unresolved relative due date could be interpreted incorrectly.""",
    },
    "no-outcomes": {
        "department": None,
        "title": "A quiet check-in",
        "transcript": """Alex: Good morning, everyone.
Morgan: Thanks for joining. We are sharing an update today.
Taylor: Everything is as reported yesterday. Have a good day.""",
    },
    # Whisper's words, unedited, from scripts/make_demo_audio.py (evals/audio/standup.whisper.json).
    # Speaker names come from the script: Whisper does not identify speakers.
    "recording": {
        "department": None,
        "title": "Launch stand-up recording",
        "transcript": """Morgan: Good morning. Let's keep this quick and go through the launch checklist.
Alex: I will finish the release notes by Thursday.
Morgan: Thanks. Decision, we ship the mobile update on Monday, not Friday.
Alex: Blocker, the payment sandbox keys still have not been approved.
Morgan: I will ask the finance team to approve the sandbox keys today.
Alex: If the approval slips, the App Store review could miss the launch window.
Morgan: Follow-up, confirm the store review timeline with the platform team.
Alex: Taylor will update the onboarding screenshots by Wednesday.
Morgan: Great. That's everything. Thanks, everyone.""",
        "recording": {
            "audio": "/demo/standup.m4a",
            "model": "faster-whisper large-v3 (int8, CPU)",
            "wer": 0.011,
            "date": "2026-10-19",
        },
    },
}

DEPARTMENTS = {"engineering": "Engineering", "hr": "People Operations", "finance": "Finance Control"}


def scenarios() -> list[dict]:
    return [{"id": key, **value, "synthetic": True} for key, value in FIXTURES.items()]
