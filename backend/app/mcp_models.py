"""Reusable structured result contracts for MCP clients."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .schemas import ItemCandidate, RecordId

TaskDraft = ItemCandidate


class Result(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IndexMeetingResult(Result):
    ok: bool
    meeting_id: str
    chunks_indexed: int = Field(ge=0)
    reindexed: bool
    version: int = Field(ge=1)
    job_id: RecordId | None


class SearchHit(Result):
    id: RecordId
    score: float
    text: str
    metadata: dict[str, Any]


class SearchMeetingResult(Result):
    results: list[SearchHit]
    provider: str
    revision_id: RecordId


class ExtractTasksResult(Result):
    job_id: RecordId
    state: Literal["queued", "running"]


class PreviewIssuesResult(Result):
    id: RecordId
    repo: str
    payload_hash: str
    would_create: list[dict[str, Any]]
    expires_at: str
    approved: bool


class CreateIssuesResult(Result):
    operation_id: RecordId
    job_id: RecordId | None
    state: str
