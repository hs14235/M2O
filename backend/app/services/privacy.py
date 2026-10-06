"""Scoped export, local erasure and minimum delivery retention with a freeze boundary."""

import secrets
from datetime import timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from ..access_policy import account
from ..auth import Principal
from ..models import (
    ApiToken,
    AuditEvent,
    AuthSession,
    DeliveryTombstone,
    ExtractionRun,
    GoogleMeetPreview,
    IntegrationOAuthState,
    Invitation,
    JiraOperation,
    JiraProposal,
    Job,
    LinkedInDraft,
    LinkedInOperation,
    LinkedInProfile,
    LinkedInProposal,
    Meeting,
    MeetingImport,
    Membership,
    OAuthState,
    Participant,
    ParticipantMention,
    PasswordRecovery,
    PlanEntry,
    ProviderConnection,
    ProviderDestination,
    PublicationOperation,
    PublicationProposal,
    SlackIdentity,
    SlackLinkChallenge,
    SlackOperation,
    SlackProposal,
    TranscriptChunk,
    TranscriptRevision,
    User,
    WorkItem,
    WorkItemEvidence,
    WorkItemRevision,
    Workspace,
    now,
)
from ..schemas import WorkspaceErasureInput
from ..settings import settings
from .common import audit
from .errors import ServiceError
from .lifecycle import cancel_actor_jobs, owner_lock, reauthenticate
from .meetings import MeetingService
from .review import ReviewService

PROPOSALS = (
    ("github", PublicationProposal, PublicationOperation),
    ("jira", JiraProposal, JiraOperation),
    ("slack", SlackProposal, SlackOperation),
    ("linkedin", LinkedInProposal, LinkedInOperation),
)
RECEIPT_FIELDS = {"status", "id", "key", "number", "post_id", "message_ts", "channel_id", "provider_effect"}


def minimal_receipt(result) -> dict:
    rows = result if isinstance(result, list) else [result] if isinstance(result, dict) else []
    return {
        "resources": [
            {
                key: value
                for key, value in row.items()
                if key in RECEIPT_FIELDS and isinstance(value, (str, int)) and len(str(value)) <= 300
            }
            for row in rows
        ]
    }


class PrivacyService:
    def __init__(self, session: Session):
        self.session = session

    def account_export(self, principal: Principal) -> dict:
        user = account(self.session, principal)
        memberships = self.session.execute(
            select(Workspace, Membership.role)
            .join(Membership)
            .where(
                Membership.user_id == user.id,
                Workspace.erasure_requested_at.is_(None),
                Workspace.erased_at.is_(None),
                Workspace.is_demo == user.is_visitor,
            )
        ).all()
        plans = self.session.scalars(
            select(PlanEntry).where(PlanEntry.user_id == user.id).order_by(PlanEntry.id)
        ).all()
        drafts = self.session.scalars(
            select(LinkedInDraft).where(LinkedInDraft.actor_id == user.id).order_by(LinkedInDraft.id)
        ).all()
        profile = self.session.get(LinkedInProfile, user.id)
        return {
            "schema_version": 1,
            "generated_at": now().isoformat(),
            "account": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "is_visitor": user.is_visitor,
                "created_at": user.created_at.isoformat(),
            },
            "memberships": [
                {
                    "workspace_id": workspace.id,
                    "name": workspace.name,
                    "department": workspace.department,
                    "role": role,
                }
                for workspace, role in memberships
            ],
            "personal_plan": [
                {
                    "id": row.id,
                    "item_id": row.item_id,
                    "planned_on": row.planned_on,
                    "state": row.state,
                    "priority": row.priority,
                    "reviewed_version": row.reviewed_version,
                }
                for row in plans
            ],
            "linkedin_drafts": [
                {
                    "id": row.id,
                    "workspace_id": row.workspace_id,
                    "meeting_id": row.meeting_id,
                    "kind": row.kind,
                    "text": row.text,
                    "version": row.version,
                }
                for row in drafts
            ],
            "linkedin_profile": profile.profile if profile else None,
        }

    def workspace_export(self, principal: Principal) -> dict:
        workspace = owner_lock(self.session, principal)
        characters = (
            self.session.scalar(
                select(func.coalesce(func.sum(func.length(TranscriptRevision.raw_text)), 0))
                .join(Meeting)
                .where(Meeting.workspace_id == workspace.id)
            )
            or 0
        )
        if characters > 2_000_000:
            raise ServiceError(
                status_code=413,
                error="Workspace exceeds the browser export limit; use the operator database backup procedure",
                where="client",
            )
        meetings = self.session.scalars(
            select(Meeting).where(Meeting.workspace_id == workspace.id).order_by(Meeting.id)
        ).all()
        # Include archived records explicitly; an archive still contains local data.
        records = []
        for meeting in meetings:
            revisions = self.session.scalars(
                select(TranscriptRevision)
                .where(TranscriptRevision.meeting_id == meeting.id)
                .order_by(TranscriptRevision.number)
            ).all()
            histories = []
            for revision in revisions:
                chunks = self.session.scalars(
                    select(TranscriptChunk)
                    .where(TranscriptChunk.revision_id == revision.id)
                    .order_by(TranscriptChunk.chunk_index)
                ).all()
                items = self.session.scalars(
                    select(WorkItem).where(WorkItem.revision_id == revision.id).order_by(WorkItem.id)
                ).all()
                item_payloads = []
                for item in items:
                    reviews = self.session.scalars(
                        select(WorkItemRevision)
                        .where(WorkItemRevision.item_id == item.id)
                        .order_by(WorkItemRevision.version)
                    ).all()
                    item_payloads.append(
                        {
                            **ReviewService(self.session, principal).item_payload(item),
                            "review_history": [
                                {
                                    "version": review.version,
                                    "actor_id": review.actor_id,
                                    "created_at": review.created_at.isoformat(),
                                    "payload": review.payload,
                                }
                                for review in reviews
                            ],
                        }
                    )
                histories.append(
                    {
                        "number": revision.number,
                        "raw_text": revision.raw_text,
                        "chunking_version": revision.chunking_version,
                        "embedding_provider": revision.embed_provider,
                        "evidence": [
                            {
                                "id": row.id,
                                "text": row.text,
                                "start_line": row.start_line,
                                "speaker": row.speaker,
                            }
                            for row in chunks
                        ],
                        "outcomes": item_payloads,
                    }
                )
            records.append(
                {
                    **MeetingService.summary(meeting),
                    "archived": bool(meeting.archived_at),
                    "revisions": histories,
                    "import_source": self.session.scalar(
                        select(MeetingImport.source).where(MeetingImport.meeting_id == meeting.id)
                    ),
                }
            )
        receipts = []
        for provider, proposal_model, operation_model in PROPOSALS:
            for proposal, operation in self.session.execute(
                select(proposal_model, operation_model)
                .join(operation_model, operation_model.proposal_id == proposal_model.id)
                .where(proposal_model.workspace_id == workspace.id)
            ):
                result = (
                    operation.results if isinstance(operation, PublicationOperation) else operation.result
                )
                receipts.append(
                    {
                        "provider": provider,
                        "operation_id": operation.id,
                        "meeting_id": proposal.meeting_id,
                        "payload_hash": proposal.payload_hash,
                        "state": operation.state,
                        "created_at": operation.created_at.isoformat(),
                        "receipt": minimal_receipt(result),
                    }
                )
        events = self.session.scalars(
            select(AuditEvent)
            .where(AuditEvent.workspace_id == workspace.id)
            .order_by(AuditEvent.created_at, AuditEvent.id)
        ).all()
        return {
            "schema_version": 1,
            "generated_at": now().isoformat(),
            "workspace": {
                "id": workspace.id,
                "name": workspace.name,
                "department": workspace.department,
                "version": workspace.version,
            },
            "participants": ReviewService(self.session, principal).participants(),
            "meetings": records,
            "delivery_receipts": receipts,
            "audit": [
                {
                    "id": event.id,
                    "actor_id": event.actor_id,
                    "action": event.action,
                    "target_id": event.target_id,
                    "created_at": event.created_at.isoformat(),
                    "details": {
                        key: value
                        for key, value in event.details.items()
                        if key
                        in {
                            "role",
                            "version",
                            "revision",
                            "position",
                            "status",
                            "state",
                            "payload_hash",
                            "chunk_count",
                            "created",
                            "mode",
                        }
                    },
                }
                for event in events
            ],
        }

    def workspace_status(self, principal: Principal) -> dict:
        user = account(self.session, principal)
        workspace = self.session.get(Workspace, principal.scope)
        member = self.session.get(Membership, (principal.scope, principal.user_id))
        if (
            not workspace
            or not member
            or user.is_visitor != workspace.is_demo
            or principal.token_workspace_id
            and principal.token_workspace_id != workspace.id
        ):
            raise ServiceError(status_code=404, error="Workspace not found", where="client")
        return {
            "id": workspace.id,
            "name": workspace.name,
            "version": workspace.version,
            "state": "erased"
            if workspace.erased_at
            else "pending_erasure"
            if workspace.erasure_requested_at
            else "active",
            "can_erase": member.role == "owner" and not user.is_visitor,
            "retention_days": settings.privacy_tombstone_days,
            "remote_content_erased": False,
        }

    def erase_workspace(self, principal: Principal, payload: WorkspaceErasureInput) -> dict:
        workspace = owner_lock(self.session, principal, allow_erasing=True)
        reauthenticate(self.session, principal, payload.password)
        if workspace.name != payload.confirmation_name or workspace.version != payload.expected_version:
            raise ServiceError(
                status_code=409,
                error="Confirm the current workspace name and version before erasure",
                where="client",
            )
        if workspace.erasure_requested_at is None:
            workspace.erasure_requested_at, workspace.version = now(), workspace.version + 1
            audit(self.session, principal, "privacy.workspace_frozen", workspace.id)
        workspace_id = workspace.id
        # Workers observe revoked scope before any cleanup waits for their job rows.
        self.session.commit()
        return self.purge_workspace(workspace_id)

    def purge_workspace(self, workspace_id: str) -> dict:
        workspace = self.session.get(Workspace, workspace_id)
        if not workspace or not workspace.erasure_requested_at:
            raise ServiceError(
                status_code=409, error="Freeze workspace authority before erasing its data", where="client"
            )
        try:
            jobs = self.session.scalars(
                select(Job)
                .where(Job.workspace_id == workspace_id)
                .order_by(Job.id)
                .with_for_update(nowait=True)
                .execution_options(populate_existing=True)
            ).all()
        except OperationalError as exc:
            if getattr(exc.orig, "sqlstate", None) != "55P03":
                raise
            self.session.rollback()
            return {
                "ok": True,
                "state": "pending_erasure",
                "workspace_id": workspace_id,
                "retry_required": True,
                "remote_content_erased": False,
            }
        if any(job.state == "running" for job in jobs):
            return {
                "ok": True,
                "state": "pending_erasure",
                "workspace_id": workspace_id,
                "retry_required": True,
                "remote_content_erased": False,
            }
        connections = set(
            self.session.scalars(
                select(ProviderDestination.connection_id).where(
                    ProviderDestination.workspace_id == workspace_id
                )
            )
        )
        connections.update(
            self.session.scalars(
                select(LinkedInProposal.connection_id).where(LinkedInProposal.workspace_id == workspace_id)
            )
        )
        connections.update(
            self.session.scalars(
                select(MeetingImport.connection_id).where(MeetingImport.workspace_id == workspace_id)
            )
        )
        for provider, proposal_model, operation_model in PROPOSALS:
            proposals = self.session.scalars(
                select(proposal_model).where(proposal_model.workspace_id == workspace_id)
            ).all()
            for proposal in proposals:
                operation = self.session.scalar(
                    select(operation_model).where(operation_model.proposal_id == proposal.id)
                )
                if operation:
                    if isinstance(operation, PublicationOperation):
                        result, key = operation.results, operation.publication_key
                    else:
                        result, key = operation.result, operation.delivery_key
                    self.session.add(
                        DeliveryTombstone(
                            workspace_id=workspace_id,
                            provider=provider,
                            operation_id=operation.id,
                            delivery_key=key,
                            payload_hash=proposal.payload_hash,
                            state=operation.state,
                            receipt=minimal_receipt(result),
                            retained_until=now() + timedelta(days=settings.privacy_tombstone_days),
                        )
                    )
        self.session.flush()
        self.session.execute(delete(Job).where(Job.workspace_id == workspace_id))
        for _, proposal_model, operation_model in PROPOSALS:
            proposal_ids = select(proposal_model.id).where(proposal_model.workspace_id == workspace_id)
            self.session.execute(delete(operation_model).where(operation_model.proposal_id.in_(proposal_ids)))
            self.session.execute(delete(proposal_model).where(proposal_model.workspace_id == workspace_id))
        self.session.execute(delete(LinkedInDraft).where(LinkedInDraft.workspace_id == workspace_id))
        meeting_ids = select(Meeting.id).where(Meeting.workspace_id == workspace_id)
        revision_ids = select(TranscriptRevision.id).where(TranscriptRevision.meeting_id.in_(meeting_ids))
        item_ids = select(WorkItem.id).where(WorkItem.workspace_id == workspace_id)
        self.session.execute(delete(PlanEntry).where(PlanEntry.item_id.in_(item_ids)))
        self.session.execute(delete(WorkItemRevision).where(WorkItemRevision.item_id.in_(item_ids)))
        self.session.execute(delete(WorkItemEvidence).where(WorkItemEvidence.item_id.in_(item_ids)))
        self.session.execute(delete(WorkItem).where(WorkItem.workspace_id == workspace_id))
        self.session.execute(
            delete(ParticipantMention).where(ParticipantMention.workspace_id == workspace_id)
        )
        self.session.execute(delete(ExtractionRun).where(ExtractionRun.revision_id.in_(revision_ids)))
        self.session.execute(delete(TranscriptChunk).where(TranscriptChunk.revision_id.in_(revision_ids)))
        self.session.execute(delete(GoogleMeetPreview).where(GoogleMeetPreview.workspace_id == workspace_id))
        self.session.execute(delete(MeetingImport).where(MeetingImport.workspace_id == workspace_id))
        self.session.execute(delete(TranscriptRevision).where(TranscriptRevision.meeting_id.in_(meeting_ids)))
        self.session.execute(delete(Meeting).where(Meeting.workspace_id == workspace_id))
        self.session.execute(delete(Participant).where(Participant.workspace_id == workspace_id))
        self.session.execute(delete(SlackIdentity).where(SlackIdentity.workspace_id == workspace_id))
        self.session.execute(
            delete(SlackLinkChallenge).where(SlackLinkChallenge.workspace_id == workspace_id)
        )
        self.session.execute(
            delete(IntegrationOAuthState).where(IntegrationOAuthState.workspace_id == workspace_id)
        )
        self.session.execute(delete(ApiToken).where(ApiToken.workspace_id == workspace_id))
        from ..models import GitHubDestination

        self.session.execute(delete(GitHubDestination).where(GitHubDestination.workspace_id == workspace_id))
        self.session.execute(
            delete(ProviderDestination).where(ProviderDestination.workspace_id == workspace_id)
        )
        for connection_id in connections:
            connection = self.session.scalar(
                select(ProviderConnection)
                .where(ProviderConnection.id == connection_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            active_binding = self.session.scalar(
                select(ProviderDestination.id)
                .join(Workspace, Workspace.id == ProviderDestination.workspace_id)
                .where(
                    ProviderDestination.connection_id == connection_id,
                    Workspace.erasure_requested_at.is_(None),
                    Workspace.erased_at.is_(None),
                )
                .limit(1)
            )
            active_publication = self.session.scalar(
                select(LinkedInProposal.id)
                .join(Workspace, Workspace.id == LinkedInProposal.workspace_id)
                .where(
                    LinkedInProposal.connection_id == connection_id,
                    Workspace.erasure_requested_at.is_(None),
                    Workspace.erased_at.is_(None),
                )
                .limit(1)
            )
            active_import = self.session.scalar(
                select(MeetingImport.id)
                .join(Workspace, Workspace.id == MeetingImport.workspace_id)
                .where(
                    MeetingImport.connection_id == connection_id,
                    Workspace.erasure_requested_at.is_(None),
                    Workspace.erased_at.is_(None),
                )
                .limit(1)
            )
            if connection and not active_binding and not active_publication and not active_import:
                self.session.execute(
                    update(ProviderConnection)
                    .where(ProviderConnection.id == connection_id)
                    .values(
                        state="reauthorization_required",
                        encrypted_credentials="",
                        scopes=[],
                        expires_at=None,
                        updated_at=now(),
                    )
                )
        self.session.execute(delete(Invitation).where(Invitation.workspace_id == workspace_id))
        self.session.execute(delete(AuditEvent).where(AuditEvent.workspace_id == workspace_id))
        self.session.execute(delete(Membership).where(Membership.workspace_id == workspace_id))
        workspace.name, workspace.erased_at = "Erased workspace", now()
        workspace.version += 1
        return {
            "ok": True,
            "state": "erased",
            "workspace_id": workspace_id,
            "remote_content_erased": False,
            "retention_days": settings.privacy_tombstone_days,
        }

    def erase_account(self, principal: Principal, password: str) -> dict:
        user = self.session.scalar(
            select(User)
            .where(User.id == principal.user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        reauthenticate(self.session, principal, password)
        assert user is not None
        owned = self.session.scalars(
            select(Membership)
            .join(Workspace)
            .where(
                Membership.user_id == user.id,
                Membership.role == "owner",
                Workspace.erased_at.is_(None),
                Workspace.erasure_requested_at.is_(None),
            )
            .order_by(Membership.workspace_id)
            .with_for_update(of=Membership)
        ).all()
        for member in owned:
            self.session.scalar(
                select(Workspace).where(Workspace.id == member.workspace_id).with_for_update()
            )
            count = (
                self.session.scalar(
                    select(func.count())
                    .select_from(Membership)
                    .join(User)
                    .where(
                        Membership.workspace_id == member.workspace_id,
                        Membership.role == "owner",
                        User.active.is_(True),
                    )
                )
                or 0
            )
            if count <= 1:
                raise ServiceError(
                    status_code=409,
                    error="Hand off workspace ownership or erase the workspace before deleting this account",
                    where="client",
                )
        user.active, user.auth_version = False, user.auth_version + 1
        user.email, user.name, user.password_hash = (
            "erased-" + user.id + "@deleted.invalid",
            "Deleted account",
            hasher_hash_unusable(),
        )
        user_id = user.id
        self.session.commit()
        # Preserve collaborators' records and required actor references, remove own data.
        self.session.execute(delete(PlanEntry).where(PlanEntry.user_id == user_id))
        self.session.execute(delete(LinkedInProfile).where(LinkedInProfile.user_id == user_id))
        self.session.execute(delete(GoogleMeetPreview).where(GoogleMeetPreview.user_id == user_id))
        for model in (
            OAuthState,
            IntegrationOAuthState,
            PasswordRecovery,
            ApiToken,
            AuthSession,
            SlackIdentity,
            SlackLinkChallenge,
        ):
            self.session.execute(delete(model).where(model.user_id == user_id))
        self.session.execute(
            update(ProviderConnection)
            .where(ProviderConnection.user_id == user_id)
            .values(
                state="reauthorization_required",
                encrypted_credentials="",
                scopes=[],
                expires_at=None,
                updated_at=now(),
            )
        )
        self.session.execute(delete(ProviderDestination).where(ProviderDestination.user_id == user_id))
        from ..models import GitHubDestination

        self.session.execute(
            delete(GitHubDestination).where(
                GitHubDestination.configured_by == user_id,
                GitHubDestination.id.not_in(
                    select(PublicationProposal.destination_id).where(
                        PublicationProposal.destination_id.is_not(None)
                    )
                ),
            )
        )
        drafts = self.session.scalars(select(LinkedInDraft).where(LinkedInDraft.actor_id == user_id)).all()
        for draft in drafts:
            draft.text, draft.snapshots, draft.version = "[erased]", [], draft.version + 1
        proposals = self.session.scalars(
            select(LinkedInProposal).where(LinkedInProposal.actor_id == user_id)
        ).all()
        for proposal in proposals:
            (
                proposal.payload,
                proposal.snapshots,
                proposal.author,
                proposal.expires_at,
                proposal.approved_at,
            ) = {}, [], "", now(), None
        self.session.execute(
            update(Invitation)
            .where(Invitation.issued_by == user_id, Invitation.consumed_at.is_(None))
            .values(revoked_at=now())
        )
        self.session.execute(
            update(Participant)
            .where(Participant.linked_user_id == user_id)
            .values(
                name="Deleted participant",
                role="",
                aliases=[],
                github_login=None,
                linkedin_url=None,
                linked_user_id=None,
            )
        )
        cancel_actor_jobs(self.session, user_id, "account_erasure")
        self.session.execute(delete(Membership).where(Membership.user_id == user_id))
        return {
            "ok": True,
            "state": "deactivated_and_anonymized",
            "collaborative_content_retained": True,
            "remote_content_erased": False,
        }


def hasher_hash_unusable() -> str:
    from ..auth import hasher

    return hasher.hash(secrets.token_urlsafe(32))
