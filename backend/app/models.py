from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    select,
)
from sqlalchemy.engine import Connection
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def uid() -> str:
    return str(uuid4())


def now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("NOT is_visitor OR visitor_expires_at IS NOT NULL", name="ck_visitor_expiry"),
        CheckConstraint("auth_version >= 1", name="ck_user_auth_version"),
        Index("ix_user_visitor_expiry", "is_visitor", "visitor_expires_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_visitor: Mapped[bool] = mapped_column(Boolean, default=False)
    visitor_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    auth_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Workspace(Base):
    __tablename__ = "workspaces"
    __table_args__ = (
        CheckConstraint("department IN ('engineering','hr','finance')", name="ck_workspace_department"),
        CheckConstraint("NOT is_demo OR demo_expires_at IS NOT NULL", name="ck_demo_workspace_expiry"),
        CheckConstraint("version >= 1", name="ck_workspace_version"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(120))
    department: Mapped[str] = mapped_column(String(20), default="engineering")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    demo_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1)
    erasure_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    erased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DemoAdmission(Base):
    """One row serializes capacity checks across API instances."""

    __tablename__ = "demo_admission"
    __table_args__ = (CheckConstraint("id = 1", name="ck_demo_admission_singleton"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)


class VisitorUsage(Base):
    __tablename__ = "visitor_usage"
    __table_args__ = (CheckConstraint("mutations >= 0 AND jobs >= 0", name="ck_visitor_usage_nonnegative"),)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    mutations: Mapped[int] = mapped_column(Integer, default=0)
    jobs: Mapped[int] = mapped_column(Integer, default=0)


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        CheckConstraint("role IN ('owner','reviewer','editor','viewer')", name="ck_membership_role"),
    )
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(20))


class Invitation(Base):
    __tablename__ = "invitations"
    __table_args__ = (
        CheckConstraint("role IN ('owner','reviewer','editor','viewer')", name="ck_invitation_role"),
        Index("ix_invitation_workspace", "workspace_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"))
    issued_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    issuer_auth_version: Mapped[int] = mapped_column(Integer)
    email: Mapped[str] = mapped_column(String(254))
    role: Mapped[str] = mapped_column(String(20))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PasswordRecovery(Base):
    __tablename__ = "password_recoveries"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    auth_version: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DeliveryTombstone(Base):
    """Minimum delivery facts retained after local content erasure, never a resend payload."""

    __tablename__ = "delivery_tombstones"
    __table_args__ = (
        UniqueConstraint("provider", "operation_id", name="uq_tombstone_operation"),
        CheckConstraint("provider IN ('github','jira','slack','linkedin')", name="ck_tombstone_provider"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    provider: Mapped[str] = mapped_column(String(20))
    operation_id: Mapped[str] = mapped_column(String(36))
    delivery_key: Mapped[str] = mapped_column(String(64))
    payload_hash: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(20))
    receipt: Mapped[dict] = mapped_column(JSON)
    retained_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    auth_version: Mapped[int] = mapped_column(Integer)


class ApiToken(Base):
    __tablename__ = "api_tokens"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    auth_version: Mapped[int] = mapped_column(Integer)


class Participant(Base):
    __tablename__ = "participants"
    __table_args__ = (UniqueConstraint("id", "workspace_id", name="uq_participant_scope"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(160), default="")
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    github_login: Mapped[str | None] = mapped_column(String(39))
    linkedin_url: Mapped[str | None] = mapped_column(String(250))
    linked_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    confirmed_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Meeting(Base):
    __tablename__ = "meetings"
    __table_args__ = (
        UniqueConstraint("workspace_id", "slug", name="uq_meeting_slug"),
        UniqueConstraint("id", "workspace_id", name="uq_meeting_scope"),
        CheckConstraint("visibility IN ('workspace','restricted')", name="ck_meeting_visibility"),
        CheckConstraint("version >= 1 AND current_revision >= 1", name="ck_meeting_version"),
        Index("ix_meeting_recent", "workspace_id", "updated_at", "id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"))
    slug: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(200))
    visibility: Mapped[str] = mapped_column(String(20), default="workspace")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    current_revision: Mapped[int] = mapped_column(Integer, default=1)
    version: Mapped[int] = mapped_column(Integer, default=1)
    occurred_on: Mapped[str | None] = mapped_column(String(10))
    timezone: Mapped[str] = mapped_column(String(60), default="UTC")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class TranscriptRevision(Base):
    __tablename__ = "transcript_revisions"
    __table_args__ = (
        UniqueConstraint("meeting_id", "number", name="uq_transcript_number"),
        UniqueConstraint("id", "meeting_id", name="uq_transcript_meeting"),
        CheckConstraint("number >= 1", name="ck_transcript_number"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"))
    number: Mapped[int] = mapped_column(Integer)
    raw_text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    chunking_version: Mapped[str] = mapped_column(String(50))
    index_status: Mapped[str] = mapped_column(String(20), default="queued")
    embed_provider: Mapped[str | None] = mapped_column(String(40))
    embed_model: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class TranscriptChunk(Base):
    __tablename__ = "transcript_chunks"
    __table_args__ = (
        UniqueConstraint("revision_id", "chunk_index", name="uq_chunk_position"),
        UniqueConstraint("id", "revision_id", name="uq_chunk_revision"),
        CheckConstraint("chunk_index >= 0 AND start_line >= 1", name="ck_chunk_position"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    revision_id: Mapped[str] = mapped_column(ForeignKey("transcript_revisions.id", ondelete="CASCADE"))
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    speaker: Mapped[str | None] = mapped_column(String(120))
    timestamp: Mapped[str | None] = mapped_column(String(20))
    start_line: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list | None] = mapped_column(JSON)


class ParticipantMention(Base):
    __tablename__ = "participant_mentions"
    __table_args__ = (
        UniqueConstraint("revision_id", "name", name="uq_mention_name"),
        ForeignKeyConstraint(["meeting_id", "workspace_id"], ["meetings.id", "meetings.workspace_id"]),
        ForeignKeyConstraint(
            ["revision_id", "meeting_id"], ["transcript_revisions.id", "transcript_revisions.meeting_id"]
        ),
        ForeignKeyConstraint(
            ["participant_id", "workspace_id"], ["participants.id", "participants.workspace_id"]
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String(36))
    meeting_id: Mapped[str] = mapped_column(String(36))
    revision_id: Mapped[str] = mapped_column(String(36))
    name: Mapped[str] = mapped_column(String(120))
    participant_id: Mapped[str | None] = mapped_column(String(36))
    confirmed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


class ExtractionRun(Base):
    __tablename__ = "extraction_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    revision_id: Mapped[str] = mapped_column(ForeignKey("transcript_revisions.id"), index=True)
    mode: Mapped[str] = mapped_column(String(30))
    coverage: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class WorkItem(Base):
    __tablename__ = "work_items"
    __table_args__ = (
        ForeignKeyConstraint(["meeting_id", "workspace_id"], ["meetings.id", "meetings.workspace_id"]),
        ForeignKeyConstraint(
            ["revision_id", "meeting_id"], ["transcript_revisions.id", "transcript_revisions.meeting_id"]
        ),
        ForeignKeyConstraint(["owner_id", "workspace_id"], ["participants.id", "participants.workspace_id"]),
        UniqueConstraint("meeting_id", "revision_id", "fingerprint", name="uq_item_extraction"),
        UniqueConstraint("id", "revision_id", name="uq_item_revision"),
        CheckConstraint("kind IN ('action','decision','blocker','follow_up','risk')", name="ck_item_kind"),
        CheckConstraint("status IN ('draft','approved','done','dismissed')", name="ck_item_status"),
        CheckConstraint("confidence >= 0 AND confidence <= 1 AND version >= 1", name="ck_item_values"),
        Index("ix_item_queue", "workspace_id", "status", "kind", "owner_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String(36))
    meeting_id: Mapped[str] = mapped_column(String(36))
    revision_id: Mapped[str] = mapped_column(String(36))
    extraction_run_id: Mapped[str | None] = mapped_column(ForeignKey("extraction_runs.id"))
    fingerprint: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    labels: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    owner_id: Mapped[str | None] = mapped_column(String(36))
    assignee_hint: Mapped[str | None] = mapped_column(String(120))
    due_hint: Mapped[str | None] = mapped_column(String(120))
    due_date: Mapped[str | None] = mapped_column(String(10))
    confidence: Mapped[float] = mapped_column(Float, default=0.6)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PlanEntry(Base):
    __tablename__ = "plan_entries"
    __table_args__ = (
        UniqueConstraint("user_id", "item_id", name="uq_plan_user_item"),
        CheckConstraint("state IN ('planned','in_progress','blocked','done')", name="ck_plan_state"),
        CheckConstraint(
            "priority BETWEEN 1 AND 3 AND version >= 1 AND reviewed_version >= 1", name="ck_plan_values"
        ),
        Index("ix_plan_day", "user_id", "planned_on"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    item_id: Mapped[str] = mapped_column(ForeignKey("work_items.id", ondelete="CASCADE"))
    planned_on: Mapped[str] = mapped_column(String(10))
    state: Mapped[str] = mapped_column(String(20), default="planned")
    priority: Mapped[int] = mapped_column(Integer, default=2)
    reviewed_version: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class WorkItemEvidence(Base):
    __tablename__ = "work_item_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["item_id", "revision_id"], ["work_items.id", "work_items.revision_id"], ondelete="CASCADE"
        ),
        ForeignKeyConstraint(
            ["chunk_id", "revision_id"], ["transcript_chunks.id", "transcript_chunks.revision_id"]
        ),
    )
    item_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    chunk_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    revision_id: Mapped[str] = mapped_column(String(36))


class WorkItemRevision(Base):
    __tablename__ = "work_item_revisions"
    __table_args__ = (UniqueConstraint("item_id", "version", name="uq_review_revision"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    item_id: Mapped[str] = mapped_column(ForeignKey("work_items.id"))
    version: Mapped[int] = mapped_column(Integer)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PublicationProposal(Base):
    __tablename__ = "publication_proposals"
    __table_args__ = (
        ForeignKeyConstraint(["meeting_id", "workspace_id"], ["meetings.id", "meetings.workspace_id"]),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id"))
    repo: Mapped[str] = mapped_column(String(180))
    destination_id: Mapped[str | None] = mapped_column(ForeignKey("github_destinations.id"))
    destination_version: Mapped[int | None] = mapped_column(Integer)
    payload_hash: Mapped[str] = mapped_column(String(64))
    payloads: Mapped[list] = mapped_column(JSON)
    snapshots: Mapped[list] = mapped_column(JSON)
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PublicationOperation(Base):
    __tablename__ = "publication_operations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    proposal_id: Mapped[str] = mapped_column(ForeignKey("publication_proposals.id"), unique=True)
    publication_key: Mapped[str] = mapped_column(String(64), unique=True)
    state: Mapped[str] = mapped_column(String(20), default="queued")
    results: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class JiraProposal(Base):
    __tablename__ = "jira_proposals"
    __table_args__ = (
        ForeignKeyConstraint(["meeting_id", "workspace_id"], ["meetings.id", "meetings.workspace_id"]),
        CheckConstraint("action IN ('create','update')", name="ck_jira_action"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id"))
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(10))
    destination: Mapped[dict] = mapped_column(JSON)
    snapshot: Mapped[dict] = mapped_column(JSON)
    payload: Mapped[dict] = mapped_column(JSON)
    payload_hash: Mapped[str] = mapped_column(String(64))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class JiraOperation(Base):
    __tablename__ = "jira_operations"
    __table_args__ = (
        CheckConstraint(
            "state IN ('queued','sending','completed','failed','uncertain')", name="ck_jira_operation_state"
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    proposal_id: Mapped[str] = mapped_column(ForeignKey("jira_proposals.id"), unique=True)
    delivery_key: Mapped[str] = mapped_column(String(64), unique=True)
    state: Mapped[str] = mapped_column(String(20), default="queued")
    result: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        ForeignKeyConstraint(["meeting_id", "workspace_id"], ["meetings.id", "meetings.workspace_id"]),
        CheckConstraint(
            "kind IN ('index','extract','publish','jira_publish','slack_publish','linkedin_publish')",
            name="ck_job_kind",
        ),
        CheckConstraint(
            "state IN ('queued','running','completed','failed','cancelled')", name="ck_job_state"
        ),
        Index("ix_job_claim", "state", "available_at", "created_at"),
        Index("ix_job_workspace", "workspace_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"))
    meeting_id: Mapped[str | None] = mapped_column(ForeignKey("meetings.id"))
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    actor_auth_version: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20))
    state: Mapped[str] = mapped_column(String(20), default="queued")
    payload: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(60))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_token: Mapped[str | None] = mapped_column(String(36))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_workspace", "workspace_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"))
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80))
    target_id: Mapped[str] = mapped_column(String(36))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class LinkedInProfile(Base):
    __tablename__ = "linkedin_profiles"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    subject: Mapped[str] = mapped_column(String(200), unique=True)
    profile: Mapped[dict] = mapped_column(JSON)
    scopes: Mapped[list] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class OAuthState(Base):
    __tablename__ = "oauth_states"
    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    session_hash: Mapped[str] = mapped_column(ForeignKey("auth_sessions.token_hash", ondelete="CASCADE"))
    nonce: Mapped[str] = mapped_column(String(100))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RateBucket(Base):
    __tablename__ = "rate_buckets"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ProviderConnection(Base):
    __tablename__ = "provider_connections"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_provider_account"),
        UniqueConstraint("id", "user_id", name="uq_provider_owner"),
        CheckConstraint(
            "provider IN ('jira','slack','github','linkedin','google_meet')", name="ck_provider_name"
        ),
        CheckConstraint("state IN ('connected','reauthorization_required')", name="ck_provider_state"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(20))
    state: Mapped[str] = mapped_column(String(30), default="connected")
    encrypted_credentials: Mapped[str] = mapped_column(Text)
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ProviderDestination(Base):
    __tablename__ = "provider_destinations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["connection_id", "user_id"],
            ["provider_connections.id", "provider_connections.user_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["memberships.workspace_id", "memberships.user_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("workspace_id", "connection_id", name="uq_provider_workspace"),
        CheckConstraint("version >= 1", name="ck_destination_version"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    connection_id: Mapped[str] = mapped_column(String(36))
    user_id: Mapped[str] = mapped_column(String(36))
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    resource_id: Mapped[str | None] = mapped_column(String(36))
    resource_name: Mapped[str | None] = mapped_column(String(200))
    resource_url: Mapped[str | None] = mapped_column(String(250))
    project_key: Mapped[str | None] = mapped_column(String(40))
    project_name: Mapped[str | None] = mapped_column(String(200))
    version: Mapped[int] = mapped_column(Integer, default=1)


class IntegrationOAuthState(Base):
    __tablename__ = "integration_oauth_states"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["memberships.workspace_id", "memberships.user_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "provider IN ('jira','slack','github','linkedin','google_meet')", name="ck_oauth_provider"
        ),
    )
    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36))
    workspace_id: Mapped[str] = mapped_column(String(36))
    provider: Mapped[str] = mapped_column(String(20))
    nonce: Mapped[str | None] = mapped_column(String(100))
    session_hash: Mapped[str] = mapped_column(ForeignKey("auth_sessions.token_hash", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class GitHubDestination(Base):
    __tablename__ = "github_destinations"
    __table_args__ = (CheckConstraint("version >= 1", name="ck_github_destination_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), unique=True)
    repo: Mapped[str] = mapped_column(String(180))
    version: Mapped[int] = mapped_column(Integer, default=1)
    configured_by: Mapped[str] = mapped_column(ForeignKey("users.id"))


class SlackAccount(Base):
    __tablename__ = "slack_accounts"
    __table_args__ = (
        UniqueConstraint("app_id", "team_id", name="uq_slack_installation"),
        CheckConstraint("version >= 1", name="ck_slack_account_version"),
    )
    connection_id: Mapped[str] = mapped_column(
        ForeignKey("provider_connections.id", ondelete="CASCADE"), primary_key=True
    )
    app_id: Mapped[str] = mapped_column(String(64))
    team_id: Mapped[str] = mapped_column(String(64))
    team_name: Mapped[str] = mapped_column(String(200))
    bot_user_id: Mapped[str] = mapped_column(String(64))
    bot_id: Mapped[str] = mapped_column(String(64))
    installed_user_id: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=1)


class SlackDestination(Base):
    __tablename__ = "slack_destinations"
    destination_id: Mapped[str] = mapped_column(
        ForeignKey("provider_destinations.id", ondelete="CASCADE"), primary_key=True
    )
    channel_id: Mapped[str] = mapped_column(String(64))
    channel_name: Mapped[str] = mapped_column(String(200))
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SlackProposal(Base):
    __tablename__ = "slack_proposals"
    __table_args__ = (
        ForeignKeyConstraint(["meeting_id", "workspace_id"], ["meetings.id", "meetings.workspace_id"]),
        CheckConstraint("action IN ('create','update')", name="ck_slack_action"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id"))
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(10))
    destination: Mapped[dict] = mapped_column(JSON)
    snapshots: Mapped[list] = mapped_column(JSON)
    target: Mapped[dict | None] = mapped_column(JSON)
    payload: Mapped[dict] = mapped_column(JSON)
    payload_hash: Mapped[str] = mapped_column(String(64))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SlackOperation(Base):
    __tablename__ = "slack_operations"
    __table_args__ = (
        CheckConstraint(
            "state IN ('queued','sending','completed','failed','uncertain')", name="ck_slack_operation_state"
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    proposal_id: Mapped[str] = mapped_column(ForeignKey("slack_proposals.id"), unique=True)
    delivery_key: Mapped[str] = mapped_column(String(64), unique=True)
    state: Mapped[str] = mapped_column(String(20), default="queued")
    result: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class LinkedInDraft(Base):
    __tablename__ = "linkedin_drafts"
    __table_args__ = (
        ForeignKeyConstraint(["meeting_id", "workspace_id"], ["meetings.id", "meetings.workspace_id"]),
        CheckConstraint("kind IN ('post','outreach')", name="ck_linkedin_draft_kind"),
        CheckConstraint("version >= 1", name="ck_linkedin_draft_version"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id"))
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    snapshots: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class LinkedInProposal(Base):
    __tablename__ = "linkedin_proposals"
    __table_args__ = (
        ForeignKeyConstraint(["meeting_id", "workspace_id"], ["meetings.id", "meetings.workspace_id"]),
        CheckConstraint("draft_version >= 1", name="ck_linkedin_proposal_draft_version"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id"))
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    draft_id: Mapped[str] = mapped_column(ForeignKey("linkedin_drafts.id"))
    draft_version: Mapped[int] = mapped_column(Integer)
    connection_id: Mapped[str] = mapped_column(ForeignKey("provider_connections.id"))
    connection_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    author: Mapped[str] = mapped_column(String(250))
    payload: Mapped[dict] = mapped_column(JSON)
    payload_hash: Mapped[str] = mapped_column(String(64))
    snapshots: Mapped[list] = mapped_column(JSON)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class LinkedInOperation(Base):
    __tablename__ = "linkedin_operations"
    __table_args__ = (
        CheckConstraint(
            "state IN ('queued','sending','completed','failed','uncertain')",
            name="ck_linkedin_operation_state",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    proposal_id: Mapped[str] = mapped_column(ForeignKey("linkedin_proposals.id"), unique=True)
    delivery_key: Mapped[str] = mapped_column(String(64), unique=True)
    state: Mapped[str] = mapped_column(String(20), default="queued")
    result: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SlackIdentity(Base):
    __tablename__ = "slack_identities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["memberships.workspace_id", "memberships.user_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("workspace_id", "connection_id", "slack_user_id", name="uq_slack_member_mapping"),
        UniqueConstraint("workspace_id", "connection_id", "user_id", name="uq_slack_user_mapping"),
        CheckConstraint("version >= 1 AND account_version >= 1", name="ck_slack_identity_version"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String(36))
    user_id: Mapped[str] = mapped_column(String(36))
    connection_id: Mapped[str] = mapped_column(ForeignKey("slack_accounts.connection_id", ondelete="CASCADE"))
    slack_user_id: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=1)
    account_version: Mapped[int] = mapped_column(Integer)
    auth_version: Mapped[int] = mapped_column(Integer)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SlackLinkChallenge(Base):
    __tablename__ = "slack_link_challenges"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["memberships.workspace_id", "memberships.user_id"],
            ondelete="CASCADE",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String(36))
    user_id: Mapped[str] = mapped_column(String(36))
    connection_id: Mapped[str] = mapped_column(ForeignKey("slack_accounts.connection_id", ondelete="CASCADE"))
    account_version: Mapped[int] = mapped_column(Integer)
    session_hash: Mapped[str] = mapped_column(ForeignKey("auth_sessions.token_hash", ondelete="CASCADE"))
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    pending_slack_user_id: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SlackInteractionContext(Base):
    __tablename__ = "slack_interaction_contexts"
    __table_args__ = (CheckConstraint("kind IN ('capture','plan')", name="ck_slack_context_kind"),)
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    identity_id: Mapped[str] = mapped_column(ForeignKey("slack_identities.id", ondelete="CASCADE"))
    identity_version: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledgement: Mapped[dict | None] = mapped_column(JSON)


class GoogleMeetAccount(Base):
    __tablename__ = "google_meet_accounts"
    connection_id: Mapped[str] = mapped_column(
        ForeignKey("provider_connections.id", ondelete="CASCADE"), primary_key=True
    )
    generation: Mapped[str] = mapped_column(String(36), default=uid)


class GoogleMeetPreview(Base):
    __tablename__ = "google_meet_previews"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["memberships.workspace_id", "memberships.user_id"],
            ondelete="CASCADE",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    user_id: Mapped[str] = mapped_column(String(36))
    auth_version: Mapped[int] = mapped_column(Integer)
    connection_id: Mapped[str] = mapped_column(ForeignKey("provider_connections.id", ondelete="CASCADE"))
    generation: Mapped[str] = mapped_column(String(36))
    payload_hash: Mapped[str] = mapped_column(String(64))
    transcript: Mapped[str] = mapped_column(Text)
    source: Mapped[dict] = mapped_column(JSON)
    participants: Mapped[list] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class MeetingImport(Base):
    __tablename__ = "meeting_imports"
    __table_args__ = (
        ForeignKeyConstraint(["meeting_id", "workspace_id"], ["meetings.id", "meetings.workspace_id"]),
        UniqueConstraint("workspace_id", "conference_record", name="uq_meet_import_source"),
        UniqueConstraint("meeting_id", name="uq_meet_import_meeting"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String(36), index=True)
    meeting_id: Mapped[str] = mapped_column(String(36))
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    connection_id: Mapped[str] = mapped_column(ForeignKey("provider_connections.id"))
    generation: Mapped[str] = mapped_column(String(36))
    conference_record: Mapped[str] = mapped_column(String(200))
    content_hash: Mapped[str] = mapped_column(String(64))
    revision_id: Mapped[str] = mapped_column(ForeignKey("transcript_revisions.id"))
    source: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SlackInboundReceipt(Base):
    __tablename__ = "slack_inbound_receipts"
    request_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    acknowledgement: Mapped[dict] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


def stamp_authority(mapper, connection: Connection, target) -> None:
    """Freeze account authority at credential, mapping and job creation."""
    field = "actor_auth_version" if isinstance(target, Job) else "auth_version"
    user_id = target.actor_id if isinstance(target, Job) else target.user_id
    if getattr(target, field) is None:
        version = connection.scalar(select(User.auth_version).where(User.id == user_id))
        if version is None:
            raise ValueError("An existing account is required to stamp authority")
        setattr(target, field, version)


for authority_model in (AuthSession, ApiToken, Job, SlackIdentity):
    event.listen(authority_model, "before_insert", stamp_authority)
