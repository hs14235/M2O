"""Exact Jira proposals tied to current outcome, destination and consenting owner."""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import Principal, aware
from ..jira_delivery import JiraDeliveryAdapter, document, encode_fields
from ..models import JiraOperation, JiraProposal, Job, Meeting, ProviderDestination, WorkItem, now
from ..schemas import JiraPreviewInput
from .common import audit, current_revision, fingerprint, meeting_access
from .errors import ServiceError
from .review import ReviewService


def destination_snapshot(binding: ProviderDestination) -> dict:
    if not binding.resource_id or not binding.project_key:
        raise ServiceError(
            status_code=409, error="Verify a Jira destination in Connections first", where="client"
        )
    return {
        key: getattr(binding, key)
        for key in (
            "id",
            "connection_id",
            "version",
            "resource_id",
            "resource_url",
            "project_key",
            "project_name",
        )
    }


class JiraDeliveryService:
    def __init__(self, session: Session, principal: Principal, adapter: JiraDeliveryAdapter | None = None):
        self.session, self.principal = session, principal
        self.adapter = adapter or JiraDeliveryAdapter()

    async def metadata(self, issue_type_id: str | None = None, issue_key: str | None = None) -> dict:
        _, binding, token = await self.adapter.access(self.session, self.principal)
        destination = destination_snapshot(binding)
        if issue_key:
            issue = await self.adapter.issue(token, destination, issue_key)
            issue_type_id = issue["fields"]["issuetype"]["id"]
        else:
            issue = None
        return {
            "destination": destination,
            "issue": issue,
            "issue_types": await self.adapter.types(token, destination) if not issue_key else [],
            "fields": await self.adapter.fields(token, destination, issue_type_id, issue_key)
            if issue_type_id
            else [],
        }

    async def preview(self, meeting_slug: str, data: JiraPreviewInput) -> dict:
        if (data.action == "update") != bool(data.issue_key):
            raise ServiceError(
                status_code=422, error="Select an existing issue only for an update", where="client"
            )
        _, binding, token = await self.adapter.access(self.session, self.principal)
        destination = destination_snapshot(binding)
        if destination["version"] != data.expected_destination_version:
            raise ServiceError(
                status_code=409, error="Jira destination changed; reload before previewing", where="client"
            )
        meeting = meeting_access(self.session, self.principal, meeting_slug, lock=True)
        revision = current_revision(self.session, meeting)
        item = self.session.get(WorkItem, data.item_id)
        if (
            not item
            or item.meeting_id != meeting.id
            or item.revision_id != revision.id
            or item.status != "approved"
            or item.version != data.expected_item_version
        ):
            raise ServiceError(
                status_code=409, error="Select the current approved outcome version", where="client"
            )
        issue = await self.adapter.issue(token, destination, data.issue_key) if data.issue_key else None
        if issue and issue["fields"]["issuetype"]["id"] != data.issue_type_id:
            raise ServiceError(
                status_code=409, error="Existing Jira issue type changed; reload its fields", where="jira"
            )
        metadata = await self.adapter.fields(token, destination, data.issue_type_id, data.issue_key)
        body = item.body + f"\n\nOutcome: {item.kind}"
        if item.due_date:
            body += f"\nReviewed due date: {item.due_date}"
        elif item.due_hint:
            body += f"\nUnconfirmed date: {item.due_hint}"
        if data.include_evidence:
            for source in ReviewService(self.session, self.principal).item_payload(item)["evidence"]:
                body += f"\n\nSource line {source['start_line']}:\n{source['text']}"
        if {"summary", "description", "project", "issuetype"} & data.fields.keys():
            raise ServiceError(
                status_code=422,
                error="Reviewed title, description and destination cannot be overridden",
                where="client",
            )
        if len(item.title) > 255:
            raise ServiceError(
                status_code=422, error="Shorten the reviewed title to 255 characters for Jira", where="client"
            )
        fields = encode_fields(metadata, {"summary": item.title, "description": body, **data.fields})
        # The description is generated through the field contract, which must be ADF.
        if fields.get("description") != document(body):
            raise ServiceError(
                status_code=422,
                error="This Jira screen does not support a rich-text description",
                where="jira",
            )
        if data.action == "create":
            fields.update(project={"key": destination["project_key"]}, issuetype={"id": data.issue_type_id})
        snapshot = {
            "item_id": item.id,
            "version": item.version,
            "revision_id": revision.id,
            "issue_key": data.issue_key,
            "remote_updated": issue["fields"]["updated"] if issue else None,
        }
        marker = fingerprint([self.principal.scope, destination, snapshot, fields])
        payload = {"fields": fields, "properties": [{"key": "m2o.delivery", "value": {"marker": marker}}]}
        proposal = JiraProposal(
            workspace_id=self.principal.scope,
            meeting_id=meeting.id,
            actor_id=self.principal.user_id,
            action=data.action,
            destination=destination,
            snapshot=snapshot,
            payload=payload,
            payload_hash=fingerprint([data.action, destination, snapshot, payload]),
            expires_at=now() + timedelta(minutes=30),
        )
        self.session.add(proposal)
        self.session.flush()
        audit(
            self.session,
            self.principal,
            "jira.previewed",
            proposal.id,
            {"action": data.action, "includes_evidence": data.include_evidence},
        )
        return self.serialize(proposal)

    @staticmethod
    def serialize(proposal: JiraProposal) -> dict:
        return {
            "id": proposal.id,
            "action": proposal.action,
            "destination": proposal.destination,
            "snapshot": proposal.snapshot,
            "payload": proposal.payload,
            "payload_hash": proposal.payload_hash,
            "expires_at": proposal.expires_at.isoformat(),
            "approved": bool(proposal.approved_at),
        }

    def proposal(self, identifier: str) -> JiraProposal:
        proposal = self.session.scalar(
            select(JiraProposal)
            .where(
                JiraProposal.id == identifier,
                JiraProposal.workspace_id == self.principal.scope,
                JiraProposal.actor_id == self.principal.user_id,
            )
            .with_for_update()
        )
        if not proposal:
            raise ServiceError(status_code=404, error="Jira preview not found", where="client")
        return proposal

    def validate(self, proposal: JiraProposal, binding: ProviderDestination) -> None:
        meeting = self.session.get(Meeting, proposal.meeting_id)
        if not meeting:
            raise ServiceError(status_code=409, error="Meeting is no longer available", where="client")
        meeting = meeting_access(self.session, self.principal, meeting.slug, lock=True)
        item = self.session.get(WorkItem, proposal.snapshot["item_id"])
        if (
            destination_snapshot(binding) != proposal.destination
            or not item
            or item.meeting_id != meeting.id
            or item.status != "approved"
            or item.version != proposal.snapshot["version"]
            or current_revision(self.session, meeting).id != proposal.snapshot["revision_id"]
        ):
            raise ServiceError(
                status_code=409, error="Jira preview is stale; review a new preview", where="client"
            )
        if proposal.payload_hash != fingerprint(
            [proposal.action, proposal.destination, proposal.snapshot, proposal.payload]
        ):
            raise ServiceError(
                status_code=409, error="Stored Jira preview integrity check failed", where="client"
            )

    async def approve(self, identifier: str, payload_hash: str, *, retry_rejected: bool = False) -> dict:
        _, binding, _ = await self.adapter.access(self.session, self.principal)
        proposal = self.proposal(identifier)
        self.validate(proposal, binding)
        if proposal.payload_hash != payload_hash or aware(proposal.expires_at) <= now():
            raise ServiceError(
                status_code=409,
                error="Jira preview hash or expiration changed; preview again",
                where="client",
            )
        delivery_key = fingerprint(
            [
                proposal.workspace_id,
                proposal.destination["resource_id"],
                proposal.destination["project_key"],
                proposal.snapshot["item_id"],
                proposal.snapshot["version"],
                proposal.action,
                proposal.snapshot["issue_key"],
            ]
        )
        existing = self.session.scalar(
            select(JiraOperation).where(JiraOperation.delivery_key == delivery_key).with_for_update()
        )
        if existing:
            previous = self.session.get(JiraProposal, existing.proposal_id)
            if not previous or previous.payload_hash != proposal.payload_hash:
                raise ServiceError(
                    status_code=409,
                    error="This outcome version already has a Jira delivery; inspect its receipt before changing the handoff",
                    where="client",
                )
            if retry_rejected and existing.state == "uncertain":
                raise ServiceError(
                    status_code=409,
                    error="An uncertain Jira write cannot be retried; reconcile its receipt",
                    where="client",
                )
            if (
                retry_rejected
                and existing.state == "failed"
                and (not existing.result or existing.result.get("status") == "rejected")
            ):
                existing.proposal_id, existing.state, existing.result = proposal.id, "queued", None
                operation = existing
                audit(
                    self.session,
                    self.principal,
                    "jira.retry_requested",
                    operation.id,
                    {"payload_hash": payload_hash},
                )
            else:
                job = self.session.scalar(
                    select(Job)
                    .where(Job.kind == "jira_publish", Job.payload["operation_id"].as_string() == existing.id)
                    .order_by(Job.created_at.desc())
                )
                return {
                    "operation_id": existing.id,
                    "job_id": job.id if job else None,
                    "state": existing.state,
                }
        else:
            operation = JiraOperation(proposal_id=proposal.id, delivery_key=delivery_key)
            self.session.add(operation)
        proposal.approved_at = now()
        self.session.flush()
        job = Job(
            workspace_id=self.principal.scope,
            meeting_id=proposal.meeting_id,
            actor_id=self.principal.user_id,
            kind="jira_publish",
            payload={"operation_id": operation.id},
        )
        self.session.add(job)
        self.session.flush()
        audit(self.session, self.principal, "jira.approved", proposal.id, {"payload_hash": payload_hash})
        return {"operation_id": operation.id, "job_id": job.id, "state": "queued"}

    def receipt(self, identifier: str) -> tuple[JiraOperation, JiraProposal]:
        operation = self.session.get(JiraOperation, identifier)
        if not operation:
            raise ServiceError(status_code=404, error="Jira receipt not found", where="client")
        proposal = self.proposal(operation.proposal_id)
        meeting = self.session.get(Meeting, proposal.meeting_id)
        if not meeting:
            raise ServiceError(status_code=404, error="Meeting not found", where="client")
        meeting_access(self.session, self.principal, meeting.slug)
        return operation, proposal

    async def reconcile(self, identifier: str, issue_key: str) -> dict:
        _, binding, token = await self.adapter.access(self.session, self.principal)
        operation, proposal = self.receipt(identifier)
        operation = self.session.scalar(
            select(JiraOperation).where(JiraOperation.id == operation.id).with_for_update()
        )
        if not operation or operation.state != "uncertain":
            raise ServiceError(
                status_code=409, error="Only uncertain Jira deliveries need reconciliation", where="client"
            )
        if binding.id != proposal.destination["id"] or destination_snapshot(binding) != proposal.destination:
            raise ServiceError(
                status_code=409,
                error="Reconnect and restore the original Jira destination before reconciling",
                where="client",
            )
        if proposal.action == "update" and issue_key != proposal.snapshot["issue_key"]:
            raise ServiceError(
                status_code=409, error="Reconcile the exact reviewed Jira issue", where="client"
            )
        marker = proposal.payload["properties"][0]["value"]["marker"]
        operation.result = await self.adapter.verify_receipt(token, proposal.destination, issue_key, marker)
        operation.state = "completed"
        audit(self.session, self.principal, "jira.reconciled", operation.id, {"issue_key": issue_key})
        return {"operation_id": operation.id, "state": operation.state, "result": operation.result}
