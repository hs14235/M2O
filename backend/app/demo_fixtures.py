"""Approved synthetic inputs, shared by the visitor API and extraction checks."""

FIXTURES = {
    "engineering": {
        "department": "engineering",
        "title": "Release 2.4 readiness",
        "people": [
            ("Priya", "Engineering manager"),
            ("Diego", "Backend engineer"),
            ("Sam", "Platform engineer"),
            ("Lena", "QA lead"),
        ],
        "transcript": """Priya: Morning, everyone. Let's get through release readiness for 2.4 in fifteen minutes.
Diego: The approval flow is done. I will add a regression test for stale approvals by Friday.
Priya: Good. Decision: we keep PostgreSQL as the source of truth for review revisions.
Sam: Blocker: the staging OAuth application still has not been approved by security.
Priya: Sam, please chase the security review today and post the ticket in the release channel.
Lena: I ran the smoke suite last night. Two checkout tests are flaky on Safari.
Lena: I will quarantine the flaky checkout tests and file a bug by tomorrow.
Diego: Risk: a retry after an uncertain GitHub response could create duplicate issues.
Priya: Then idempotency keys go in before launch. Diego will add idempotency keys to the GitHub adapter by Wednesday.
Sam: Follow-up: confirm the migration restore drill with the platform team.
Sam: I can run the restore drill on Thursday morning if the snapshot is ready.
Lena: Decision: release notes ship with the build, not after it.
Priya: Lena, please draft the release notes from the approved outcomes by Thursday.
Diego: Risk: the feature flag service has no rollback runbook yet.
Priya: Okay. Go or no-go is Friday at ten. Thanks, everyone.""",
    },
    "hr": {
        "department": "hr",
        "title": "New-hire onboarding sync",
        "people": [
            ("Grace", "HR manager"),
            ("Omar", "People partner"),
            ("Hana", "Onboarding coordinator"),
            ("Felix", "IT support lead"),
        ],
        "transcript": """Grace: Thanks for joining. Three new hires start on Monday, so let's make sure day one is smooth.
Hana: I will send the welcome packs and first-week schedules by Thursday.
Grace: Decision: every new hire gets an onboarding buddy from their own team.
Omar: I will match buddies for all three starters by Friday.
Felix: Blocker: two laptops are still waiting for manager approval in the equipment portal.
Grace: Felix, please escalate the laptop approvals to the hiring managers today.
Hana: The benefits enrollment session is booked for Tuesday afternoon.
Omar: Risk: personal details could end up in external issue bodies if we copy the intake form.
Grace: Decision: intake details stay in the HR system, and only task titles leave it.
Felix: I can set up accounts and badge access on Friday once the laptops arrive.
Hana: Follow-up: confirm the training session dates with the compliance facilitator.
Omar: Risk: the thirty-day manager check-ins are not on anyone's calendar yet.
Grace: Omar will schedule the thirty-day check-ins with each manager by next Wednesday.
Grace: Great. Let's regroup Friday before the starters arrive.""",
    },
    "finance": {
        "department": "finance",
        "title": "October close review",
        "people": [
            ("Victor", "Financial controller"),
            ("Mei", "Accounts payable lead"),
            ("Jordan", "Treasury analyst"),
            ("Ruth", "Audit liaison"),
        ],
        "transcript": """Victor: Let's walk through the October close. We need sign-off by the fifth business day.
Mei: I will reconcile the vendor invoice ledger against the bank feed by Friday.
Victor: Decision: every journal entry over ten thousand needs a second reviewer before posting.
Jordan: Blocker: the purchase order for the cloud contract has no confirmed approver.
Victor: Jordan, please find the budget owner for that purchase order today.
Ruth: The auditors asked for the accruals schedule and the fixed asset roll-forward.
Ruth: I will send the auditors the accruals schedule by Wednesday.
Mei: Risk: an unresolved relative due date could be read as the wrong month.
Victor: Decision: close tasks use calendar dates, never "end of next week".
Jordan: I can prepare the November cash forecast by Monday.
Mei: Follow-up: confirm the intercompany balances with the subsidiary controller.
Ruth: Risk: two expense reports are missing receipts and could fail the audit sample.
Victor: Mei will chase the missing receipts with both employees by Thursday.
Victor: Thanks. Sign-off review is Friday at two.""",
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
# Speakers in the shared examples (the launch stand-up recording and the quiet check-in),
# so every demo directory can name them.
SHARED_PEOPLE = [("Morgan", "Launch lead"), ("Alex", "Mobile engineer"), ("Taylor", "Product designer")]


def scenarios() -> list[dict]:
    return [{"id": key, **value, "synthetic": True} for key, value in FIXTURES.items()]
