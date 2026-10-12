"""Read-only operator aggregates. Never serialize product payloads or identifiers."""

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import QueuePool

from ..auth import aware
from ..models import (
    JOB_MAX_ATTEMPTS,
    DeliveryTombstone,
    JiraOperation,
    Job,
    LinkedInOperation,
    PublicationOperation,
    SlackOperation,
    User,
    Workspace,
    now,
)
from ..settings import settings
from .retention import TEMPORARY_RECORDS

JOB_KINDS = (
    "index",
    "extract",
    "publish",
    "jira_publish",
    "slack_publish",
    "linkedin_publish",
    "transcribe",
)
JOB_STATES = ("queued", "running", "completed", "failed", "cancelled")
EFFECT_STATES = ("queued", "sending", "completed", "failed", "uncertain")
PROVIDERS = ("github", "jira", "slack", "linkedin")
SIZE_TABLES = (
    "transcript_revisions",
    "transcript_chunks",
    "work_items",
    "work_item_revisions",
    "jobs",
    "audit_events",
    "google_meet_previews",
    "audio_uploads",
    "delivery_tombstones",
)


def operational_snapshot(session: Session) -> dict:
    """A database observation, not worker health, authority or a capacity promise.

    Connection states come from pg_stat_activity, which hides other roles' session
    state from unprivileged users: there, active and idle_in_transaction are lower
    bounds, while total stays exact.
    """
    cutoff = now()
    jobs = {kind: {state: 0 for state in JOB_STATES} for kind in JOB_KINDS}
    queued_age: dict[str, int | None] = dict.fromkeys(JOB_KINDS, None)
    unknown_jobs = 0
    with session.no_autoflush:
        rows = session.execute(
            select(Job.kind, Job.state, func.count(), func.min(Job.created_at)).group_by(Job.kind, Job.state)
        )
        for kind, state, count, oldest in rows:
            if kind not in JOB_KINDS or state not in JOB_STATES:
                unknown_jobs += count
                continue
            jobs[kind][state] = count
            if state == "queued" and oldest is not None:
                queued_age[kind] = max(0, int((cutoff - aware(oldest)).total_seconds()))
        effects = {provider: dict.fromkeys(EFFECT_STATES, 0) for provider in PROVIDERS}
        unknown_effects = 0
        for provider, model in (
            ("github", PublicationOperation),
            ("jira", JiraOperation),
            ("slack", SlackOperation),
            ("linkedin", LinkedInOperation),
        ):
            for state, count in session.execute(select(model.state, func.count()).group_by(model.state)):
                if state in EFFECT_STATES:
                    effects[provider][state] = count
                else:
                    unknown_effects += count

        def count_rows(model, *conditions):
            return session.scalar(select(func.count()).select_from(model).where(*conditions)) or 0

        retained = count_rows(User, User.is_visitor.is_(True))
        active = count_rows(
            User, User.is_visitor.is_(True), User.active.is_(True), User.visitor_expires_at > cutoff
        )
        report: dict = {
            "schema_version": 1,
            "observed_at": cutoff.isoformat(),
            "jobs": jobs,
            "oldest_queued_seconds": queued_age,
            "unknown_job_rows": unknown_jobs,
            "expired_running_leases": count_rows(Job, Job.state == "running", Job.lease_until <= cutoff),
            "running_without_lease": count_rows(Job, Job.state == "running", Job.lease_until.is_(None)),
            "attempt_limit_rows": count_rows(
                Job, Job.state.in_(("queued", "running")), Job.attempts >= JOB_MAX_ATTEMPTS
            ),
            "delivery_effects": effects,
            "unknown_effect_rows": unknown_effects,
            "unresolved_tombstones": count_rows(
                DeliveryTombstone, DeliveryTombstone.state.in_(("sending", "uncertain"))
            ),
            "visitors": {
                "active": active,
                "retained": retained,
                "expired": count_rows(User, User.is_visitor.is_(True), User.visitor_expires_at <= cutoff),
                "active_limit": settings.visitor_active_limit,
                "retained_limit": settings.visitor_retained_limit,
            },
            "pending_erasure_workspaces": count_rows(
                Workspace, Workspace.erasure_requested_at.is_not(None), Workspace.erased_at.is_(None)
            ),
            "expired_temporary_records": {
                model.__tablename__: count_rows(model, model.expires_at <= cutoff)
                for model, _ in TEMPORARY_RECORDS
            },
            "storage": {"database_bytes": None, "relation_bytes": {}},
            "connections": {
                "server_max_connections": None,
                "total": None,
                "active": None,
                "idle_in_transaction": None,
            },
        }
        connection = session.connection()
        pool = connection.engine.pool
        report["pool"] = {
            "scope": "diagnostic_process_only",
            "size": pool.size() if isinstance(pool, QueuePool) else None,
            "checked_out": pool.checkedout() if isinstance(pool, QueuePool) else None,
        }
        if connection.dialect.name == "postgresql":
            report["storage"]["database_bytes"] = session.scalar(
                text("SELECT pg_database_size(current_database())")
            )
            report["storage"]["relation_bytes"] = {
                table: session.scalar(
                    text("SELECT pg_total_relation_size(to_regclass(:table_name))"), {"table_name": table}
                )
                for table in SIZE_TABLES
            }
            report["connections"] = dict(
                session.execute(
                    text(
                        "SELECT count(*) AS total, count(*) FILTER (WHERE state = 'active') AS active, "
                        "count(*) FILTER (WHERE state IN ('idle in transaction','idle in transaction (aborted)')) "
                        "AS idle_in_transaction FROM pg_stat_activity WHERE datname = current_database()"
                    )
                )
                .mappings()
                .one()
            )
            report["connections"]["server_max_connections"] = int(
                session.scalar(text("SHOW max_connections"))
            )
        return report
