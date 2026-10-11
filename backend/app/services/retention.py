"""Bounded operator maintenance; preview first, unresolved effects retained."""

from datetime import timedelta
from typing import cast

from sqlalchemy import delete, or_, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from ..auth import aware
from ..models import (
    ApiToken,
    AuthSession,
    DeliveryTombstone,
    GoogleMeetPreview,
    IntegrationOAuthState,
    Invitation,
    LinkedInProfile,
    Membership,
    OAuthState,
    PasswordRecovery,
    ProviderConnection,
    RateBucket,
    SlackIdentity,
    SlackInboundReceipt,
    SlackInteractionContext,
    SlackLinkChallenge,
    User,
    Workspace,
    now,
)
from ..settings import settings
from .errors import ServiceError
from .privacy import PrivacyService

TEMPORARY_RECORDS = (
    (GoogleMeetPreview, GoogleMeetPreview.id),
    (RateBucket, RateBucket.key),
    (SlackInboundReceipt, SlackInboundReceipt.request_hash),
    (SlackInteractionContext, SlackInteractionContext.token_hash),
    (SlackLinkChallenge, SlackLinkChallenge.id),
    (PasswordRecovery, PasswordRecovery.token_hash),
    (OAuthState, OAuthState.state_hash),
    (IntegrationOAuthState, IntegrationOAuthState.state_hash),
    (Invitation, Invitation.id),
    (ApiToken, ApiToken.token_hash),
    # Session removal may also cascade expired or unexpired session-bound states.
    (AuthSession, AuthSession.token_hash),
)


class RetentionService:
    def __init__(self, session: Session):
        self.session = session

    def run(self, *, limit: int = 20, apply: bool = False) -> dict:
        if not 1 <= limit <= 100:
            raise ValueError("Maintenance batch must contain between 1 and 100 records")
        cutoff = now()
        visitors = self.session.scalars(
            select(User)
            .where(User.is_visitor.is_(True), User.visitor_expires_at <= cutoff)
            .order_by(User.visitor_expires_at, User.id)
            .limit(limit)
        ).all()
        tombstones = self.session.scalars(
            select(DeliveryTombstone)
            .where(
                DeliveryTombstone.retained_until <= cutoff,
                DeliveryTombstone.state.not_in({"uncertain", "sending"}),
            )
            .order_by(DeliveryTombstone.retained_until, DeliveryTombstone.id)
            .limit(limit)
        ).all()
        temporary = {
            model.__tablename__: list(
                self.session.scalars(
                    select(key).where(model.expires_at <= cutoff).order_by(model.expires_at, key).limit(limit)
                )
            )
            for model, key in TEMPORARY_RECORDS
        }
        report = {
            "applied": apply,
            "batch_limit": limit,
            "limit_scope": "per_record_class",
            "expired_visitors": len(visitors),
            "eligible_tombstones": len(tombstones),
            "removed_visitors": 0,
            "pending_visitors": 0,
            "protected_visitors": 0,
            "removed_tombstones": 0,
            "temporary_records": {
                name: {"eligible": len(identifiers), "removed": 0} for name, identifiers in temporary.items()
            },
            "dependent_removals": "Visitor purges and session deletion may also remove dependent records",
        }
        if not apply:
            return report
        visitor_ids, tombstone_ids = [user.id for user in visitors], [row.id for row in tombstones]
        self.session.commit()
        for user_id in visitor_ids:
            user = self.session.scalar(
                select(User)
                .where(User.id == user_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if (
                not user
                or not user.is_visitor
                or not user.visitor_expires_at
                or aware(user.visitor_expires_at) > now()
            ):
                continue
            workspaces = self.session.scalars(
                select(Workspace).join(Membership).where(Membership.user_id == user_id)
            ).all()
            protected = any(
                not workspace.is_demo
                or len(
                    self.session.scalars(
                        select(Membership).where(Membership.workspace_id == workspace.id)
                    ).all()
                )
                != 1
                for workspace in workspaces
            )
            if protected:
                report["protected_visitors"] += 1
                self.session.rollback()
                continue
            user.active, user.auth_version = False, user.auth_version + 1
            workspace_ids = [workspace.id for workspace in workspaces]
            for workspace in workspaces:
                if workspace.erasure_requested_at is None:
                    workspace.erasure_requested_at, workspace.version = now(), workspace.version + 1
            self.session.commit()
            pending = False
            for workspace_id in workspace_ids:
                result = PrivacyService(self.session).purge_workspace(workspace_id)
                pending = pending or result["state"] == "pending_erasure"
                self.session.commit()
            if pending:
                report["pending_visitors"] += 1
                continue
            for model in (
                OAuthState,
                IntegrationOAuthState,
                ApiToken,
                AuthSession,
                SlackIdentity,
                SlackLinkChallenge,
                PasswordRecovery,
                LinkedInProfile,
            ):
                self.session.execute(delete(model).where(model.user_id == user_id))
            self.session.execute(
                delete(Invitation).where(
                    or_(Invitation.issued_by == user_id, Invitation.consumed_by == user_id)
                )
            )
            self.session.execute(delete(ProviderConnection).where(ProviderConnection.user_id == user_id))
            self.session.execute(delete(User).where(User.id == user_id, User.is_visitor.is_(True)))
            self.session.commit()
            report["removed_visitors"] += 1
        if tombstone_ids:
            result = self.session.execute(
                delete(DeliveryTombstone).where(
                    DeliveryTombstone.id.in_(tombstone_ids),
                    DeliveryTombstone.retained_until <= cutoff,
                    DeliveryTombstone.state.not_in({"uncertain", "sending"}),
                )
            )
            report["removed_tombstones"] = cast(CursorResult, result).rowcount
        # Recheck expiry in DELETE: a quota may have been renewed since selection.
        # Cascade/purge removals are intentionally distinct from direct removals.
        for model, key in TEMPORARY_RECORDS:
            identifiers = temporary[model.__tablename__]
            if identifiers:
                result = self.session.execute(
                    delete(model).where(key.in_(identifiers), model.expires_at <= cutoff)
                )
                report["temporary_records"][model.__tablename__]["removed"] = cast(
                    CursorResult, result
                ).rowcount
        self.session.commit()
        return report

    def resolve_tombstone(self, identifier: str, resolution: str, *, apply: bool = False) -> dict:
        if resolution not in {"confirmed", "not_sent", "accepted_unknown"}:
            raise ValueError("Choose a confirmed effect, confirmed absence or explicit accepted uncertainty")
        row = self.session.scalar(
            select(DeliveryTombstone).where(DeliveryTombstone.id == identifier).with_for_update()
        )
        if not row:
            raise ServiceError(status_code=404, error="Retention record not found", where="client")
        if apply:
            row.receipt = {
                **row.receipt,
                "resolution": {"status": resolution, "decided_at": now().isoformat()},
            }
            row.state, row.retained_until = (
                "resolved",
                now() + timedelta(days=settings.privacy_tombstone_days),
            )
        return {
            "id": row.id,
            "provider": row.provider,
            "state": row.state,
            "applied": apply,
            "resolution": resolution,
            "retained_until": aware(row.retained_until).isoformat(),
        }
