"""Validate and import a legacy SQLite file without modifying the source."""

import argparse
import json
from pathlib import Path

from sqlalchemy import select

from app.auth import Principal
from app.database import session_scope
from app.models import (
    Meeting,
    Membership,
    TranscriptChunk,
    TranscriptRevision,
    WorkItem,
    WorkItemEvidence,
    WorkItemRevision,
)
from app.schemas import IndexInput, ItemCandidate
from app.services.common import audit, fingerprint
from app.services.meetings import MeetingService
from app.storage import read_legacy


def validate(rows):
    rejected = []
    for position, row in enumerate(rows):
        IndexInput(meeting_id=row["id"], title=row["title"], transcript=row["raw_text"])
        indices = {chunk["chunk_index"] for chunk in row["chunks"]}
        for ordinal, task in enumerate(row["tasks"]):
            valid_source = isinstance(task["source_i"], int) and task["source_i"] in indices
            valid_confidence = isinstance(task["confidence"], (int, float)) and 0 <= task["confidence"] <= 1
            if not valid_source or not valid_confidence:
                rejected.append(
                    {
                        "meeting_position": position,
                        "task_position": ordinal,
                        "reason": "invalid_evidence_or_confidence",
                    }
                )
            else:
                ItemCandidate(
                    kind="action",
                    title=task["title"],
                    body=task["body"],
                    labels=task["labels"],
                    assignee_hint=task["assignee_hint"],
                    due_hint=task["due_hint"],
                    confidence=task["confidence"],
                    source_ids=["00000000-0000-4000-8000-000000000001"],
                )
    return rejected


def import_rows(session, principal, rows):
    imported = 0
    for row in rows:
        if session.scalar(
            select(Meeting.id).where(
                Meeting.workspace_id == principal.workspace_id, Meeting.slug == row["id"]
            )
        ):
            raise ValueError("A meeting identifier already exists; import into an empty workspace")
        MeetingService(session, principal).index(
            IndexInput(meeting_id=row["id"], title=row["title"], transcript=row["raw_text"])
        )
        meeting = session.scalar(
            select(Meeting).where(Meeting.workspace_id == principal.workspace_id, Meeting.slug == row["id"])
        )
        revision = session.scalar(
            select(TranscriptRevision).where(TranscriptRevision.meeting_id == meeting.id)
        )
        chunks = session.scalars(
            select(TranscriptChunk).where(TranscriptChunk.revision_id == revision.id)
        ).all()
        # Original chunk boundaries may differ. Preserve the source evidence text
        # by adding dedicated legacy chunks rather than guessing a new position.
        source_map = {}
        for old in row["chunks"]:
            chunk = TranscriptChunk(
                revision_id=revision.id,
                chunk_index=len(chunks) + len(source_map),
                text=old["text"],
                speaker=old["speaker"],
                timestamp=old["timestamp"],
                start_line=max(1, old["start_line"]),
            )
            session.add(chunk)
            session.flush()
            source_map[old["chunk_index"]] = chunk.id
        for old in row["tasks"]:
            task = ItemCandidate(
                kind="action",
                title=old["title"],
                body=old["body"],
                labels=old["labels"],
                assignee_hint=old["assignee_hint"],
                due_hint=old["due_hint"],
                confidence=old["confidence"],
                source_ids=[source_map[old["source_i"]]],
            )
            item = WorkItem(
                workspace_id=meeting.workspace_id,
                meeting_id=meeting.id,
                revision_id=revision.id,
                fingerprint=fingerprint(["legacy", old["id"]]),
                **task.model_dump(exclude={"source_ids"}),
            )
            session.add(item)
            session.flush()
            session.add(
                WorkItemEvidence(item_id=item.id, chunk_id=task.source_ids[0], revision_id=revision.id)
            )
            session.add(
                WorkItemRevision(
                    item_id=item.id,
                    version=1,
                    actor_id=principal.user_id,
                    payload={
                        **task.model_dump(),
                        "legacy_publications": [
                            publication
                            for publication in row["publications"]
                            if publication.get("task_title") == old["title"]
                            and publication.get("status") in {"created", "existing"}
                        ],
                    },
                )
            )
        # Old publication records are preserved as audit metadata, never replayed.
        audit(
            session,
            principal,
            "legacy.imported",
            meeting.id,
            {"legacy_publications": row["publications"], "legacy_chunk_count": len(source_map)},
        )
        imported += 1
    return imported


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("sqlite_file", type=Path)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    rows = read_legacy(args.sqlite_file)
    rejected = validate(rows)
    print(
        json.dumps(
            {"meetings": len(rows), "invalid_tasks": rejected, "mode": "apply" if args.apply else "dry_run"}
        )
    )
    if rejected:
        raise ValueError("Import stopped; repair invalid legacy evidence in a copy of the source")
    if args.apply:
        with session_scope() as session:
            member = session.get(Membership, (args.workspace, args.actor))
            if not member or member.role != "owner":
                raise ValueError("The import actor must own the destination workspace")
            count = import_rows(session, Principal(args.actor, args.workspace, member.role), rows)
        print(f"Imported {count} meetings in one transaction; source unchanged.")


if __name__ == "__main__":
    main()
