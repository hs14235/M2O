"""Exact member-post approval, owned consent and durable uncertain-write handling."""

import logging
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from sqlalchemy import delete, select

from ..access_policy import is_private_scope, require_private_account, require_private_scope
from ..auth import Principal, aware, digest, require_role
from ..database import session_scope
from ..linkedin import AUTHORIZATION_URL
from ..linkedin_publishing import PUBLISHING_SCOPES, LinkedInPublishingAdapter, UncertainLinkedInWrite
from ..models import (
    IntegrationOAuthState,
    Job,
    LinkedInOperation,
    LinkedInProposal,
    Meeting,
    Membership,
    ProviderConnection,
    ProviderDestination,
    User,
    Workspace,
    now,
)
from ..provider_credentials import seal, unseal
from ..settings import settings
from .common import audit, fingerprint, meeting_access
from .errors import ServiceError
from .linkedin_drafts import LinkedInDraftService

logger = logging.getLogger("meeting.providers")


class LinkedInPublishingService:
    def __init__(self, session, principal, adapter=None):
        self.session, self.principal = session, principal
        self.adapter = adapter or LinkedInPublishingAdapter()

    def connection(self, *, lock=False):
        query = select(ProviderConnection).where(
            ProviderConnection.user_id == self.principal.user_id, ProviderConnection.provider == "linkedin"
        )
        return self.session.scalar(
            query.with_for_update().execution_options(populate_existing=True) if lock else query
        )

    def association(self, connection):
        return self.session.scalar(
            select(ProviderDestination)
            .where(
                ProviderDestination.connection_id == connection.id,
                ProviderDestination.user_id == self.principal.user_id,
                ProviderDestination.workspace_id == self.principal.workspace_id,
            )
            .execution_options(populate_existing=True)
        )

    def associate(self, connection):
        # Caller holds the connection lock; privacy cleanup takes that same lock
        # before deciding whether any other workspace still needs this grant.
        if self.association(connection) is None:
            self.session.add(
                ProviderDestination(
                    connection_id=connection.id,
                    user_id=self.principal.user_id,
                    workspace_id=self.principal.workspace_id,
                )
            )
            self.session.flush()

    def live_workspace(self):
        self.session.scalar(
            select(Workspace)
            .where(Workspace.id == self.principal.workspace_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        self.require_enabled()

    def status(self) -> dict:
        if not is_private_scope(self.session, self.principal):
            return {
                "configured": False,
                "state": "not_connected",
                "author": None,
                "expires_at": None,
                "can_connect": False,
                "can_publish": False,
                "can_draft": self.principal.role in {"owner", "reviewer", "editor"},
                "can_message": False,
                "can_reconcile": False,
            }
        row = self.connection()
        associated = bool(row and self.association(row))
        ready = bool(
            row
            and associated
            and row.state == "connected"
            and row.expires_at is not None
            and aware(row.expires_at) > now()
            and PUBLISHING_SCOPES.issubset(set(row.scopes))
        )
        can_publish = (
            ready
            and settings.linkedin_publishing_configured
            and not settings.public_demo_mode
            and self.principal.role in {"owner", "reviewer"}
        )
        return {
            "configured": settings.linkedin_publishing_configured,
            "state": "connected" if ready else "reauthorization_required" if row else "not_connected",
            "author": unseal(row).get("author")
            if ready and settings.linkedin_publishing_configured
            else None,
            "expires_at": aware(row.expires_at).isoformat()
            if row and associated and row.expires_at
            else None,
            "can_connect": settings.linkedin_publishing_configured
            and not settings.public_demo_mode
            and self.principal.role in {"owner", "reviewer"},
            "can_publish": can_publish,
            "can_draft": self.principal.role in {"owner", "reviewer", "editor"},
            "can_message": False,
            "can_reconcile": False,
        }

    def require_enabled(self):
        require_role(self.principal, {"owner", "reviewer"})
        require_private_scope(self.session, self.principal)
        if settings.public_demo_mode:
            raise ServiceError(
                status_code=403, error="Demo mode does not connect or publish to LinkedIn", where="client"
            )
        if not settings.linkedin_publishing_configured:
            raise ServiceError(
                status_code=503,
                error="LinkedIn publishing requires approved product configuration",
                where="linkedin",
            )

    def begin(self) -> dict:
        self.session.scalar(select(User).where(User.id == self.principal.user_id).with_for_update())
        self.require_enabled()
        if not self.principal.session_hash:
            raise ServiceError(
                status_code=403, error="Connect publishing from a signed-in browser session", where="client"
            )
        state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self.session.execute(
            delete(IntegrationOAuthState).where(
                IntegrationOAuthState.user_id == self.principal.user_id,
                IntegrationOAuthState.workspace_id == self.principal.workspace_id,
                IntegrationOAuthState.provider == "linkedin",
            )
        )
        self.session.add(
            IntegrationOAuthState(
                state_hash=digest(state),
                user_id=self.principal.user_id,
                workspace_id=self.principal.workspace_id,
                provider="linkedin",
                session_hash=self.principal.session_hash,
                nonce=nonce,
                expires_at=now() + timedelta(minutes=10),
            )
        )
        return {
            "url": AUTHORIZATION_URL
            + "?"
            + urlencode(
                {
                    "response_type": "code",
                    "client_id": settings.linkedin_client_id,
                    "redirect_uri": settings.linkedin_publishing_redirect_uri,
                    "scope": " ".join(sorted(PUBLISHING_SCOPES)),
                    "state": state,
                    "nonce": nonce,
                }
            )
        }

    async def complete(self, state: str, code: str | None, denied: bool = False) -> dict:
        # Disconnect uses the same user lock so a pending exchange cannot restore
        # credentials after a completed disconnect.
        user = self.session.scalar(
            select(User)
            .where(User.id == self.principal.user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        row = self.session.scalar(
            select(IntegrationOAuthState)
            .where(
                IntegrationOAuthState.state_hash == digest(state),
                IntegrationOAuthState.provider == "linkedin",
            )
            .with_for_update()
        )
        if (
            not row
            or row.user_id != self.principal.user_id
            or row.session_hash != self.principal.session_hash
            or aware(row.expires_at) <= now()
            or not row.nonce
        ):
            raise ServiceError(
                status_code=400, error="LinkedIn publishing state is invalid or expired", where="linkedin"
            )
        member = self.session.scalar(
            select(Membership)
            .where(Membership.workspace_id == row.workspace_id, Membership.user_id == row.user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if not member or member.role not in {"owner", "reviewer"} or not user or not user.active:
            raise ServiceError(
                status_code=403, error="LinkedIn connection authority was revoked", where="client"
            )
        self.principal = Principal(
            row.user_id, row.workspace_id, member.role, session_hash=self.principal.session_hash
        )
        self.require_enabled()
        nonce = row.nonce
        self.session.delete(row)
        if denied or not code:
            self.session.commit()
            raise ServiceError(
                status_code=400, error="LinkedIn publishing consent was cancelled", where="linkedin"
            )
        try:
            credentials = await self.adapter.exchange(code, nonce)
        except ServiceError:
            self.session.commit()
            raise
        try:
            self.live_workspace()
        except ServiceError:
            self.session.commit()
            raise
        connection = self.connection(lock=True)
        if (
            connection
            and connection.encrypted_credentials
            and unseal(connection).get("author") != credentials["author"]
        ):
            self.session.commit()
            raise ServiceError(
                status_code=409,
                error="Disconnect the publishing account before linking another",
                where="linkedin",
            )
        if not connection:
            connection = ProviderConnection(
                user_id=self.principal.user_id,
                provider="linkedin",
                encrypted_credentials="",
                scopes=credentials["scopes"],
                expires_at=credentials["expires_at"],
            )
            self.session.add(connection)
            self.session.flush()
        connection.state, connection.updated_at, connection.scopes, connection.expires_at = (
            "connected",
            now(),
            credentials["scopes"],
            credentials["expires_at"],
        )
        connection.encrypted_credentials = seal(
            connection, {"access_token": credentials["access_token"], "author": credentials["author"]}
        )
        self.associate(connection)
        audit(self.session, self.principal, "linkedin.publishing_connected", connection.id)
        return {"workspace_id": self.principal.workspace_id, "connected": True}

    def disconnect(self) -> dict:
        self.session.scalar(select(User).where(User.id == self.principal.user_id).with_for_update())
        require_private_scope(self.session, self.principal)
        return self.disconnect_account()

    def disconnect_account(self) -> dict:
        self.session.scalar(select(User).where(User.id == self.principal.user_id).with_for_update())
        require_private_account(self.session, self.principal)
        connection = self.connection(lock=True)
        if connection:
            # Retain referenced account identity but delete its encrypted token.
            connection.encrypted_credentials, connection.state, connection.updated_at = (
                "",
                "reauthorization_required",
                now(),
            )
            if self.principal.workspace_id is not None:
                audit(self.session, self.principal, "linkedin.publishing_disconnected", connection.id)
            else:
                logger.info("linkedin.publishing_disconnected", extra={"actor_id": self.principal.user_id})
        self.session.execute(
            delete(IntegrationOAuthState).where(
                IntegrationOAuthState.user_id == self.principal.user_id,
                IntegrationOAuthState.provider == "linkedin",
            )
        )
        return {"connected": False}

    def access(self):
        self.require_enabled()
        user = self.session.scalar(
            select(User)
            .where(User.id == self.principal.user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        member = self.session.scalar(
            select(Membership)
            .where(
                Membership.workspace_id == self.principal.workspace_id,
                Membership.user_id == self.principal.user_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if not member or member.role not in {"owner", "reviewer"} or not user or not user.active:
            raise ServiceError(
                status_code=403, error="LinkedIn publication authority was revoked", where="client"
            )
        self.live_workspace()
        row = self.connection(lock=True)
        if (
            not row
            or row.state != "connected"
            or row.expires_at is None
            or aware(row.expires_at) <= now()
            or not PUBLISHING_SCOPES.issubset(set(row.scopes))
        ):
            raise ServiceError(
                status_code=409,
                error="Reconnect LinkedIn publishing with a current posting grant",
                where="linkedin",
            )
        credentials = unseal(row)
        if (
            not isinstance(credentials.get("access_token"), str)
            or not credentials["access_token"]
            or not isinstance(credentials.get("author"), str)
        ):
            raise ServiceError(status_code=409, error="Reconnect LinkedIn publishing", where="linkedin")
        self.associate(row)
        return row, credentials

    @staticmethod
    def hash(proposal) -> str:
        return fingerprint(
            [
                proposal.workspace_id,
                proposal.actor_id,
                proposal.draft_id,
                proposal.draft_version,
                proposal.connection_id,
                aware(proposal.connection_updated_at).isoformat(),
                proposal.author,
                proposal.payload,
                proposal.snapshots,
            ]
        )

    def preview(self, meeting_id, payload) -> dict:
        row, meeting = LinkedInDraftService(self.session, self.principal).get(
            meeting_id, payload.draft_id, lock=True
        )
        if (
            row.kind != "post"
            or row.version != payload.expected_draft_version
            or not LinkedInDraftService(self.session, self.principal).current(row, meeting)
        ):
            raise ServiceError(
                status_code=409, error="Select a current post draft before publishing", where="client"
            )
        if not payload.disclosure_confirmed:
            raise ServiceError(
                status_code=403, error="Confirm that this draft may be disclosed publicly", where="client"
            )
        connection, credentials = self.access()
        proposal = LinkedInProposal(
            workspace_id=self.principal.workspace_id,
            meeting_id=meeting.id,
            actor_id=self.principal.user_id,
            draft_id=row.id,
            draft_version=row.version,
            connection_id=connection.id,
            connection_updated_at=connection.updated_at,
            author=credentials["author"],
            payload={
                "body": self.adapter.payload(credentials["author"], row.text),
                "api_version": settings.linkedin_api_version,
            },
            snapshots=row.snapshots,
            payload_hash="",
            expires_at=now() + timedelta(minutes=30),
        )
        proposal.payload_hash = self.hash(proposal)
        self.session.add(proposal)
        self.session.flush()
        audit(
            self.session,
            self.principal,
            "linkedin.previewed",
            proposal.id,
            {"draft_version": row.version, "public_disclosure_confirmed": True},
        )
        return {
            "id": proposal.id,
            "draft_id": row.id,
            "draft_version": row.version,
            "author": proposal.author,
            "audience": "PUBLIC",
            "payload": proposal.payload["body"],
            "api_version": proposal.payload["api_version"],
            "payload_hash": proposal.payload_hash,
            "expires_at": proposal.expires_at.isoformat(),
            "approved": False,
            "sources": proposal.snapshots,
        }

    def proposal(self, proposal_id, *, lock=False):
        query = select(LinkedInProposal).where(
            LinkedInProposal.id == proposal_id,
            LinkedInProposal.workspace_id == self.principal.workspace_id,
            LinkedInProposal.actor_id == self.principal.user_id,
        )
        row = self.session.scalar(query.with_for_update() if lock else query)
        if row is None:
            raise ServiceError(status_code=404, error="LinkedIn preview not found", where="client")
        return row

    def validate(self, proposal):
        meeting = self.session.get(Meeting, proposal.meeting_id)
        if meeting is None:
            raise ServiceError(status_code=404, error="Meeting not found", where="client")
        row, meeting = LinkedInDraftService(self.session, self.principal).get(
            meeting.slug, proposal.draft_id, lock=True
        )
        connection, credentials = self.access()
        if (
            row.version != proposal.draft_version
            or not LinkedInDraftService(self.session, self.principal).current(row, meeting)
            or connection.id != proposal.connection_id
            or aware(connection.updated_at) != aware(proposal.connection_updated_at)
            or credentials["author"] != proposal.author
            or self.hash(proposal) != proposal.payload_hash
        ):
            raise ServiceError(
                status_code=409,
                error="LinkedIn preview is stale; prepare and review a new preview",
                where="client",
            )
        return credentials

    def approve(self, proposal_id, payload_hash) -> dict:
        proposal = self.proposal(proposal_id, lock=True)
        if proposal.payload_hash != payload_hash or aware(proposal.expires_at) <= now():
            raise ServiceError(
                status_code=409, error="LinkedIn preview hash or expiration is invalid", where="client"
            )
        self.validate(proposal)
        key = fingerprint([proposal.workspace_id, proposal.author, proposal.draft_id, proposal.draft_version])
        operation = self.session.scalar(
            select(LinkedInOperation).where(LinkedInOperation.delivery_key == key)
        )
        if operation:
            job = self.session.scalar(
                select(Job).where(
                    Job.kind == "linkedin_publish", Job.payload["operation_id"].as_string() == operation.id
                )
            )
            return {"operation_id": operation.id, "job_id": job.id if job else None, "state": operation.state}
        proposal.approved_at = now()
        operation = LinkedInOperation(proposal_id=proposal.id, delivery_key=key)
        self.session.add(operation)
        self.session.flush()
        job = Job(
            workspace_id=proposal.workspace_id,
            meeting_id=proposal.meeting_id,
            actor_id=self.principal.user_id,
            kind="linkedin_publish",
            payload={"operation_id": operation.id},
        )
        self.session.add(job)
        self.session.flush()
        audit(self.session, self.principal, "linkedin.approved", proposal.id, {"payload_hash": payload_hash})
        return {"operation_id": operation.id, "job_id": job.id, "state": job.state}

    @staticmethod
    def receipt(operation, proposal) -> dict:
        return {
            "operation_id": operation.id,
            "proposal_id": proposal.id,
            "state": operation.state,
            "result": operation.result,
            "author": proposal.author,
            "draft_id": proposal.draft_id,
            "draft_version": proposal.draft_version,
            "created_at": operation.created_at.isoformat(),
            "can_reconcile": False,
            "can_retry_rejected": False,
        }

    def operation(self, operation_id) -> dict:
        row = self.session.execute(
            select(LinkedInOperation, LinkedInProposal)
            .join(LinkedInProposal, LinkedInProposal.id == LinkedInOperation.proposal_id)
            .where(
                LinkedInOperation.id == operation_id,
                LinkedInProposal.workspace_id == self.principal.workspace_id,
                LinkedInProposal.actor_id == self.principal.user_id,
            )
        ).first()
        if row is None:
            raise ServiceError(status_code=404, error="LinkedIn delivery not found", where="client")
        operation, proposal = row
        meeting = self.session.get(Meeting, proposal.meeting_id)
        if not meeting:
            raise ServiceError(status_code=404, error="Meeting not found", where="client")
        meeting_access(self.session, self.principal, meeting.slug)
        return self.receipt(operation, proposal)

    def history(self, meeting_id) -> list[dict]:
        meeting = meeting_access(self.session, self.principal, meeting_id)
        rows = self.session.execute(
            select(LinkedInOperation, LinkedInProposal)
            .join(LinkedInProposal, LinkedInProposal.id == LinkedInOperation.proposal_id)
            .where(
                LinkedInProposal.workspace_id == self.principal.workspace_id,
                LinkedInProposal.meeting_id == meeting.id,
                LinkedInProposal.actor_id == self.principal.user_id,
            )
            .order_by(LinkedInOperation.created_at.desc(), LinkedInOperation.id.desc())
            .limit(50)
        ).all()
        return [self.receipt(operation, proposal) for operation, proposal in rows]


async def publish_linkedin(record, adapter=None):
    from ..worker import authorized, owned_job

    adapter = adapter or LinkedInPublishingAdapter()
    with session_scope() as session:
        job = owned_job(session, record)
        principal, _ = authorized(session, job)
        operation = session.scalar(
            select(LinkedInOperation)
            .where(LinkedInOperation.id == job.payload["operation_id"])
            .with_for_update()
        )
        if not operation:
            raise ServiceError(status_code=404, error="LinkedIn delivery not found", where="client")
        service = LinkedInPublishingService(session, principal, adapter)
        proposal = service.proposal(operation.proposal_id, lock=True)
        if not proposal.approved_at:
            raise ServiceError(
                status_code=403, error="LinkedIn delivery has not been approved", where="client"
            )
        credentials = service.validate(proposal)
        if operation.state == "completed":
            return {"operation_id": operation.id, "state": operation.state, "result": operation.result}
        if operation.state != "queued" or record["recovered"]:
            operation.state, operation.result = (
                "uncertain",
                {
                    "status": "uncertain",
                    "error": "Recovered delivery requires investigation; no post repeated",
                },
            )
            return {"operation_id": operation.id, "state": operation.state, "result": operation.result}
        operation.state, operation.result = (
            "sending",
            {"status": "uncertain", "error": "Write intent recorded"},
        )
        session.commit()
        job = owned_job(session, record)
        principal, _ = authorized(session, job)
        service = LinkedInPublishingService(session, principal, adapter)
        proposal = service.proposal(operation.proposal_id, lock=True)
        credentials = service.validate(proposal)
        try:
            operation.result = await adapter.publish(
                credentials["access_token"], proposal.payload["body"], proposal.payload["api_version"]
            )
            operation.state = "completed"
        except UncertainLinkedInWrite:
            operation.state, operation.result = (
                "uncertain",
                {
                    "status": "uncertain",
                    "error": "LinkedIn did not confirm the post; inspect your account before any further action",
                },
            )
        except ServiceError as exc:
            operation.state, operation.result = (
                "failed",
                {"status": "rejected", "error": "LinkedIn rejected the post; inspect permissions or content"},
            )
            if exc.detail.get("provider_status") in {401, 403}:
                connection = service.connection(lock=True)
                if connection:
                    connection.state, connection.updated_at = "reauthorization_required", now()
        audit(session, principal, "linkedin.delivery_recorded", operation.id, {"state": operation.state})
        return {"operation_id": operation.id, "state": operation.state, "result": operation.result}
