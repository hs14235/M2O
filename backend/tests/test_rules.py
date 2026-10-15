from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.chunking import to_chunk_records
from app.schemas import IndexInput, ItemCandidate, LoginInput, ModelOutput
from app.services.errors import ServiceError
from app.services.shared import normalize_source_i
from app.tasks import _parse_tasks_json, extract_tasks_rules


def test_rules_finds_actions():
    tasks = extract_tasks_rules(
        [
            {"i": 0, "id": str(uuid4()), "text": "Action: Alex to wire FastAPI endpoints by Friday."},
            {"i": 1, "text": "Status: We discussed timelines."},
        ]
    )
    assert len(tasks) == 1
    assert tasks[0]["assignee_hint"] == "Alex"
    assert tasks[0]["due_hint"] == "by Friday"
    assert "Wire FastAPI" in tasks[0]["title"]


def test_all_outcome_types_and_speaker_owner():
    chunks = to_chunk_records(
        "Alex: Action: I will review the API by Monday.\nMorgan: Decision: Use PostgreSQL.\nTaylor: Blocker: Access is pending.\nAlex: Follow-up: Confirm owner.\nMorgan: Risk: The budget is uncertain."
    )
    tasks = extract_tasks_rules(chunks)
    assert {task["kind"] for task in tasks} == {"action", "decision", "blocker", "follow_up", "risk"}
    assert tasks[0]["assignee_hint"] == "Alex"
    assert tasks[0]["due_hint"] == "by Monday"


@pytest.mark.parametrize(
    "text",
    [
        "- [x] Ship API",
        "Action: Do not share private notes",
        "Action: The report is already completed",
        "Action: The launch is cancelled",
        "Status: Nothing to do",
    ],
)
def test_no_completed_negated_or_unlabelled_tasks(text):
    assert extract_tasks_rules([{"i": 0, "text": text}]) == []


def test_chunk_byte_bound_and_unicode():
    text = "Alex: " + "🙂" * 1000 + "\nMorgan: Decision: Keep evidence."
    chunks = to_chunk_records(text)
    assert all(len(row["text"].encode()) <= 1200 for row in chunks)
    assert all(row["speaker"] == "Alex" for row in chunks[:-1])
    assert chunks[-1]["speaker"] == "Morgan"
    assert chunks[-1]["start_line"] == 2
    assert "".join(row["text"] for row in chunks[:-1]).count("🙂") == 1000


def test_actual_sources_cannot_be_reinterpreted_as_local_positions():
    assert normalize_source_i(9, [1, 9]) == 9
    for invalid in (999, "9", True, None):
        with pytest.raises(ServiceError):
            normalize_source_i(invalid, [1, 9])


def test_strict_model_json_and_confidence():
    assert _parse_tasks_json('{"tasks":[{"title":"Hallucination","source_i":999}]}') == []
    with pytest.raises(ValidationError):
        ItemCandidate(title="Unsafe", confidence=2, source_ids=[str(uuid4())])
    assert ModelOutput.model_validate_json('{"tasks":[]}').tasks == []


def test_contract_rejects_extra_fields_invalid_timezone_and_preserves_password():
    with pytest.raises(ValidationError):
        IndexInput(meeting_id="valid", transcript="Action: Ship", unexpected=True)
    with pytest.raises(ValidationError):
        IndexInput(meeting_id="../escape", transcript="Action: Ship")
    with pytest.raises(ValidationError):
        IndexInput(meeting_id="valid", transcript="Action: Ship", timezone="Mars/Olympus")
    assert LoginInput(email="owner@example.test", password=" password ").password == " password "


@pytest.mark.parametrize(
    ("line", "owner", "title"),
    [
        (
            "Riley: I'll draft the API deprecation notice by Friday.",
            "Riley",
            "Draft the API deprecation notice by Friday",
        ),
        ("Jordan: Casey will pair with Sam on the cache bug.", "Casey", "Pair with Sam on the cache bug"),
        ("[09:01] Riley: Sure. And Sam to update the runbook.", "Sam", "Update the runbook"),
        ("[10:02] Taylor: Then I will write the cleanup ticket.", "Taylor", "Write the cleanup ticket"),
        (
            "Sam: Riley, please chase the bank for the new limits.",
            "Riley",
            "Chase the bank for the new limits",
        ),
        (
            "Morgan: Action: Reconcile the accruals, owner: Riley, due Oct 31.",
            "Riley",
            "Reconcile the accruals",
        ),
    ],
)
def test_implicit_commitments_name_the_right_owner(line, owner, title):
    tasks = extract_tasks_rules(to_chunk_records(line))
    assert [(task["assignee_hint"], task["title"]) for task in tasks] == [(owner, title)]


@pytest.mark.parametrize(
    "line",
    [
        "Alex: Action: We won't need to migrate the legacy logs after all.",
        "[10:00] Morgan: We agreed to keep the v1 endpoint alive.",
        "Morgan: Yes, I'll have it done by Friday.",
        "Sam: Someone needs to update the handbook.",
    ],
)
def test_filler_pronouns_and_negations_are_not_owners_or_actions(line):
    assert extract_tasks_rules(to_chunk_records(line)) == []


def test_titles_start_with_a_capital_letter():
    tasks = extract_tasks_rules(to_chunk_records("Alex: Action: I will add a regression test by Friday."))
    assert tasks[0]["title"] == "Add a regression test by Friday"
