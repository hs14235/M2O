from time import perf_counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    ExtractionRun,
    ParticipantMention,
    TranscriptChunk,
    TranscriptRevision,
    WorkItem,
    WorkItemEvidence,
    WorkItemRevision,
)
from ..schemas import ItemCandidate
from ..settings import settings
from ..tasks import LABEL_PATTERN, extract_tasks_ollama, extract_tasks_rules
from .common import fingerprint
from .errors import ServiceError


class ExtractionService:
    def __init__(self, session: Session | None):
        self.session = session

    async def generate(self, revision_id: str) -> dict:
        if self.session is None:
            raise ValueError("A database session is required to load evidence")
        chunks = self.session.scalars(
            select(TranscriptChunk)
            .where(TranscriptChunk.revision_id == revision_id)
            .order_by(TranscriptChunk.chunk_index)
        ).all()
        records = [
            {"id": chunk.id, "i": chunk.chunk_index, "text": chunk.text, "speaker": chunk.speaker}
            for chunk in chunks
        ]
        return await self.generate_records(records)

    async def generate_records(self, records: list[dict], *, use_model: bool = True) -> dict:
        started = perf_counter()
        batches, pending, size = [], [], 0
        for chunk in records:
            amount = len(chunk["text"].encode("utf-8")) + 180
            if pending and size + amount > 3500:
                batches.append(pending)
                pending, size = [], 0
            pending.append(chunk)
            size += amount
        if pending:
            batches.append(pending)
        candidates, modes, warnings = [], [], []
        for batch in batches:
            generated, warning = (
                await extract_tasks_ollama(batch) if use_model else (None, "synthetic_demo_rules")
            )
            if warning:
                warnings.append(warning)
            if generated:
                modes.append("ollama")
                explicit_chunks = [chunk for chunk in batch if LABEL_PATTERN.search(chunk["text"])]
                explicit_ids = {chunk["id"] for chunk in explicit_chunks}
                candidates.extend(task for task in generated if not set(task["source_ids"]) & explicit_ids)
                if explicit_chunks:
                    # Literal labels retain exact facts even when a small model
                    # omits, paraphrases or misclassifies an explicit outcome.
                    modes.append("rules")
                    warnings.append("explicit_outcomes_preserved")
                    for task in extract_tasks_rules(explicit_chunks):
                        task.pop("source_i", None)
                        candidates.append(ItemCandidate.model_validate(task).model_dump())
            else:
                modes.append("rules")
                for task in extract_tasks_rules(batch):
                    task.pop("source_i", None)
                    candidates.append(ItemCandidate.model_validate(task).model_dump())
        by_key = {}
        for task in candidates:
            key = fingerprint([task["kind"], task["title"].casefold(), task["body"].casefold()])
            if key in by_key:
                by_key[key]["source_ids"] = list(
                    dict.fromkeys([*by_key[key]["source_ids"], *task["source_ids"]])
                )[:8]
            else:
                by_key[key] = task
        if len(by_key) > settings.max_outcomes:
            warnings.append("outcome_limit_reached")
        return {
            "tasks": list(by_key.values())[: settings.max_outcomes],
            "mode": "ollama"
            if modes and all(mode == "ollama" for mode in modes)
            else "mixed"
            if "ollama" in modes
            else "rules",
            "coverage": {
                "total_chunks": len(records),
                "processed_chunks": len(records),
                "batches": len(batches),
                "warnings": sorted(set(warnings)),
                "full_transcript": True,
            },
            "timings": {"total_ms": round((perf_counter() - started) * 1000, 2)},
        }

    def persist(self, meeting, revision_id: str, result: dict) -> dict:
        if self.session is None:
            raise ValueError("A database session is required to persist outcomes")
        revision = self.session.get(TranscriptRevision, revision_id)
        if (
            revision is None
            or revision.meeting_id != meeting.id
            or revision.number != meeting.current_revision
            or meeting.archived_at
        ):
            raise ServiceError(status_code=409, error="Transcript changed during extraction", where="client")
        run = ExtractionRun(revision_id=revision_id, mode=result["mode"], coverage=result["coverage"])
        self.session.add(run)
        self.session.flush()
        source_ids = set(
            self.session.scalars(select(TranscriptChunk.id).where(TranscriptChunk.revision_id == revision_id))
        )
        mentions = list(
            self.session.scalars(
                select(ParticipantMention).where(ParticipantMention.revision_id == revision_id)
            ).all()
        )
        confirmed = {
            mention.name.casefold(): mention.participant_id for mention in mentions if mention.confirmed_by
        }
        created = 0
        for raw in result["tasks"]:
            task = ItemCandidate.model_validate(raw)
            if not set(task.source_ids).issubset(source_ids):
                continue
            key = fingerprint([task.kind, task.title.casefold(), task.body.casefold()])
            existing = self.session.scalar(
                select(WorkItem).where(
                    WorkItem.meeting_id == meeting.id,
                    WorkItem.revision_id == revision_id,
                    WorkItem.fingerprint == key,
                )
            )
            if existing:
                continue
            owner = confirmed.get((task.assignee_hint or "").casefold())
            if task.assignee_hint and not any(
                mention.name.casefold() == task.assignee_hint.casefold() for mention in mentions
            ):
                mention = ParticipantMention(
                    workspace_id=meeting.workspace_id,
                    meeting_id=meeting.id,
                    revision_id=revision_id,
                    name=task.assignee_hint,
                )
                self.session.add(mention)
                mentions.append(mention)
            item = WorkItem(
                workspace_id=meeting.workspace_id,
                meeting_id=meeting.id,
                revision_id=revision_id,
                extraction_run_id=run.id,
                fingerprint=key,
                owner_id=owner,
                **task.model_dump(exclude={"source_ids"}),
            )
            self.session.add(item)
            self.session.flush()
            for source_id in dict.fromkeys(task.source_ids):
                self.session.add(
                    WorkItemEvidence(item_id=item.id, chunk_id=source_id, revision_id=revision_id)
                )
            self.session.add(
                WorkItemRevision(item_id=item.id, version=1, payload=task.model_dump(), actor_id=None)
            )
            created += 1
        self.session.flush()
        return {
            "run_id": run.id,
            "mode": result["mode"],
            "coverage": result["coverage"],
            "created": created,
            "timings": result["timings"],
        }
