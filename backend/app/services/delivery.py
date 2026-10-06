"""Destination capabilities and provider-independent, revision-checked handoffs."""

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..access_policy import is_private_scope
from ..auth import Principal
from ..jira import connection_status
from ..models import LinkedInProfile, Participant, Workspace
from ..schemas import ExportInput
from ..settings import settings
from ..slack import connection_status as slack_status
from .common import current_revision, fingerprint, meeting_access
from .errors import ServiceError
from .issues import IssueService
from .linkedin_publishing import LinkedInPublishingService
from .review import ReviewService


def integration_catalog(session: Session, principal: Principal) -> list[dict]:
    private = is_private_scope(session, principal)
    github_ready = private and bool(
        settings.github_token.get_secret_value() and settings.github_allowed_repos.strip()
    )
    github = IssueService(session, principal).destination_status()
    jira = connection_status(session, principal)
    slack = slack_status(session, principal)
    linkedin = LinkedInPublishingService(session, principal).status()
    return [
        {
            "id": "local",
            "name": "Local handoff",
            "purpose": "delivery",
            "status": "ready",
            "can_preview": True,
            "can_publish": False,
            "description": "Download reviewed outcomes as Markdown or JSON. No account connection needed.",
        },
        {
            "id": "github",
            "name": "GitHub",
            "purpose": "delivery",
            "status": "configured" if github_ready else "preview_only",
            "can_preview": principal.role in {"owner", "reviewer", "editor"},
            "can_publish": github["can_publish"],
            "description": "Create issues from an exact approved preview. Publication requires an enabled repository and reviewer.",
        },
        {
            "id": "jira",
            "name": "Jira",
            "purpose": "delivery",
            "status": "connected"
            if jira["state"] == "connected"
            else "configured"
            if jira["configured"]
            else "needs_configuration",
            "can_preview": bool(jira["can_manage"] and jira["state"] == "connected" and jira["destination"]),
            "can_publish": bool(jira["can_manage"] and jira["state"] == "connected" and jira["destination"]),
            "description": "Create or update Jira issues from an exact approved preview using your verified destination. Personal-plan progress stays separate.",
        },
        {
            "id": "slack",
            "name": "Slack",
            "purpose": "delivery",
            "status": "connected"
            if slack["state"] == "connected"
            else "configured"
            if slack["configured"]
            else "needs_configuration",
            "can_preview": slack["can_create"],
            "can_publish": slack["can_create"],
            "description": "Deliver or update a reviewed message in your verified Slack channel. Personal-plan progress stays separate.",
        },
        {
            "id": "linkedin",
            "name": "LinkedIn",
            "purpose": "context",
            "status": "connected"
            if linkedin["state"] == "connected" or private and session.get(LinkedInProfile, principal.user_id)
            else "configured"
            if linkedin["configured"] or private and settings.linkedin_configured
            else "needs_configuration",
            "can_preview": linkedin["can_publish"],
            "can_publish": linkedin["can_publish"],
            "can_draft": linkedin["can_draft"],
            "can_context": private and settings.linkedin_configured,
            "can_message": False,
            "description": "Prepare local post or outreach drafts. Live member posts require separate approved consent; profile context uses your own consenting account.",
        },
    ]


def export_outcomes(session: Session, principal: Principal, meeting_id: str, payload: ExportInput) -> dict:
    meeting = meeting_access(session, principal, meeting_id, lock=True)
    revision = current_revision(session, meeting)
    if meeting.current_revision != payload.expected_revision:
        raise ServiceError(
            status_code=409, error="Transcript changed; reload before exporting", where="client"
        )
    items = {item["id"]: item for item in ReviewService(session, principal).list_items(meeting, revision.id)}
    owners = {
        person.id: {"id": person.id, "name": person.name, "role": person.role}
        for person in session.scalars(
            select(Participant).where(Participant.workspace_id == principal.workspace_id)
        )
    }
    records = []
    for item_id, expected_version in payload.versions.items():
        item = items.get(item_id)
        if not item or item["status"] != "approved" or item["version"] != expected_version:
            raise ServiceError(
                status_code=409,
                error="Selected outcomes changed; review them before exporting",
                where="client",
            )
        records.append(
            {
                **{
                    key: item[key]
                    for key in (
                        "id",
                        "version",
                        "kind",
                        "title",
                        "body",
                        "labels",
                        "owner_id",
                        "due_date",
                        "due_hint",
                    )
                },
                "status": "approved",
                "due_date": str(item["due_date"]) if item["due_date"] else None,
                "owner": owners.get(item["owner_id"]),
                "evidence": [
                    {key: value for key, value in source.items() if payload.include_evidence or key != "text"}
                    for source in item["evidence"]
                ],
            }
        )
    workspace = session.get(Workspace, principal.workspace_id)
    bundle = {
        "schema_version": 1,
        "meeting": {"id": meeting.slug, "title": meeting.title, "revision": meeting.current_revision},
        "department": workspace.department if workspace else None,
        "outcomes": records,
    }
    if payload.format == "json":
        content, media_type, extension = (
            json.dumps(bundle, ensure_ascii=False, indent=2),
            "application/json",
            "json",
        )
    else:
        lines = [f"# {meeting.title}", "", f"Transcript revision: {meeting.current_revision}", ""]
        for item in records:
            lines.extend(
                [
                    f"## {item['title']}",
                    "",
                    f"Type: {item['kind']} | Reviewed version: {item['version']}",
                    "",
                    item["body"],
                    "",
                ]
            )
            if item["owner"]:
                lines.extend([f"Owner: {item['owner']['name']} ({item['owner']['role']})", ""])
            if item["due_date"]:
                lines.extend([f"Due date: {item['due_date']}", ""])
            elif item["due_hint"]:
                lines.extend([f"Date still needs confirmation: {item['due_hint']}", ""])
            if payload.include_evidence:
                for source in item["evidence"]:
                    lines.extend(
                        [
                            f"Source line {source['start_line']}:",
                            "> " + source["text"].replace("\n", "\n> "),
                            "",
                        ]
                    )
        content, media_type, extension = "\n".join(lines), "text/markdown", "md"
    return {
        "filename": f"{meeting.slug}-reviewed-outcomes.{extension}",
        "media_type": media_type,
        "content": content,
        "snapshot_hash": fingerprint(bundle),
    }
