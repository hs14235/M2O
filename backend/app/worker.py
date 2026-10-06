"""Durable PostgreSQL queue. Inference runs outside transactions; commits verify leases."""

import argparse
import asyncio
import logging
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import or_, select

from .access_policy import require_private_scope, user_is_active, workspace_access
from .auth import Principal
from .database import must_get, session_scope
from .embeddings import get_embedding_function
from .github import AmbiguousWrite, GitHubAdapter
from .jira_delivery import JiraDeliveryAdapter, UncertainJiraWrite
from .models import (
    JiraOperation,
    JiraProposal,
    Job,
    LinkedInOperation,
    Meeting,
    Membership,
    PublicationOperation,
    PublicationProposal,
    SlackOperation,
    SlackProposal,
    TranscriptChunk,
    TranscriptRevision,
    User,
    now,
)
from .services.common import audit, meeting_access
from .services.errors import ServiceError
from .services.extraction import ExtractionService
from .services.issues import IssueService
from .services.linkedin_publishing import publish_linkedin
from .settings import settings
from .slack_delivery import SlackDeliveryAdapter, UncertainSlackWrite, content_hash

log = logging.getLogger("meeting.worker")


def settle_exhausted_delivery(
    session, job, *, reason="Worker attempt limit reached before a confirmed delivery"
):
    """Keep durable provider intent visible when a job cannot obtain another lease."""
    if job.kind == "publish":
        operation = session.get(PublicationOperation, job.payload.get("operation_id"))
        if not operation:
            return
        if operation.state == "completed":
            job.state, job.error_code = "completed", None
        else:
            operation.state = (
                "uncertain"
                if operation.state == "sending"
                or operation.state == "uncertain"
                or any(row.get("status") == "uncertain" for row in operation.results)
                else "failed"
            )
            if not operation.results:
                operation.results = [{"status": "not_sent", "error": reason}]
        job.result = {"operation_id": operation.id, "state": operation.state, "results": operation.results}
        return
    model = {
        "jira_publish": JiraOperation,
        "slack_publish": SlackOperation,
        "linkedin_publish": LinkedInOperation,
    }.get(job.kind)
    if model is None:
        return
    receipt = session.get(model, job.payload.get("operation_id"))
    if not receipt:
        return
    if receipt.state == "completed":
        job.state, job.error_code = "completed", None
    else:
        receipt.state = (
            "uncertain"
            if receipt.state == "sending" or receipt.result and receipt.result.get("status") == "uncertain"
            else "failed"
        )
        receipt.result = receipt.result or {
            "status": "not_sent",
            "error": reason,
        }
    job.result = {"operation_id": receipt.id, "state": receipt.state, "result": receipt.result}


def claim():
    with session_scope() as session:
        job = session.scalar(
            select(Job)
            .where(
                or_(Job.state == "queued", (Job.state == "running") & (Job.lease_until < now())),
                Job.available_at <= now(),
            )
            .order_by(Job.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not job:
            return None
        if job.attempts >= 3:
            job.state, job.error_code = "failed", "attempt_limit"
            job.lease_until = None
            settle_exhausted_delivery(session, job)
            return None
        recovered = job.state == "running"
        job.state, job.lease_token = "running", str(uuid4())
        job.lease_until = now() + timedelta(seconds=90)
        job.attempts += 1
        session.flush()
        return {"id": job.id, "lease": job.lease_token, "kind": job.kind, "recovered": recovered}


def owned_job(session, claim_record):
    job = session.scalar(select(Job).where(Job.id == claim_record["id"]).with_for_update())
    if job is None or job.state != "running" or job.lease_token != claim_record["lease"]:
        raise ServiceError(status_code=409, error="Job lease is no longer owned")
    return job


def authorized(session, job):
    # Intent commits and provider reads can span an administrator's role change.
    # Re-read authority instead of trusting an ORM object cached before the await.
    member = session.scalar(
        select(Membership)
        .where(Membership.workspace_id == job.workspace_id, Membership.user_id == job.actor_id)
        .execution_options(populate_existing=True)
    )
    user = session.scalar(
        select(User).where(User.id == job.actor_id).execution_options(populate_existing=True)
    )
    allowed = (
        {"owner"}
        if job.kind in {"jira_publish", "slack_publish"}
        else {"owner", "reviewer"}
        if job.kind in {"publish", "linkedin_publish"}
        else {"owner", "reviewer", "editor"}
    )
    if (
        not user_is_active(user)
        or not member
        or member.role not in allowed
        or user is None
        or user.auth_version != job.actor_auth_version
    ):
        raise ServiceError(status_code=403, error="Job authorization was revoked")
    principal = Principal(job.actor_id, job.workspace_id, member.role, auth_version=job.actor_auth_version)
    workspace_access(session, principal)
    if job.kind in {"publish", "jira_publish", "slack_publish", "linkedin_publish"}:
        require_private_scope(session, principal)
    meeting = session.get(Meeting, job.meeting_id)
    if not meeting:
        raise ServiceError(status_code=404, error="Meeting no longer exists")
    meeting_access(session, principal, meeting.slug)
    return principal, meeting


async def heartbeat(record):
    while True:
        await asyncio.sleep(20)

        def renew():
            with session_scope() as session:
                job = owned_job(session, record)
                job.lease_until = now() + timedelta(seconds=90)

        await asyncio.to_thread(renew)


async def publish(record, adapter):
    with session_scope() as session:
        job = owned_job(session, record)
        _, _meeting = authorized(session, job)
        operation = must_get(session, PublicationOperation, job.payload["operation_id"])
        proposal = must_get(session, PublicationProposal, operation.proposal_id)
        count = len(proposal.payloads)
    for position in range(count):
        # Review edits take the same meeting lock. The lock spans this bounded HTTP
        # request so a reviewed snapshot cannot change between checking and sending.
        with session_scope() as session:
            job = owned_job(session, record)
            principal, _ = authorized(session, job)
            operation = must_get(session, PublicationOperation, job.payload["operation_id"])
            proposal = must_get(session, PublicationProposal, operation.proposal_id)
            IssueService(session, principal).validate_snapshot(proposal)
            if not proposal.approved_by or settings.public_demo_mode:
                raise ServiceError(status_code=403, error="Publication is disabled")
            allowed = {repo.strip().casefold() for repo in settings.github_allowed_repos.split(",")}
            if proposal.repo.casefold() not in allowed:
                raise ServiceError(status_code=403, error="Destination authorization was revoked")
            if position < len(operation.results) and operation.results[position].get("status") in {
                "created",
                "existing",
            }:
                continue
            marker = proposal.snapshots[position]["marker"]
            found = await adapter.find_marker(proposal.repo, marker, proposal.payloads[position])
            # A crash after POST may have written an issue. Absence in a subsequent
            # scan is not sufficient proof that a second POST would be safe.
            prior_result = operation.results[position] if position < len(operation.results) else None
            uncertain = record["recovered"] or prior_result and prior_result.get("status") == "uncertain"
            if found:
                result = found
            elif prior_result and prior_result.get("status") == "conflict":
                # A known resource with drift is not permission to create another.
                result = prior_result
            elif uncertain:
                result = {"status": "uncertain", "error": "Manual reconciliation required"}
            else:
                operation.state = "sending"
                # Persist intent before the network boundary, with a separate commit.
                operation.results = [
                    *operation.results,
                    {"status": "uncertain", "error": "Write intent recorded"},
                ]
                session.commit()
                job = owned_job(session, record)
                principal, _ = authorized(session, job)
                proposal = must_get(session, PublicationProposal, operation.proposal_id)
                IssueService(session, principal).validate_snapshot(proposal)
                try:
                    result = await adapter.create(proposal.repo, proposal.payloads[position])
                except AmbiguousWrite:
                    result = {
                        "status": "uncertain",
                        "error": "GitHub did not confirm the write; reconcile before proceeding",
                    }
                except ServiceError:
                    result = {"status": "rejected", "error": "GitHub rejected the exact reviewed payload"}
            results = list(operation.results)
            if position < len(results):
                results[position] = result
            else:
                results.append(result)
            operation.results = results
            operation.state = (
                "uncertain"
                if result["status"] == "uncertain"
                else "failed"
                if result["status"] in {"rejected", "conflict"}
                else "sending"
            )
            audit(
                session,
                principal,
                "publication.result",
                operation.id,
                {"position": position, "status": result["status"]},
            )
        if result["status"] in {"uncertain", "conflict", "rejected"}:
            return {"operation_id": operation.id, "state": operation.state, "results": results}
    with session_scope() as session:
        job = owned_job(session, record)
        operation = must_get(session, PublicationOperation, job.payload["operation_id"])
        operation.state = "completed"
        return {"operation_id": operation.id, "state": operation.state, "results": operation.results}


async def publish_jira(record, adapter):
    from .services.jira_delivery import JiraDeliveryService

    with session_scope() as session:
        job = owned_job(session, record)
        principal, _ = authorized(session, job)
        # Refresh can commit rotating credentials. Release the job lock before
        # taking the account lock, then reacquire and validate all sending state.
        session.commit()
        _, binding, _ = await adapter.access(session, principal)
        job = owned_job(session, record)
        principal, _ = authorized(session, job)
        operation = must_get(session, JiraOperation, job.payload["operation_id"])
        proposal = must_get(session, JiraProposal, operation.proposal_id)
        service = JiraDeliveryService(session, principal, adapter)
        if (
            proposal.actor_id != principal.user_id
            or proposal.workspace_id != principal.scope
            or not proposal.approved_at
        ):
            raise ServiceError(status_code=403, error="Jira delivery approval is unavailable")
        service.validate(proposal, binding)
        if operation.state == "completed":
            return {"operation_id": operation.id, "state": operation.state, "result": operation.result}
        if operation.state != "queued" or record["recovered"]:
            operation.state = "uncertain"
            operation.result = {
                "status": "uncertain",
                "error": "Recovered delivery requires reconciliation; no write repeated",
            }
            return {"operation_id": operation.id, "state": operation.state, "result": operation.result}
        # Commit intent first. A crash from this point onward must never resend.
        operation.state = "sending"
        operation.result = {"status": "uncertain", "error": "Write intent recorded"}
        session.commit()
        _, binding, token = await adapter.access(session, principal)
        job = owned_job(session, record)
        principal, _ = authorized(session, job)
        proposal = must_get(session, JiraProposal, operation.proposal_id)
        service.validate(proposal, binding)
        try:
            if proposal.action == "update":
                issue = await adapter.issue(token, proposal.destination, proposal.snapshot["issue_key"])
                if issue["fields"]["updated"] != proposal.snapshot["remote_updated"]:
                    raise ServiceError(
                        status_code=409, error="Jira issue changed after preview; no update sent"
                    )
            result = await adapter.write(
                token, proposal.destination, proposal.action, proposal.payload, proposal.snapshot["issue_key"]
            )
            operation.state = "completed"
        except UncertainJiraWrite:
            result = {
                "status": "uncertain",
                "error": "Jira did not confirm the write; reconcile before proceeding",
            }
            operation.state = "uncertain"
        except ServiceError:
            result = {
                "status": "rejected",
                "error": "Jira permissions, issue version or field requirements changed; no automatic retry",
            }
            operation.state = "failed"
        operation.result = result
        audit(
            session,
            principal,
            "jira.delivery_result",
            operation.id,
            {"state": operation.state, "status": result["status"]},
        )
        return {"operation_id": operation.id, "state": operation.state, "result": result}


async def publish_slack(record, adapter):
    from .services.slack_delivery import SlackDeliveryService

    with session_scope() as session:
        job = owned_job(session, record)
        principal, _ = authorized(session, job)
        session.commit()
        _, binding, account, _ = await adapter.access(session, principal)
        job = owned_job(session, record)
        principal, _ = authorized(session, job)
        operation = must_get(session, SlackOperation, job.payload["operation_id"])
        proposal = must_get(session, SlackProposal, operation.proposal_id)
        service = SlackDeliveryService(session, principal, adapter)
        if (
            proposal.actor_id != principal.user_id
            or proposal.workspace_id != principal.scope
            or not proposal.approved_at
        ):
            raise ServiceError(status_code=403, error="Slack delivery approval is unavailable")
        service.validate(proposal, binding, account)
        if operation.state == "completed":
            return {"operation_id": operation.id, "state": operation.state, "result": operation.result}
        if operation.state != "queued" or record["recovered"]:
            operation.state, operation.result = (
                "uncertain",
                {
                    "status": "uncertain",
                    "safe_error": "Recovered Slack delivery requires reconciliation; no write repeated",
                },
            )
            return {"operation_id": operation.id, "state": operation.state, "result": operation.result}
        operation.state, operation.result = (
            "sending",
            {"status": "uncertain", "safe_error": "Write intent recorded"},
        )
        session.commit()
        _, binding, account, token = await adapter.access(session, principal)
        job = owned_job(session, record)
        principal, _ = authorized(session, job)
        service.validate(proposal, binding, account)
        try:
            await adapter.channel(token, proposal.destination["channel_id"])
            if proposal.target:
                message = await adapter.message(token, proposal.destination, proposal.target["message_ts"])
                if content_hash(message) != proposal.target["observed_content_hash"]:
                    raise ServiceError(
                        status_code=409, error="Slack message changed after preview; no update sent"
                    )
            result = await adapter.write(
                token,
                proposal.destination,
                proposal.action,
                proposal.payload,
                proposal.target["message_ts"] if proposal.target else None,
            )
            operation.state = "completed"
        except UncertainSlackWrite:
            operation.state = "uncertain"
            result = {
                "status": "uncertain",
                "safe_error": "Slack did not confirm the write; reconcile before proceeding",
            }
        except ServiceError:
            operation.state = "failed"
            result = {
                "status": "rejected",
                "safe_error": "Slack permissions, channel or message changed; no automatic retry",
            }
        operation.result = result
        audit(
            session,
            principal,
            "slack.delivery_result",
            operation.id,
            {"state": operation.state, "status": result["status"]},
        )
        return {"operation_id": operation.id, "state": operation.state, "result": result}


async def execute(record, adapter=None, linkedin_adapter=None):
    if record["kind"] == "linkedin_publish":
        return await publish_linkedin(record, linkedin_adapter or adapter)
    if record["kind"] == "slack_publish":
        return await publish_slack(record, adapter or SlackDeliveryAdapter())
    if record["kind"] == "jira_publish":
        return await publish_jira(record, adapter or JiraDeliveryAdapter())
    if record["kind"] == "publish":
        return await publish(record, adapter or GitHubAdapter())
    with session_scope() as session:
        job = owned_job(session, record)
        principal, _ = authorized(session, job)
        visitor = must_get(session, User, principal.user_id).is_visitor
        revision_id = job.payload["revision_id"]
        chunks = session.scalars(
            select(TranscriptChunk)
            .where(TranscriptChunk.revision_id == revision_id)
            .order_by(TranscriptChunk.chunk_index)
        ).all()
        records = [
            {"id": chunk.id, "i": chunk.chunk_index, "text": chunk.text, "speaker": chunk.speaker}
            for chunk in chunks
        ]
    if record["kind"] == "index":
        provider = "hash" if visitor else settings.embed_provider
        model = "deterministic-hash" if visitor else settings.embed_model
        vectors = await asyncio.to_thread(
            get_embedding_function(provider),
            [row["text"] for row in records],
            model,
        )
        if len(vectors) != len(records):
            raise ServiceError(status_code=500, error="Embedding count mismatch")
        with session_scope() as session:
            job = owned_job(session, record)
            authorized(session, job)
            revision = must_get(session, TranscriptRevision, revision_id)
            for row, vector in zip(records, vectors, strict=True):
                must_get(session, TranscriptChunk, row["id"]).embedding = vector
            revision.index_status, revision.embed_provider, revision.embed_model = (
                "ready",
                provider,
                model,
            )
        return {"chunks_indexed": len(records), "provider": provider}
    generated = await ExtractionService(None).generate_records(records, use_model=not visitor)
    with session_scope() as session:
        job = owned_job(session, record)
        principal, meeting = authorized(session, job)
        meeting = session.scalar(select(Meeting).where(Meeting.id == meeting.id).with_for_update())
        if meeting is None:
            raise ServiceError(status_code=409, error="Meeting disappeared during extraction")
        result = ExtractionService(session).persist(meeting, revision_id, generated)
        audit(
            session,
            principal,
            "extraction.completed",
            meeting.id,
            {"created": result["created"], "mode": result["mode"]},
        )
        return result


async def run_once(adapter=None, *, linkedin_adapter=None):
    record = await asyncio.to_thread(claim)
    if not record:
        return False
    pulse = asyncio.create_task(heartbeat(record))
    try:
        result = await execute(record, adapter, linkedin_adapter)
        with session_scope() as session:
            job = owned_job(session, record)
            job.state, job.result = "completed", result
            job.lease_until = None
    except Exception as exc:  # noqa: BLE001 -- Durable jobs must record any unexpected failure.
        # Log only a class/code: SQL, transcripts and credentials stay out of logs.
        code = f"service_{exc.status_code}" if isinstance(exc, ServiceError) else type(exc).__name__
        log.error("job_failed", extra={"job_id": record["id"], "error_code": code})
        with session_scope() as session:
            job = session.get(Job, record["id"])
            if job and job.lease_token == record["lease"]:
                job.state, job.error_code, job.lease_until = "failed", code, None
                if job.kind == "publish":
                    operation = must_get(session, PublicationOperation, job.payload["operation_id"])
                    operation.state = (
                        "uncertain"
                        if any(row["status"] == "uncertain" for row in operation.results)
                        else "failed"
                    )
                    job.result = {
                        "operation_id": operation.id,
                        "state": operation.state,
                        "results": operation.results,
                    }
                if job.kind == "jira_publish":
                    jira_operation = must_get(session, JiraOperation, job.payload["operation_id"])
                    jira_operation.state = (
                        "uncertain"
                        if jira_operation.result and jira_operation.result.get("status") == "uncertain"
                        else "failed"
                    )
                    job.result = {
                        "operation_id": jira_operation.id,
                        "state": jira_operation.state,
                        "result": jira_operation.result,
                    }
                if job.kind == "slack_publish":
                    slack_operation = must_get(session, SlackOperation, job.payload["operation_id"])
                    slack_operation.state = (
                        "uncertain"
                        if slack_operation.result and slack_operation.result.get("status") == "uncertain"
                        else "failed"
                    )
                    slack_operation.result = slack_operation.result or {
                        "status": "not_sent",
                        "safe_error": "Slack delivery authorization or source changed before sending",
                    }
                    job.result = {
                        "operation_id": slack_operation.id,
                        "state": slack_operation.state,
                        "result": slack_operation.result,
                    }
                if job.kind == "linkedin_publish":
                    linkedin_operation = must_get(session, LinkedInOperation, job.payload["operation_id"])
                    linkedin_operation.state = (
                        "uncertain"
                        if linkedin_operation.result
                        and linkedin_operation.result.get("status") == "uncertain"
                        else "failed"
                    )
                    linkedin_operation.result = linkedin_operation.result or {
                        "status": "not_sent",
                        "error": "LinkedIn authorization or source changed before sending",
                    }
                    job.result = {
                        "operation_id": linkedin_operation.id,
                        "state": linkedin_operation.state,
                        "result": linkedin_operation.result,
                    }
                if job.kind == "index":
                    must_get(session, TranscriptRevision, job.payload["revision_id"]).index_status = "failed"
    finally:
        pulse.cancel()
        try:
            await pulse
        except (asyncio.CancelledError, ServiceError):
            pass
    return True


async def serve():
    while True:
        if not await run_once():
            await asyncio.sleep(1)


def main():
    from .observability import configure_logging

    configure_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    asyncio.run(run_once() if args.once else serve())


if __name__ == "__main__":
    main()
