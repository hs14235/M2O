import re
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..access_policy import is_private_scope, require_private_scope
from ..auth import Principal, aware, require_role
from ..models import (
    GitHubDestination,
    Job,
    Meeting,
    Participant,
    PublicationOperation,
    PublicationProposal,
    WorkItem,
    WorkItemRevision,
    Workspace,
    now,
)
from ..schemas import PreviewInput
from ..settings import settings
from .common import audit, current_revision, fingerprint, meeting_access
from .errors import ServiceError
from .review import ReviewService


class IssueService:
    def __init__(self, session: Session, principal: Principal):
        self.session, self.principal = session, principal

    @staticmethod
    def allowed_repos() -> set[str]:
        return {
            value.strip().casefold() for value in settings.github_allowed_repos.split(",") if value.strip()
        }

    def destination_status(self) -> dict:
        if not is_private_scope(self.session, self.principal):
            return {"configured": False, "destination": None, "can_manage": False, "can_publish": False}
        row = self.session.scalar(
            select(GitHubDestination).where(GitHubDestination.workspace_id == self.principal.workspace_id)
        )
        configured = bool(settings.github_token.get_secret_value())
        enabled = bool(row and configured and row.repo.casefold() in self.allowed_repos())
        return {
            "configured": configured,
            "destination": {"id": row.id, "repo": row.repo, "version": row.version} if row else None,
            "can_manage": self.principal.role == "owner" and not settings.public_demo_mode,
            "can_publish": enabled
            and self.principal.role in {"owner", "reviewer"}
            and not settings.public_demo_mode,
        }

    def bind(self, repo: str, expected_version: int) -> dict:
        require_role(self.principal, {"owner"})
        require_private_scope(self.session, self.principal)
        if settings.public_demo_mode:
            raise ServiceError(
                status_code=403, error="Demo mode does not configure publication destinations", where="client"
            )
        if (
            not isinstance(repo, str)
            or len(repo) > 180
            or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo)
        ):
            raise ServiceError(status_code=422, error="Invalid repository", where="client")
        if type(expected_version) is not int or expected_version < 0:
            raise ServiceError(status_code=422, error="Invalid destination version", where="client")
        if repo.casefold() not in self.allowed_repos() or not settings.github_token.get_secret_value():
            raise ServiceError(
                status_code=403, error="This repository is not enabled by the operator", where="client"
            )
        workspace = self.session.scalar(
            select(Workspace).where(Workspace.id == self.principal.workspace_id).with_for_update()
        )
        if workspace is None:
            raise ServiceError(status_code=404, error="Workspace not found", where="client")
        row = self.session.scalar(
            select(GitHubDestination).where(GitHubDestination.workspace_id == workspace.id).with_for_update()
        )
        if expected_version != (row.version if row else 0):
            raise ServiceError(
                status_code=409, error="Destination changed; reload before configuring it", where="client"
            )
        if row:
            row.repo, row.version, row.configured_by = repo, row.version + 1, self.principal.user_id
        else:
            row = GitHubDestination(
                workspace_id=workspace.id, repo=repo, version=1, configured_by=self.principal.user_id
            )
            self.session.add(row)
        self.session.flush()
        audit(
            self.session,
            self.principal,
            "github.destination_configured",
            row.id,
            {"repo": repo, "version": row.version},
        )
        return self.destination_status()

    def preview(self, meeting_id: str, payload: PreviewInput) -> dict:
        require_role(self.principal, {"owner", "reviewer", "editor"})
        meeting = meeting_access(self.session, self.principal, meeting_id, lock=True)
        revision = current_revision(self.session, meeting)
        if meeting.visibility == "restricted" and not payload.external_disclosure_confirmed:
            raise ServiceError(
                status_code=403,
                error="Confirm external disclosure before preparing this restricted meeting",
                where="client",
            )
        if payload.expected_versions is not None and set(payload.expected_versions) != set(payload.task_ids):
            raise ServiceError(
                status_code=409, error="Selected outcomes differ from the expected versions", where="client"
            )
        destination = (
            self.session.scalar(
                select(GitHubDestination).where(GitHubDestination.workspace_id == self.principal.workspace_id)
            )
            if is_private_scope(self.session, self.principal)
            else None
        )
        if destination and destination.repo.casefold() != payload.repo.casefold():
            raise ServiceError(
                status_code=409,
                error="Repository differs from this workspace's selected destination",
                where="client",
            )
        if payload.expected_destination_version is not None and (
            not destination or destination.version != payload.expected_destination_version
        ):
            raise ServiceError(
                status_code=409, error="Destination changed; reload before previewing", where="client"
            )
        payloads, snapshots = [], []
        for item_id in dict.fromkeys(payload.task_ids):
            item = self.session.get(WorkItem, item_id)
            if not item or item.meeting_id != meeting.id or item.revision_id != revision.id:
                raise ServiceError(
                    status_code=409,
                    error="Selected outcomes must belong to the current transcript",
                    where="client",
                )
            if item.status != "approved":
                raise ServiceError(
                    status_code=409,
                    error="Approve every selected outcome before previewing publication",
                    where="client",
                )
            if payload.expected_versions is not None and payload.expected_versions[item.id] != item.version:
                raise ServiceError(
                    status_code=409, error="Outcome changed; reload before previewing", where="client"
                )
            original = self.session.scalar(
                select(WorkItemRevision).where(
                    WorkItemRevision.item_id == item.id, WorkItemRevision.version == 1
                )
            )
            if original and any(
                publication.get("repo", "").casefold() == payload.repo.casefold()
                for publication in original.payload.get("legacy_publications", [])
            ):
                raise ServiceError(
                    status_code=409,
                    error="This imported outcome already has a publication in that destination; review the legacy audit record",
                    where="client",
                )
            marker = f"<!-- meeting-to-tasks:{fingerprint([meeting.workspace_id, payload.repo.casefold(), item.id, item.version])} -->"
            body = item.body + f"\n\nOutcome: {item.kind}\n"
            owner = self.session.get(Participant, item.owner_id) if item.owner_id else None
            if owner:
                body += f"Owner: {owner.name} ({owner.role})\n"
            if item.due_date:
                body += f"Due date: {item.due_date}\n"
            elif item.due_hint:
                body += f"Unresolved date: {item.due_hint}\n"
            if payload.include_evidence:
                for source in ReviewService(self.session, self.principal).item_payload(item)["evidence"]:
                    body += (
                        f"\nSource chunk {source['i'] + 1}, line {source['start_line']}:\n> "
                        + source["text"].replace("\n", "\n> ")
                        + "\n"
                    )
            body += "\n" + marker
            issue = {"title": item.title, "body": body, "labels": item.labels}
            if owner and owner.github_login:
                issue["assignees"] = [owner.github_login]
            payloads.append(issue)
            snapshots.append(
                {
                    "id": item.id,
                    "version": item.version,
                    "revision_id": revision.id,
                    "marker": marker,
                    "external_disclosure_confirmed": payload.external_disclosure_confirmed,
                }
            )
        proposal = PublicationProposal(
            workspace_id=self.principal.workspace_id,
            meeting_id=meeting.id,
            repo=payload.repo,
            destination_id=destination.id if destination else None,
            destination_version=destination.version if destination else None,
            payload_hash=fingerprint([payload.repo, payloads]),
            payloads=payloads,
            snapshots=snapshots,
            expires_at=now() + timedelta(minutes=30),
        )
        self.session.add(proposal)
        self.session.flush()
        audit(
            self.session,
            self.principal,
            "publication.previewed",
            proposal.id,
            {"count": len(payloads), "includes_evidence": payload.include_evidence},
        )
        return self.serialize(proposal)

    @staticmethod
    def serialize(proposal):
        return {
            "id": proposal.id,
            "repo": proposal.repo,
            "payload_hash": proposal.payload_hash,
            "would_create": proposal.payloads,
            "expires_at": proposal.expires_at.isoformat(),
            "approved": bool(proposal.approved_at),
            "destination": {
                "id": proposal.destination_id,
                "version": proposal.destination_version,
                "repo": proposal.repo,
            }
            if proposal.destination_id
            else None,
        }

    def validate_snapshot(self, proposal):
        require_private_scope(self.session, self.principal)
        meeting = self.session.scalar(
            select(Meeting).where(Meeting.id == proposal.meeting_id).with_for_update()
        )
        if meeting is None:
            raise ServiceError(status_code=404, error="Meeting not found", where="client")
        meeting_access(self.session, self.principal, meeting.slug)
        if (
            proposal.workspace_id != self.principal.workspace_id
            or meeting.workspace_id != self.principal.workspace_id
        ):
            raise ServiceError(status_code=404, error="Publication preview not found", where="client")
        if fingerprint([proposal.repo, proposal.payloads]) != proposal.payload_hash:
            raise ServiceError(status_code=409, error="Stored preview integrity check failed", where="server")
        self.validate_destination(proposal)
        if meeting.visibility == "restricted" and not all(
            snapshot.get("external_disclosure_confirmed") for snapshot in proposal.snapshots
        ):
            raise ServiceError(
                status_code=403,
                error="Restricted meeting disclosure requires a new confirmed preview",
                where="client",
            )
        revision = current_revision(self.session, meeting)
        for snapshot in proposal.snapshots:
            item = self.session.get(WorkItem, snapshot["id"])
            if (
                not item
                or item.meeting_id != meeting.id
                or item.revision_id != revision.id
                or item.version != snapshot["version"]
                or item.status != "approved"
                or revision.id != snapshot["revision_id"]
            ):
                raise ServiceError(
                    status_code=409, error="Preview is stale; create and review a new preview", where="client"
                )
        return meeting

    def receipt_destination_current(self, proposal) -> bool:
        destination = self.session.scalar(
            select(GitHubDestination).where(GitHubDestination.workspace_id == self.principal.workspace_id)
        )
        return bool(
            destination
            and destination.id == proposal.destination_id
            and destination.version == proposal.destination_version
            and destination.repo.casefold() == proposal.repo.casefold()
        )

    def validate_destination(self, proposal):
        destination = self.session.scalar(
            select(GitHubDestination)
            .where(GitHubDestination.workspace_id == self.principal.workspace_id)
            .with_for_update()
        )
        if (
            not destination
            or destination.id != proposal.destination_id
            or destination.version != proposal.destination_version
            or destination.repo.casefold() != proposal.repo.casefold()
        ):
            raise ServiceError(
                status_code=409,
                error="Workspace destination changed or is unbound; prepare a new preview",
                where="client",
            )
        return destination

    def approve(self, proposal_id: str, payload_hash: str) -> dict:
        require_role(self.principal, {"owner", "reviewer"})
        require_private_scope(self.session, self.principal)
        proposal = self.session.scalar(
            select(PublicationProposal)
            .where(
                PublicationProposal.id == proposal_id,
                PublicationProposal.workspace_id == self.principal.workspace_id,
            )
            .with_for_update()
        )
        if not proposal:
            raise ServiceError(status_code=404, error="Publication preview not found", where="client")
        if proposal.payload_hash != payload_hash or aware(proposal.expires_at) <= now():
            raise ServiceError(
                status_code=409, error="Preview hash or expiration is invalid; preview again", where="client"
            )
        if settings.public_demo_mode:
            raise ServiceError(status_code=403, error="Demo mode allows previews only", where="client")
        meeting = self.validate_snapshot(proposal)
        if (
            proposal.repo.casefold() not in self.allowed_repos()
            or not settings.github_token.get_secret_value()
        ):
            raise ServiceError(
                status_code=403, error="This destination is not enabled for publication", where="client"
            )
        # A repeated approval, including an ambiguous operation, never creates another job.
        existing = self.session.scalar(
            select(PublicationOperation).where(
                PublicationOperation.publication_key
                == fingerprint([proposal.repo.casefold(), proposal.payloads])
            )
        )
        if existing:
            job = self.session.scalar(
                select(Job).where(
                    Job.kind == "publish", Job.payload["operation_id"].as_string() == existing.id
                )
            )
            return {"operation_id": existing.id, "job_id": job.id if job else None, "state": existing.state}
        proposal.approved_by, proposal.approved_at = self.principal.user_id, now()
        operation = PublicationOperation(
            proposal_id=proposal.id,
            publication_key=fingerprint([proposal.repo.casefold(), proposal.payloads]),
        )
        self.session.add(operation)
        self.session.flush()
        job = Job(
            workspace_id=self.principal.workspace_id,
            meeting_id=meeting.id,
            actor_id=self.principal.user_id,
            kind="publish",
            payload={"operation_id": operation.id},
        )
        self.session.add(job)
        self.session.flush()
        audit(
            self.session, self.principal, "publication.approved", proposal.id, {"payload_hash": payload_hash}
        )
        return {"operation_id": operation.id, "job_id": job.id, "state": job.state}

    @staticmethod
    def receipt(operation: PublicationOperation, proposal: PublicationProposal) -> dict:
        results = [
            {
                **(
                    operation.results[index]
                    if index < len(operation.results)
                    else {"status": "not_attempted"}
                ),
                "item_id": snapshot["id"],
                "version": snapshot["version"],
                "revision_id": snapshot["revision_id"],
            }
            for index, snapshot in enumerate(proposal.snapshots)
        ]
        allowed = proposal.repo.casefold() in IssueService.allowed_repos() and bool(
            settings.github_token.get_secret_value()
        )
        return {
            "operation_id": operation.id,
            "proposal_id": proposal.id,
            "state": operation.state,
            "repo": proposal.repo,
            "results": results,
            "created_at": operation.created_at.isoformat(),
            "can_reconcile": (
                operation.state == "uncertain"
                or (
                    operation.state == "failed"
                    and any(result.get("status") == "conflict" for result in operation.results)
                )
            )
            and allowed
            and not settings.public_demo_mode,
            "can_retry_rejected": False,
        }

    def operation(self, operation_id: str) -> dict:
        row = self.session.execute(
            select(PublicationOperation, PublicationProposal)
            .join(PublicationProposal, PublicationProposal.id == PublicationOperation.proposal_id)
            .where(
                PublicationOperation.id == operation_id,
                PublicationProposal.workspace_id == self.principal.workspace_id,
            )
        ).first()
        if row is None:
            raise ServiceError(status_code=404, error="Publication operation not found", where="client")
        operation, proposal = row
        meeting = self.session.get(Meeting, proposal.meeting_id)
        if meeting is None:
            raise ServiceError(status_code=404, error="Meeting not found", where="client")
        meeting_access(self.session, self.principal, meeting.slug)
        result = self.receipt(operation, proposal)
        result["can_reconcile"] = (
            result["can_reconcile"]
            and self.principal.role in {"owner", "reviewer"}
            and self.receipt_destination_current(proposal)
        )
        return result

    def history(self, meeting_id: str) -> list[dict]:
        meeting = meeting_access(self.session, self.principal, meeting_id)
        rows = self.session.execute(
            select(PublicationOperation, PublicationProposal)
            .join(PublicationProposal, PublicationProposal.id == PublicationOperation.proposal_id)
            .where(
                PublicationProposal.workspace_id == self.principal.workspace_id,
                PublicationProposal.meeting_id == meeting.id,
            )
            .order_by(PublicationOperation.created_at.desc(), PublicationOperation.id.desc())
            .limit(50)
        ).all()
        result = []
        for operation, proposal in rows:
            receipt = self.receipt(operation, proposal)
            receipt["can_reconcile"] = (
                receipt["can_reconcile"]
                and self.principal.role
                in {
                    "owner",
                    "reviewer",
                }
                and self.receipt_destination_current(proposal)
            )
            result.append(receipt)
        return result

    async def reconcile(self, operation_id: str, adapter=None):
        from ..github import GitHubAdapter

        require_role(self.principal, {"owner", "reviewer"})
        require_private_scope(self.session, self.principal)
        operation = self.session.scalar(
            select(PublicationOperation).where(PublicationOperation.id == operation_id).with_for_update()
        )
        if operation is None:
            raise ServiceError(status_code=404, error="Publication operation not found", where="client")
        proposal = self.session.get(PublicationProposal, operation.proposal_id) if operation else None
        if not proposal or proposal.workspace_id != self.principal.workspace_id:
            raise ServiceError(status_code=404, error="Publication operation not found", where="client")
        meeting = self.session.get(Meeting, proposal.meeting_id)
        if meeting is None:
            raise ServiceError(status_code=404, error="Meeting not found", where="client")
        meeting_access(self.session, self.principal, meeting.slug)
        if operation.state != "uncertain" and not (
            operation.state == "failed"
            and any(result.get("status") == "conflict" for result in operation.results)
        ):
            raise ServiceError(
                status_code=409,
                error="Only uncertain or conflicting publication operations need reconciliation",
                where="client",
            )
        if settings.public_demo_mode or proposal.repo.casefold() not in self.allowed_repos():
            raise ServiceError(
                status_code=403, error="Reconciliation is not enabled for this destination", where="client"
            )
        self.validate_destination(proposal)
        adapter = adapter or GitHubAdapter()
        results = list(operation.results)
        for position, result in enumerate(results):
            if result["status"] in {"uncertain", "conflict"}:
                found = await adapter.find_marker(
                    proposal.repo, proposal.snapshots[position]["marker"], proposal.payloads[position]
                )
                if found:
                    results[position] = found
        operation.results = results
        if len(results) == len(proposal.payloads) and all(
            result["status"] in {"created", "existing"} for result in results
        ):
            operation.state = "completed"
        audit(
            self.session, self.principal, "publication.reconciled", operation.id, {"state": operation.state}
        )
        return {"operation_id": operation.id, "state": operation.state, "results": results}
