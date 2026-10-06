"""Revision-bound Slack previews, approved delivery intents and persistent receipts."""

from datetime import timedelta

from sqlalchemy import select

from ..auth import aware
from ..models import (
    Job,
    Meeting,
    SlackAccount,
    SlackDestination,
    SlackOperation,
    SlackProposal,
    WorkItem,
    now,
)
from ..slack import binding_query, connection_status
from ..slack_delivery import SlackDeliveryAdapter, content_hash, marker, message_payload
from .common import audit, current_revision, fingerprint, meeting_access
from .errors import ServiceError
from .review import ReviewService


def destination_snapshot(session, binding, account):
    channel = session.get(SlackDestination, binding.id)
    if not channel:
        raise ServiceError(
            status_code=409, error="Verify a Slack channel in Connections first", where="client"
        )
    return {
        "id": binding.id,
        "connection_id": binding.connection_id,
        "version": binding.version,
        "app_id": account.app_id,
        "team_id": account.team_id,
        "team_name": account.team_name,
        "bot_user_id": account.bot_user_id,
        "bot_id": account.bot_id,
        "channel_id": channel.channel_id,
        "channel_name": channel.channel_name,
    }


class SlackDeliveryService:
    def __init__(self, session, principal, adapter=None):
        self.session, self.principal = session, principal
        self.adapter = adapter or SlackDeliveryAdapter()

    async def preview(self, meeting_slug, data):
        if (data.action == "update") != bool(data.target_operation_id):
            raise ServiceError(
                status_code=422, error="Choose a previous M2O delivery only for an update", where="client"
            )
        _, binding, account, token = await self.adapter.access(self.session, self.principal)
        destination = destination_snapshot(self.session, binding, account)
        if binding.version != data.expected_destination_version:
            raise ServiceError(status_code=409, error="Slack destination changed; reload", where="client")
        await self.adapter.channel(token, destination["channel_id"])
        meeting = meeting_access(self.session, self.principal, meeting_slug, lock=True)
        revision = current_revision(self.session, meeting)
        if meeting.current_revision != data.expected_revision:
            raise ServiceError(
                status_code=409, error="Transcript changed; review a new preview", where="client"
            )
        if meeting.visibility == "restricted" and not data.confirm_restricted_share:
            raise ServiceError(
                status_code=422,
                error="Explicitly confirm sharing restricted meeting outcomes to Slack",
                where="client",
            )
        records, snapshots = [], []
        for identifier, version in sorted(data.versions.items()):
            item = self.session.get(WorkItem, identifier)
            if (
                not item
                or item.meeting_id != meeting.id
                or item.revision_id != revision.id
                or item.status != "approved"
                or item.version != version
            ):
                raise ServiceError(
                    status_code=409, error="Select only current approved outcome versions", where="client"
                )
            payload = ReviewService(self.session, self.principal).item_payload(item)
            if not data.include_evidence:
                payload["evidence"] = []
            records.append(payload)
            snapshots.append({"item_id": item.id, "version": item.version, "revision_id": revision.id})
        target = None
        if data.target_operation_id:
            operation, previous = self.receipt(data.target_operation_id)
            if (
                operation.state != "completed"
                or not operation.result
                or previous.meeting_id != meeting.id
                or previous.destination != destination
            ):
                raise ServiceError(
                    status_code=409,
                    error="Select a completed M2O message at the current Slack destination",
                    where="client",
                )
            message_ts = operation.result["message_ts"]
            remote = await self.adapter.message(token, destination, message_ts)
            if marker(remote) != marker(previous.payload):
                raise ServiceError(
                    status_code=409, error="Previous M2O message marker changed", where="slack"
                )
            target = {
                "operation_id": operation.id,
                "message_ts": message_ts,
                "observed_content_hash": content_hash(remote),
            }
        reference = fingerprint([self.principal.scope, destination, snapshots, records, target])
        payload = message_payload(destination["channel_id"], records, reference)
        proposal = SlackProposal(
            workspace_id=self.principal.scope,
            meeting_id=meeting.id,
            actor_id=self.principal.user_id,
            action=data.action,
            destination=destination,
            snapshots=snapshots,
            target=target,
            payload=payload,
            payload_hash=fingerprint([data.action, destination, snapshots, target, payload]),
            expires_at=now() + timedelta(minutes=30),
        )
        self.session.add(proposal)
        self.session.flush()
        audit(
            self.session,
            self.principal,
            "slack.previewed",
            proposal.id,
            {
                "action": data.action,
                "includes_evidence": data.include_evidence,
                "restricted_share_confirmed": data.confirm_restricted_share,
            },
        )
        return self.serialize(proposal)

    @staticmethod
    def serialize(proposal):
        return {
            "id": proposal.id,
            "action": proposal.action,
            "destination": proposal.destination,
            "snapshots": proposal.snapshots,
            "target": proposal.target,
            "payload": proposal.payload,
            "payload_hash": proposal.payload_hash,
            "expires_at": proposal.expires_at.isoformat(),
            "approved": bool(proposal.approved_at),
        }

    def proposal(self, identifier):
        proposal = self.session.scalar(
            select(SlackProposal)
            .where(
                SlackProposal.id == identifier,
                SlackProposal.workspace_id == self.principal.scope,
                SlackProposal.actor_id == self.principal.user_id,
            )
            .with_for_update()
        )
        if not proposal:
            raise ServiceError(status_code=404, error="Slack preview not found", where="client")
        return proposal

    def validate(self, proposal, binding, account):
        meeting = self.session.get(Meeting, proposal.meeting_id)
        if not meeting:
            raise ServiceError(status_code=409, error="Meeting is no longer available", where="client")
        meeting = meeting_access(self.session, self.principal, meeting.slug, lock=True)
        revision = current_revision(self.session, meeting)
        if destination_snapshot(self.session, binding, account) != proposal.destination:
            raise ServiceError(
                status_code=409, error="Slack destination changed; review a new preview", where="client"
            )
        for snapshot in proposal.snapshots:
            item = self.session.get(WorkItem, snapshot["item_id"])
            if (
                not item
                or item.meeting_id != meeting.id
                or item.status != "approved"
                or item.version != snapshot["version"]
                or item.revision_id != revision.id
                or item.revision_id != snapshot["revision_id"]
            ):
                raise ServiceError(
                    status_code=409, error="Slack source changed; review a new preview", where="client"
                )
        if proposal.payload_hash != fingerprint(
            [proposal.action, proposal.destination, proposal.snapshots, proposal.target, proposal.payload]
        ):
            raise ServiceError(
                status_code=409, error="Stored Slack preview integrity check failed", where="client"
            )

    async def approve(self, identifier, payload_hash, *, retry_rejected=False):
        _, binding, account, _ = await self.adapter.access(self.session, self.principal)
        proposal = self.proposal(identifier)
        self.validate(proposal, binding, account)
        if proposal.payload_hash != payload_hash or aware(proposal.expires_at) <= now():
            raise ServiceError(
                status_code=409, error="Slack preview hash or expiry changed; preview again", where="client"
            )
        delivery_key = fingerprint(
            [
                proposal.workspace_id,
                proposal.destination["app_id"],
                proposal.destination["team_id"],
                proposal.destination["channel_id"],
                proposal.snapshots,
                proposal.action,
                proposal.target["message_ts"] if proposal.target else None,
            ]
        )
        existing = self.session.scalar(
            select(SlackOperation).where(SlackOperation.delivery_key == delivery_key).with_for_update()
        )
        if existing:
            previous = self.session.get(SlackProposal, existing.proposal_id)
            if not previous or previous.payload_hash != proposal.payload_hash:
                raise ServiceError(
                    status_code=409,
                    error="This outcome version already has a Slack delivery; inspect its receipt",
                    where="client",
                )
            if retry_rejected and existing.state == "uncertain":
                raise ServiceError(
                    status_code=409,
                    error="An uncertain Slack write cannot be retried; reconcile",
                    where="client",
                )
            if (
                retry_rejected
                and existing.state == "failed"
                and (not existing.result or existing.result.get("status") in {"rejected", "not_sent"})
            ):
                existing.proposal_id, existing.state, existing.result = proposal.id, "queued", None
                operation = existing
                audit(self.session, self.principal, "slack.retry_requested", operation.id)
            else:
                job = self.session.scalar(
                    select(Job)
                    .where(
                        Job.kind == "slack_publish", Job.payload["operation_id"].as_string() == existing.id
                    )
                    .order_by(Job.created_at.desc())
                )
                return {
                    "operation_id": existing.id,
                    "job_id": job.id if job else None,
                    "state": existing.state,
                }
        else:
            operation = SlackOperation(proposal_id=proposal.id, delivery_key=delivery_key)
            self.session.add(operation)
        proposal.approved_at = now()
        self.session.flush()
        job = Job(
            workspace_id=self.principal.scope,
            meeting_id=proposal.meeting_id,
            actor_id=self.principal.user_id,
            kind="slack_publish",
            payload={"operation_id": operation.id},
        )
        self.session.add(job)
        self.session.flush()
        audit(self.session, self.principal, "slack.approved", proposal.id, {"payload_hash": payload_hash})
        return {"operation_id": operation.id, "job_id": job.id, "state": "queued"}

    def receipt(self, identifier):
        operation = self.session.get(SlackOperation, identifier)
        if not operation:
            raise ServiceError(status_code=404, error="Slack receipt not found", where="client")
        proposal = self.proposal(operation.proposal_id)
        meeting = self.session.get(Meeting, proposal.meeting_id)
        if not meeting:
            raise ServiceError(status_code=404, error="Meeting not found", where="client")
        meeting_access(self.session, self.principal, meeting.slug)
        return operation, proposal

    def receipt_payload(self, operation, proposal):
        ready = connection_status(self.session, self.principal)["can_create"]
        binding = self.session.scalar(binding_query(self.principal))
        account = self.session.get(SlackAccount, binding.connection_id) if binding else None
        current_destination = False
        if binding and account:
            try:
                current_destination = (
                    destination_snapshot(self.session, binding, account) == proposal.destination
                )
            except ServiceError:
                pass
        retry_current = ready and current_destination and aware(proposal.expires_at) > now()
        if retry_current:
            try:
                self.validate(proposal, binding, account)
            except ServiceError:
                retry_current = False
        return {
            "operation_id": operation.id,
            "proposal_id": proposal.id,
            "action": proposal.action,
            "state": operation.state,
            "result": operation.result,
            "source_versions": proposal.snapshots,
            "created_at": operation.created_at.isoformat(),
            "can_reconcile": ready and current_destination and operation.state == "uncertain",
            "can_retry_rejected": retry_current
            and operation.state == "failed"
            and (not operation.result or operation.result.get("status") in {"rejected", "not_sent"}),
            "proposal": self.serialize(proposal),
        }

    def history(self, meeting_slug):
        meeting = meeting_access(self.session, self.principal, meeting_slug)
        rows = self.session.execute(
            select(SlackOperation, SlackProposal)
            .join(SlackProposal)
            .where(
                SlackProposal.meeting_id == meeting.id,
                SlackProposal.workspace_id == self.principal.scope,
                SlackProposal.actor_id == self.principal.user_id,
            )
            .order_by(SlackOperation.created_at.desc())
            .limit(50)
        ).all()
        return [self.receipt_payload(operation, proposal) for operation, proposal in rows]

    async def reconcile(self, identifier, message_ts):
        _, binding, account, token = await self.adapter.access(self.session, self.principal)
        operation, proposal = self.receipt(identifier)
        operation = self.session.scalar(
            select(SlackOperation).where(SlackOperation.id == operation.id).with_for_update()
        )
        if not operation or operation.state != "uncertain":
            raise ServiceError(
                status_code=409, error="Only uncertain Slack deliveries need reconciliation", where="client"
            )
        if proposal.destination != destination_snapshot(self.session, binding, account) or (
            proposal.target and proposal.target["message_ts"] != message_ts
        ):
            raise ServiceError(
                status_code=409, error="Reconcile the original Slack destination and message", where="client"
            )
        operation.result = await self.adapter.verify(token, proposal, message_ts)
        operation.state = "completed"
        audit(self.session, self.principal, "slack.reconciled", operation.id)
        return self.receipt_payload(operation, proposal)
