"""Local stdio MCP adapter over the same authorized services as REST."""

import logging
from typing import Annotated, Any

from httpx import HTTPError
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field, ValidationError
from sqlalchemy.exc import SQLAlchemyError

from .auth import mcp_principal
from .database import must_get, session_scope
from .models import Job
from .schemas import IndexInput, ItemPatch, PreviewInput, SearchInput
from .services.errors import ServiceError
from .services.issues import IssueService
from .services.meetings import MeetingService
from .services.retrieval import RetrievalService
from .services.review import ReviewService

MeetingId = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")]
READ_ONLY = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)
LOCAL_WRITE = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False
)
EXTERNAL_WRITE = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=True
)
mcp = MCPServer(
    name="meeting-to-tasks",
    title="Meeting to Outcomes",
    version="1.0.0",
    instructions="Every tool requires a workspace-scoped MCP_API_TOKEN. Extraction queues a local write. Review outcome evidence and approve outcomes before previewing publication. create_github_issues requires explicit human approval of the exact proposal hash and is disabled in demo mode.",
)
logger = logging.getLogger("meeting_to_tasks.mcp")


def call(action):
    try:
        with session_scope() as session:
            return action(session, mcp_principal(session))
    except ServiceError as exc:
        raise ToolError(exc.detail["error"]) from exc
    except ValidationError as exc:
        raise ToolError("Tool arguments failed validation") from exc
    except (SQLAlchemyError, HTTPError, OSError, RuntimeError) as exc:
        logger.error("tool_failed", extra={"error_type": type(exc).__name__})
        raise ToolError("The tool could not complete the request") from None


@mcp.tool(annotations=LOCAL_WRITE, structured_output=True)
def index_meeting(
    meeting_id: MeetingId,
    transcript: Annotated[str, Field(min_length=1, max_length=1_000_000)],
    title: Annotated[str, Field(max_length=200)] = "",
    expected_version: Annotated[int, Field(ge=1)] | None = None,
) -> dict[str, Any]:
    """Create a transcript revision and queue indexing; replacement requires its current version."""
    return call(
        lambda s, p: MeetingService(s, p).index(
            IndexInput(
                meeting_id=meeting_id, transcript=transcript, title=title, expected_version=expected_version
            )
        )
    )


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def search_meeting(
    meeting_id: MeetingId,
    query: Annotated[str, Field(min_length=1, max_length=500)],
    k: Annotated[int, Field(ge=1, le=20)] = 5,
) -> dict[str, Any]:
    """Search persisted vectors within the authorized workspace and meeting."""
    payload = SearchInput(q=query, k=k)
    return call(lambda s, p: RetrievalService(s, p).search(meeting_id, payload.q, payload.k))


@mcp.tool(annotations=LOCAL_WRITE, structured_output=True)
def extract_meeting_tasks(meeting_id: MeetingId) -> dict[str, Any]:
    """Queue full-transcript local extraction; inspect job status before reviewing drafts."""
    return call(lambda s, p: MeetingService(s, p).enqueue_extraction(meeting_id))


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def get_meeting(meeting_id: MeetingId) -> dict[str, Any]:
    """Read current transcript evidence, outcomes, participant mentions and revision versions."""
    return call(lambda s, p: MeetingService(s, p).get(meeting_id))


@mcp.tool(annotations=READ_ONLY, structured_output=True)
def get_job(job_id: Annotated[str, Field(pattern=r"^[a-f0-9-]{36}$")]) -> dict[str, Any]:
    """Read an authorized job's durable state."""

    def read(session, principal):
        job = session.get(Job, job_id)
        if not job or job.workspace_id != principal.workspace_id:
            raise ServiceError(status_code=404, error="Job not found")
        if job.meeting_id:
            from .models import Meeting
            from .services.common import meeting_access

            meeting_access(session, principal, must_get(session, Meeting, job.meeting_id).slug)
        return {"id": job.id, "state": job.state, "result": job.result, "error_code": job.error_code}

    return call(read)


@mcp.tool(annotations=LOCAL_WRITE, structured_output=True)
def review_outcome(
    meeting_id: MeetingId, item_id: str, expected_version: int, changes: dict
) -> dict[str, Any]:
    """Save a version-checked review. Only reviewers and owners can approve outcomes."""
    return call(
        lambda s, p: ReviewService(s, p).patch(
            meeting_id, item_id, ItemPatch.model_validate({**changes, "expected_version": expected_version})
        )
    )


@mcp.tool(annotations=LOCAL_WRITE, structured_output=True)
def preview_github_issues(
    repo: str, meeting_id: MeetingId, task_ids: list[str], include_evidence: bool = False
) -> dict[str, Any]:
    """Store an exact immutable proposal for approved outcomes, without external calls."""
    return call(
        lambda s, p: IssueService(s, p).preview(
            meeting_id, PreviewInput(repo=repo, task_ids=task_ids, include_evidence=include_evidence)
        )
    )


@mcp.tool(annotations=EXTERNAL_WRITE, structured_output=True)
def create_github_issues(
    proposal_id: str, payload_hash: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
) -> dict[str, Any]:
    """After explicit human permission, approve this exact preview and queue publication."""
    return call(lambda s, p: IssueService(s, p).approve(proposal_id, payload_hash))


def main():
    # Network MCP hosting requires separate per-client authentication, so the local
    # scoped token is intentionally exposed only over the invoking client's stdio.
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
