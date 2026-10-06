"""Read-only access to the legacy SQLite export; PostgreSQL owns current state."""

import json
import sqlite3
from pathlib import Path


def read_legacy(path: Path) -> list[dict]:
    path = path.resolve(strict=True)
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"meetings", "transcript_chunks", "task_drafts"}.issubset(tables):
            raise ValueError("Unsupported legacy SQLite schema")
        rows = []
        for meeting in connection.execute("SELECT * FROM meetings ORDER BY id"):
            chunks = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM transcript_chunks WHERE meeting_id=? ORDER BY chunk_index",
                    (meeting["id"],),
                )
            ]
            tasks = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM task_drafts WHERE meeting_id=? ORDER BY ordinal", (meeting["id"],)
                )
            ]
            for task in tasks:
                task["labels"] = json.loads(task.pop("labels_json"))
            publications = (
                [
                    dict(row)
                    for row in connection.execute(
                        "SELECT * FROM issue_publications WHERE meeting_id=?", (meeting["id"],)
                    )
                ]
                if "issue_publications" in tables
                else []
            )
            rows.append({**dict(meeting), "chunks": chunks, "tasks": tasks, "publications": publications})
        return rows
