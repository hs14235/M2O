import hashlib
import json
import sqlite3

import pytest

from app.schemas import ItemPatch, PreviewInput
from app.services.errors import ServiceError
from app.services.issues import IssueService
from app.services.meetings import MeetingService
from app.services.review import ReviewService
from app.storage import read_legacy
from scripts.import_legacy import import_rows, validate


def fixture_file(path, source=8, confidence=0.6):
    with sqlite3.connect(path) as connection:
        connection.executescript("""
        CREATE TABLE meetings(id TEXT PRIMARY KEY,title TEXT,raw_text TEXT);
        CREATE TABLE transcript_chunks(meeting_id TEXT,chunk_index INTEGER,text TEXT,speaker TEXT,timestamp TEXT,start_line INTEGER);
        CREATE TABLE task_drafts(id INTEGER,meeting_id TEXT,ordinal INTEGER,title TEXT,body TEXT,labels_json TEXT,assignee_hint TEXT,due_hint TEXT,source_i INTEGER,confidence REAL);
        CREATE TABLE issue_publications(id INTEGER,meeting_id TEXT,repo TEXT,task_title TEXT,status TEXT,issue_url TEXT);
        """)
        connection.execute(
            "INSERT INTO meetings VALUES(?,?,?)", ("legacy", "Legacy", "Action: Synthetic review")
        )
        connection.execute(
            "INSERT INTO transcript_chunks VALUES(?,?,?,?,?,?)",
            ("legacy", 8, "Original evidence at index eight.", "Alex", None, 5),
        )
        connection.execute(
            "INSERT INTO task_drafts VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                1,
                "legacy",
                0,
                "Human legacy wording",
                "Preserve this human edit",
                json.dumps(["meeting-action"]),
                "Alex",
                "Friday",
                source,
                confidence,
            ),
        )
        connection.execute(
            "INSERT INTO issue_publications VALUES(?,?,?,?,?,?)",
            (
                1,
                "legacy",
                "synthetic/demo",
                "Earlier issue",
                "created",
                "https://github.com/synthetic/demo/issues/1",
            ),
        )


def test_import_preserves_source_and_exact_legacy_evidence(session, seeded, tmp_path):
    path = tmp_path / "legacy.db"
    fixture_file(path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    rows = read_legacy(path)
    assert validate(rows) == []
    assert import_rows(session, seeded["principal"], rows) == 1
    session.commit()
    details = MeetingService(session, seeded["principal"]).get("legacy")
    task = details["tasks"][0]
    assert task["title"] == "Human legacy wording"
    assert task["evidence"][0]["text"] == "Original evidence at index eight."
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    with pytest.raises(ValueError, match="already exists"):
        import_rows(session, seeded["principal"], rows)


def test_imported_successful_publication_cannot_be_replayed(session, seeded, tmp_path):
    path = tmp_path / "legacy.db"
    fixture_file(path)
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE issue_publications SET task_title=?", ("Human legacy wording",))
    import_rows(session, seeded["principal"], read_legacy(path))
    session.commit()
    task = MeetingService(session, seeded["principal"]).get("legacy")["tasks"][0]
    ReviewService(session, seeded["principal"]).patch(
        "legacy", task["id"], ItemPatch(expected_version=1, status="approved")
    )
    session.commit()
    with pytest.raises(ServiceError, match="already has a publication"):
        IssueService(session, seeded["principal"]).preview(
            "legacy", PreviewInput(repo="synthetic/demo", task_ids=[task["id"]])
        )


@pytest.mark.parametrize("source,confidence", [(999, 0.6), (8, 2)])
def test_import_rejects_broken_legacy_citations_and_confidence(tmp_path, source, confidence):
    path = tmp_path / "legacy.db"
    fixture_file(path, source, confidence)
    assert validate(read_legacy(path))[0]["reason"] == "invalid_evidence_or_confidence"
