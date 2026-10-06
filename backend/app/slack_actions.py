"""Signed Slack requests act only through browser-confirmed, current workspace identities."""

import hashlib
import hmac
import json
import re
import secrets
import time
from datetime import date, timedelta
from urllib.parse import parse_qs

import httpx
from pydantic import ValidationError
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from .access_policy import is_private_scope, require_private_scope
from .auth import Principal, aware, digest, require_role
from .models import (
    AuthSession,
    Membership,
    ProviderConnection,
    ProviderDestination,
    SlackAccount,
    SlackIdentity,
    SlackInboundReceipt,
    SlackInteractionContext,
    SlackLinkChallenge,
    User,
    now,
    uid,
)
from .provider_credentials import unseal
from .schemas import IndexInput, PlanInput, PlanPatch
from .services.common import audit
from .services.errors import ServiceError
from .services.meetings import MeetingService
from .services.planning import PlanningService
from .settings import settings
from .slack import BASE, SCOPES, provider_id

MAX_BODY = 65536
ROLES = {"owner", "reviewer", "editor"}


def enabled() -> bool:
    return bool(
        settings.slack_configured
        and settings.slack_interactions_enabled
        and settings.slack_app_id
        and settings.slack_signing_secret.get_secret_value()
        and not settings.public_demo_mode
    )


def verify_request(body: bytes, timestamps: list[str], signatures: list[str]) -> str:
    if not enabled():
        raise ServiceError(
            status_code=503, error="Slack interactions require an enabled, awake endpoint", where="slack"
        )
    if len(body) > MAX_BODY:
        raise ServiceError(status_code=413, error="Slack request exceeds the limit", where="slack")
    if (
        len(timestamps) != 1
        or len(signatures) != 1
        or not re.fullmatch(r"[0-9]{10}", timestamps[0])
        or not re.fullmatch(r"v0=[a-f0-9]{64}", signatures[0])
    ):
        raise ServiceError(status_code=401, error="Slack signature is invalid", where="slack")
    timestamp = timestamps[0]
    if abs(time.time() - int(timestamp)) > 300:
        raise ServiceError(status_code=401, error="Slack request has expired", where="slack")
    signed = b"v0:" + timestamp.encode() + b":" + body
    expected = (
        "v0="
        + hmac.new(
            settings.slack_signing_secret.get_secret_value().encode(), signed, hashlib.sha256
        ).hexdigest()
    )
    if not hmac.compare_digest(expected, signatures[0]):
        raise ServiceError(status_code=401, error="Slack signature is invalid", where="slack")
    return hashlib.sha256(signed).hexdigest()


def parse_form(body: bytes) -> dict:
    try:
        parsed = parse_qs(
            body.decode("utf-8"), keep_blank_values=True, strict_parsing=True, max_num_fields=40
        )
    except (ValueError, UnicodeError) as exc:
        raise ServiceError(status_code=422, error="Slack form could not be validated", where="slack") from exc
    if any(len(values) != 1 for values in parsed.values()):
        raise ServiceError(status_code=422, error="Slack form contains repeated fields", where="slack")
    return {key: values[0] for key, values in parsed.items()}


def message(value: str) -> dict:
    return {"response_type": "ephemeral", "text": value}


def plain(value: str) -> dict:
    return {"type": "plain_text", "text": value}


def input_block(key: str, label: str, element: dict, *, optional: bool = False) -> dict:
    return {
        "type": "input",
        "block_id": key,
        "label": plain(label),
        "element": {"action_id": "value", **element},
        "optional": optional,
    }


class SlackActions:
    def __init__(self, session: Session, transport: httpx.AsyncBaseTransport | None = None):
        self.session, self.transport = session, transport

    def account(self, connection_id: str, workspace_id: str | None = None):
        if not enabled():
            raise ServiceError(status_code=503, error="Slack interactions are disabled", where="slack")
        connection = self.session.get(ProviderConnection, connection_id)
        if not connection:
            raise ServiceError(
                status_code=403, error="Slack installation authority is unavailable", where="slack"
            )
        # Reconnection locks the owner before changing installation generation.
        # Keep the same order here instead of taking the account row first.
        owner = self.session.scalar(
            select(User)
            .where(User.id == connection.user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        connection = self.session.scalar(
            select(ProviderConnection)
            .where(ProviderConnection.id == connection_id)
            .execution_options(populate_existing=True)
        )
        bindings = self.session.scalars(
            select(ProviderDestination)
            .where(
                ProviderDestination.connection_id == connection_id,
                *([ProviderDestination.workspace_id == workspace_id] if workspace_id else []),
            )
            .order_by(ProviderDestination.workspace_id)
        ).all()
        permitted = []
        for binding in bindings:
            member = self.session.scalar(
                select(Membership)
                .where(Membership.workspace_id == binding.workspace_id, Membership.user_id == binding.user_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if (
                owner
                and owner.active
                and member
                and member.role == "owner"
                and is_private_scope(self.session, Principal(owner.id, binding.workspace_id, member.role))
            ):
                permitted.append(binding)
        account = self.session.scalar(
            select(SlackAccount)
            .where(SlackAccount.connection_id == connection_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            not account
            or not connection
            or connection.provider != "slack"
            or connection.state != "connected"
            or not SCOPES.issubset(set(connection.scopes))
        ):
            raise ServiceError(
                status_code=403, error="Slack installation authority is unavailable", where="slack"
            )
        if not permitted:
            raise ServiceError(
                status_code=403, error="Slack workspace installation authority was revoked", where="slack"
            )
        return account, connection

    def principal(self, identity: SlackIdentity) -> Principal:
        account, _ = self.account(identity.connection_id, identity.workspace_id)
        user = self.session.scalar(select(User).where(User.id == identity.user_id).with_for_update())
        member = self.session.scalar(
            select(Membership)
            .where(Membership.user_id == identity.user_id, Membership.workspace_id == identity.workspace_id)
            .with_for_update()
        )
        if (
            not user
            or not user.active
            or not member
            or identity.account_version != account.version
            or identity.auth_version != user.auth_version
        ):
            raise ServiceError(
                status_code=403, error="Confirm your current Slack identity in M2O", where="slack"
            )
        require_role(Principal(user.id, identity.workspace_id, member.role), ROLES)
        principal = Principal(user.id, identity.workspace_id, member.role, auth_version=identity.auth_version)
        require_private_scope(self.session, principal)
        return principal

    def browser(self, principal: Principal):
        require_private_scope(self.session, principal)
        browser = self.session.get(AuthSession, principal.session_hash) if principal.session_hash else None
        user = self.session.get(User, principal.user_id)
        member = self.session.get(Membership, (principal.scope, principal.user_id))
        if (
            not browser
            or browser.user_id != principal.user_id
            or aware(browser.expires_at) <= now()
            or not user
            or not user.active
            or not member
        ):
            raise ServiceError(
                status_code=403, error="Link Slack from your signed-in M2O browser", where="slack"
            )
        require_role(Principal(principal.user_id, principal.scope, member.role), ROLES)

    def link_status(self, principal: Principal) -> dict:
        if not is_private_scope(self.session, principal):
            return {"enabled": False, "can_link": False, "installations": []}
        current_user = self.session.get(User, principal.user_id)
        assert current_user is not None
        installations = []
        for account in self.session.scalars(
            select(SlackAccount)
            .join(ProviderDestination, ProviderDestination.connection_id == SlackAccount.connection_id)
            .where(ProviderDestination.workspace_id == principal.scope)
        ):
            try:
                self.account(account.connection_id, principal.scope)
            except ServiceError:
                continue
            identity = self.session.scalar(
                select(SlackIdentity).where(
                    SlackIdentity.connection_id == account.connection_id,
                    SlackIdentity.workspace_id == principal.scope,
                    SlackIdentity.user_id == principal.user_id,
                )
            )
            installations.append(
                {
                    "connection_id": account.connection_id,
                    "team_id": account.team_id,
                    "team_name": account.team_name,
                    "linked": bool(
                        identity
                        and identity.account_version == account.version
                        and identity.auth_version == current_user.auth_version
                    ),
                    "slack_user_id": identity.slack_user_id if identity else None,
                }
            )
        return {
            "enabled": enabled(),
            "can_link": enabled()
            and principal.role in ROLES
            and bool(principal.session_hash)
            and bool(installations),
            "installations": installations,
        }

    def begin_link(self, principal: Principal, connection_id: str) -> dict:
        self.browser(principal)
        account, _ = self.account(connection_id, principal.scope)
        self.session.execute(
            delete(SlackLinkChallenge).where(
                SlackLinkChallenge.user_id == principal.user_id,
                SlackLinkChallenge.workspace_id == principal.scope,
            )
        )
        code = secrets.token_urlsafe(24)
        challenge = SlackLinkChallenge(
            workspace_id=principal.scope,
            user_id=principal.user_id,
            connection_id=connection_id,
            account_version=account.version,
            session_hash=principal.session_hash,
            code_hash=digest(code),
            expires_at=now() + timedelta(minutes=5),
        )
        self.session.add(challenge)
        self.session.flush()
        return {
            "challenge_id": challenge.id,
            "command": "/m2o link " + code,
            "team_id": account.team_id,
            "team_name": account.team_name,
            "expires_at": challenge.expires_at.isoformat(),
        }

    def challenge(self, principal: Principal, challenge_id: str):
        self.browser(principal)
        challenge = self.session.scalar(
            select(SlackLinkChallenge)
            .where(
                SlackLinkChallenge.id == challenge_id,
                SlackLinkChallenge.workspace_id == principal.scope,
                SlackLinkChallenge.user_id == principal.user_id,
            )
            .with_for_update()
        )
        if (
            not challenge
            or challenge.session_hash != principal.session_hash
            or aware(challenge.expires_at) <= now()
            or challenge.consumed_at
        ):
            raise ServiceError(
                status_code=409, error="Slack link challenge expired; start again", where="slack"
            )
        account, _ = self.account(challenge.connection_id, principal.scope)
        if challenge.account_version != account.version:
            raise ServiceError(
                status_code=409, error="Slack installation changed; start again", where="slack"
            )
        return challenge, account

    def pending_link(self, principal: Principal, challenge_id: str) -> dict:
        challenge, account = self.challenge(principal, challenge_id)
        return {
            "challenge_id": challenge.id,
            "team_id": account.team_id,
            "team_name": account.team_name,
            "slack_user_id": challenge.pending_slack_user_id,
            "expires_at": challenge.expires_at.isoformat(),
        }

    def confirm_link(self, principal: Principal, challenge_id: str, slack_user_id: str) -> dict:
        challenge, account = self.challenge(principal, challenge_id)
        if not challenge.pending_slack_user_id or challenge.pending_slack_user_id != slack_user_id:
            raise ServiceError(
                status_code=409,
                error="Review the Slack member that submitted your linking code",
                where="slack",
            )
        other = self.session.scalar(
            select(SlackIdentity).where(
                SlackIdentity.workspace_id == principal.scope,
                SlackIdentity.connection_id == account.connection_id,
                SlackIdentity.slack_user_id == slack_user_id,
            )
        )
        if other and other.user_id != principal.user_id:
            raise ServiceError(
                status_code=409,
                error="This Slack member is already linked to another M2O user",
                where="slack",
            )
        identity = self.session.scalar(
            select(SlackIdentity)
            .where(
                SlackIdentity.workspace_id == principal.scope,
                SlackIdentity.connection_id == account.connection_id,
                SlackIdentity.user_id == principal.user_id,
            )
            .with_for_update()
        )
        if not identity:
            identity = SlackIdentity(
                workspace_id=principal.scope,
                user_id=principal.user_id,
                connection_id=account.connection_id,
                slack_user_id=slack_user_id,
                account_version=account.version,
            )
            self.session.add(identity)
        else:
            identity.version += 1
            current_user = self.session.get(User, principal.user_id)
            assert current_user is not None
            identity.auth_version = current_user.auth_version
            identity.slack_user_id, identity.account_version, identity.confirmed_at = (
                slack_user_id,
                account.version,
                now(),
            )
        challenge.consumed_at = now()
        self.session.flush()
        audit(self.session, principal, "slack.identity_confirmed", identity.id)
        return self.link_status(principal)

    def unlink(self, principal: Principal, connection_id: str) -> dict:
        self.browser(principal)
        identity = self.session.scalar(
            select(SlackIdentity)
            .where(
                SlackIdentity.user_id == principal.user_id,
                SlackIdentity.workspace_id == principal.scope,
                SlackIdentity.connection_id == connection_id,
            )
            .with_for_update()
        )
        if identity:
            audit(self.session, principal, "slack.identity_removed", identity.id)
            self.session.delete(identity)
        self.session.execute(
            delete(SlackLinkChallenge).where(
                SlackLinkChallenge.user_id == principal.user_id,
                SlackLinkChallenge.workspace_id == principal.scope,
                SlackLinkChallenge.connection_id == connection_id,
            )
        )
        self.session.flush()
        return {"ok": True}

    def installation(self, app_id, team_id):
        try:
            # Legacy shortcut payloads omit api_app_id; the signing secret and
            # configured app ID still bind that request to this application.
            app_id = provider_id(settings.slack_app_id if app_id is None else app_id, "A")
            team_id = provider_id(team_id, "T")
        except ValueError as exc:
            raise ServiceError(
                status_code=422, error="Slack app and team are required", where="slack"
            ) from exc
        if app_id != settings.slack_app_id:
            raise ServiceError(
                status_code=403, error="Slack request belongs to another application", where="slack"
            )
        account = self.session.scalar(
            select(SlackAccount).where(SlackAccount.app_id == app_id, SlackAccount.team_id == team_id)
        )
        if not account:
            raise ServiceError(
                status_code=403, error="Slack installation is not connected to M2O", where="slack"
            )
        self.account(account.connection_id)
        return account

    def identity(self, account, slack_user_id, workspace_id=None):
        try:
            slack_user_id = provider_id(slack_user_id, "UW")
        except ValueError as exc:
            raise ServiceError(status_code=422, error="Slack member is invalid", where="slack") from exc
        identities = self.session.scalars(
            select(SlackIdentity)
            .where(
                SlackIdentity.connection_id == account.connection_id,
                SlackIdentity.slack_user_id == slack_user_id,
                *([SlackIdentity.workspace_id == workspace_id] if workspace_id else []),
            )
            .with_for_update()
        ).all()
        if len(identities) != 1:
            raise ServiceError(
                status_code=409,
                error="Link this Slack account in M2O first; when linked to multiple workspaces, add the workspace ID to the command",
                where="slack",
            )
        self.principal(identities[0])
        return identities[0]

    def context(self, identity, kind, payload):
        token = secrets.token_urlsafe(32)
        self.session.add(
            SlackInteractionContext(
                token_hash=digest(token),
                identity_id=identity.id,
                identity_version=identity.version,
                kind=kind,
                payload=payload,
                expires_at=now() + timedelta(minutes=10),
            )
        )
        self.session.flush()
        return token

    def capture_view(self, identity, transcript=""):
        token = self.context(identity, "capture", {})
        return {
            "type": "modal",
            "callback_id": "m2o_capture",
            "private_metadata": token,
            "title": plain("Capture a meeting"),
            "submit": plain("Save in M2O"),
            "close": plain("Cancel"),
            "blocks": [
                {
                    "type": "section",
                    "text": plain(
                        "Save notes or transcript text privately, then review participants and outcomes in M2O. This does not import a recording or publish anything."
                    ),
                },
                input_block("title", "Meeting title", {"type": "plain_text_input", "max_length": 200}),
                input_block(
                    "transcript",
                    "Transcript or notes",
                    {
                        "type": "plain_text_input",
                        "multiline": True,
                        "max_length": 3000,
                        **({"initial_value": transcript[:3000]} if transcript else {}),
                    },
                ),
                input_block(
                    "occurred",
                    "Meeting date",
                    {"type": "datepicker", "initial_date": date.today().isoformat()},
                ),
                input_block(
                    "timezone",
                    "IANA timezone",
                    {"type": "plain_text_input", "max_length": 60, "initial_value": "UTC"},
                ),
            ],
        }

    def plan_view(self, identity, day: date):
        principal = self.principal(identity)
        plan = PlanningService(self.session, principal).list(day)
        choices = {}
        for entry in plan["entries"]:
            if not entry["stale"]:
                choices[entry["item_id"]] = {
                    "meeting_id": entry["meeting_id"],
                    "item_version": entry["item_version"],
                    "plan_version": entry["version"],
                    "title": entry["title"],
                }
        for entry in plan["candidates"]:
            if len(choices) >= 40:
                break
            choices.setdefault(
                entry["item_id"],
                {
                    "meeting_id": entry["meeting_id"],
                    "item_version": entry["item_version"],
                    "plan_version": None,
                    "title": entry["title"],
                },
            )
        if not choices:
            raise ServiceError(
                status_code=409,
                error="There are no current approved actions for this day; review or reconfirm outcomes in M2O",
                where="slack",
            )
        choices = dict(list(choices.items())[:40])
        token = self.context(identity, "plan", {"choices": choices})
        statuses = [
            {"text": plain(label), "value": value}
            for value, label in [
                ("planned", "Planned"),
                ("in_progress", "In progress"),
                ("blocked", "Blocked"),
                ("done", "Done"),
            ]
        ]
        priorities = [
            {"text": plain(label), "value": str(value)}
            for value, label in [(1, "High"), (2, "Normal"), (3, "Low")]
        ]
        return {
            "type": "modal",
            "callback_id": "m2o_plan",
            "private_metadata": token,
            "title": plain("My M2O plan"),
            "submit": plain("Save my progress"),
            "close": plain("Cancel"),
            "blocks": [
                {
                    "type": "section",
                    "text": plain(
                        "This updates only your personal M2O plan. Review approval and external issue status remain separate."
                    ),
                },
                input_block(
                    "item",
                    "Reviewed outcome",
                    {
                        "type": "static_select",
                        "options": [
                            {"text": plain(entry["title"][:75]), "value": key}
                            for key, entry in choices.items()
                        ],
                    },
                ),
                input_block(
                    "state",
                    "Your progress",
                    {"type": "static_select", "options": statuses, "initial_option": statuses[0]},
                ),
                input_block("day", "Planned date", {"type": "datepicker", "initial_date": day.isoformat()}),
                input_block(
                    "priority",
                    "Priority",
                    {"type": "static_select", "options": priorities, "initial_option": priorities[1]},
                ),
            ],
        }

    async def open_view(self, identity, trigger_id, view):
        if not isinstance(trigger_id, str) or not 1 <= len(trigger_id) <= 256:
            raise ServiceError(status_code=422, error="Slack trigger is unavailable", where="slack")
        _, connection = self.account(identity.connection_id, identity.workspace_id)
        if connection.expires_at and aware(connection.expires_at) <= now() + timedelta(seconds=60):
            raise ServiceError(
                status_code=409,
                error="Refresh the Slack connection from M2O before opening this form",
                where="slack",
            )
        token = unseal(connection)["access_token"]
        try:
            async with httpx.AsyncClient(
                timeout=1.5, transport=self.transport, trust_env=False, follow_redirects=False
            ) as client:
                response = await client.post(
                    BASE + "views.open",
                    headers={"Authorization": "Bearer " + token},
                    json={"trigger_id": trigger_id, "view": view},
                )
            if (
                response.status_code != 200
                or len(response.content) > MAX_BODY
                or response.json().get("ok") is not True
            ):
                raise ValueError("Modal response not verified")
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            raise ServiceError(
                status_code=409,
                error="The Slack form could not be opened; run the command again",
                where="slack",
            ) from exc

    async def command(self, form):
        account = self.installation(form.get("api_app_id"), form.get("team_id"))
        if form.get("command") != "/m2o" or not isinstance(form.get("text"), str) or len(form["text"]) > 1000:
            raise ServiceError(status_code=422, error="Use a supported M2O command", where="slack")
        parts = form["text"].split()
        action = parts[0] if parts else "help"
        slack_user = provider_id(form.get("user_id"), "UW")
        if action == "help":
            return message(
                "Use /m2o link CODE from M2O Connections, /m2o meeting, or /m2o plan [YYYY-MM-DD]. If you linked several M2O workspaces, append the workspace ID."
            )
        if action == "link" and len(parts) == 2 and re.fullmatch(r"[A-Za-z0-9_-]{32}", parts[1]):
            challenge = self.session.scalar(
                select(SlackLinkChallenge)
                .where(
                    SlackLinkChallenge.code_hash == digest(parts[1]),
                    SlackLinkChallenge.connection_id == account.connection_id,
                )
                .with_for_update()
            )
            if (
                not challenge
                or aware(challenge.expires_at) <= now()
                or challenge.consumed_at
                or challenge.account_version != account.version
            ):
                raise ServiceError(
                    status_code=409, error="Linking code expired; generate a new code in M2O", where="slack"
                )
            browser = self.session.get(AuthSession, challenge.session_hash)
            if not browser or aware(browser.expires_at) <= now():
                raise ServiceError(
                    status_code=409, error="Sign in to M2O and generate a new linking code", where="slack"
                )
            if challenge.pending_slack_user_id and challenge.pending_slack_user_id != slack_user:
                raise ServiceError(
                    status_code=409,
                    error="This code has already been submitted; generate a new one",
                    where="slack",
                )
            challenge.pending_slack_user_id = slack_user
            return message(
                "Return to the M2O browser that generated this code. Review this Slack member ID ("
                + slack_user
                + ") and confirm the link there. No account link is active yet."
            )
        if action not in {"meeting", "plan"} or len(parts) > (3 if action == "plan" else 2):
            raise ServiceError(status_code=422, error="Use /m2o help for supported commands", where="slack")
        day, workspace_id = date.today(), None
        for value in parts[1:]:
            if action == "plan" and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
                day = date.fromisoformat(value)
            elif re.fullmatch(r"[a-f0-9-]{36}", value) and workspace_id is None:
                workspace_id = value
            else:
                raise ServiceError(status_code=422, error="Command arguments are invalid", where="slack")
        identity = self.identity(account, slack_user, workspace_id)
        view = self.capture_view(identity) if action == "meeting" else self.plan_view(identity, day)
        await self.open_view(identity, form.get("trigger_id"), view)
        return message("The M2O form is open. Changes are saved only when you submit it.")

    @staticmethod
    def value(values, key, kind="value") -> str:
        entry = values.get(key, {}).get("value", {})
        if not isinstance(entry, dict):
            raise ValueError("Invalid form value")
        value = (
            entry.get("selected_option", {}).get("value")
            if kind == "select"
            else entry.get("selected_date")
            if kind == "date"
            else entry.get("value")
        )
        if not isinstance(value, str) or not value.strip():
            raise ValueError("A required form value is missing")
        return value

    def submission(self, account, slack_user, payload):
        view = payload.get("view")
        if (
            not isinstance(view, dict)
            or not isinstance(view.get("private_metadata"), str)
            or len(view["private_metadata"]) > 100
        ):
            raise ServiceError(status_code=422, error="Slack form context is invalid", where="slack")
        context = self.session.scalar(
            select(SlackInteractionContext)
            .where(SlackInteractionContext.token_hash == digest(view["private_metadata"]))
            .with_for_update()
        )
        if not context or aware(context.expires_at) <= now():
            raise ServiceError(
                status_code=409, error="This form expired; open a fresh M2O form", where="slack"
            )
        identity = self.session.get(SlackIdentity, context.identity_id)
        if (
            not identity
            or identity.connection_id != account.connection_id
            or identity.slack_user_id != slack_user
            or identity.version != context.identity_version
        ):
            raise ServiceError(
                status_code=403, error="This form belongs to another linked account", where="slack"
            )
        principal = self.principal(identity)
        if context.consumed_at:
            return context.acknowledgement or {}
        if view.get("callback_id") != "m2o_" + context.kind:
            raise ServiceError(
                status_code=422, error="Slack form type does not match its context", where="slack"
            )
        values = view.get("state", {}).get("values")
        if not isinstance(values, dict):
            raise ServiceError(status_code=422, error="Slack form values are missing", where="slack")
        if context.kind == "capture":
            request = IndexInput.model_validate(
                dict(
                    meeting_id="slack-" + uid(),
                    title=self.value(values, "title"),
                    transcript=self.value(values, "transcript"),
                    occurred_on=self.value(values, "occurred", "date"),
                    timezone=self.value(values, "timezone"),
                    visibility="restricted",
                )
            )
            if len(request.transcript) > 3000:
                raise ServiceError(
                    status_code=422, error="Slack meeting text exceeds 3000 characters", where="slack"
                )
            result = MeetingService(self.session, principal).index(request)
            audit(self.session, principal, "slack.meeting_captured", result["job_id"])
        else:
            item_id = self.value(values, "item", "select")
            selected = context.payload["choices"].get(item_id)
            if not selected:
                raise ServiceError(status_code=422, error="Select an outcome from this form", where="slack")
            request = PlanInput(
                expected_item_version=selected["item_version"],
                planned_on=date.fromisoformat(self.value(values, "day", "date")),
                priority=int(self.value(values, "priority", "select")),
            )
            state = self.value(values, "state", "select")
            service = PlanningService(self.session, principal)
            version = selected["plan_version"]
            if version is None:
                # Validate the entire transition before adding any personal state.
                patch = PlanPatch.model_validate(
                    {**request.model_dump(), "expected_version": 1, "state": state}
                )
                result = service.add(selected["meeting_id"], item_id, request)
                if state != "planned":
                    result = service.patch(selected["meeting_id"], item_id, patch)
            else:
                result = service.patch(
                    selected["meeting_id"],
                    item_id,
                    PlanPatch.model_validate(
                        {**request.model_dump(), "expected_version": version, "state": state}
                    ),
                )
            audit(self.session, principal, "slack.personal_progress_saved", result["id"])
        context.consumed_at, context.acknowledgement = now(), {}
        self.session.flush()
        return {}

    async def interaction(self, payload):
        if not isinstance(payload, dict):
            raise ServiceError(status_code=422, error="Slack payload is invalid", where="slack")
        team, user = payload.get("team"), payload.get("user")
        account = self.installation(
            payload.get("api_app_id"), team.get("id") if isinstance(team, dict) else None
        )
        slack_user = provider_id(user.get("id") if isinstance(user, dict) else None, "UW")
        kind = payload.get("type")
        if kind == "view_submission":
            return self.submission(account, slack_user, payload)
        expected_callback = "m2o_capture_meeting" if kind == "shortcut" else "m2o_capture_message"
        if kind not in {"shortcut", "message_action"} or payload.get("callback_id") != expected_callback:
            raise ServiceError(status_code=422, error="Unsupported Slack interaction", where="slack")
        identity = self.identity(account, slack_user)
        transcript = payload.get("message", {}).get("text", "") if kind == "message_action" else ""
        if not isinstance(transcript, str):
            raise ServiceError(status_code=422, error="Message text is invalid", where="slack")
        await self.open_view(identity, payload.get("trigger_id"), self.capture_view(identity, transcript))
        return {}

    async def receive(self, body: bytes, request_hash: str, *, interactive: bool):
        if self.session.bind is not None and self.session.bind.dialect.name == "postgresql":
            self.session.execute(text("SET LOCAL lock_timeout = '750ms'"))
            self.session.execute(text("SET LOCAL statement_timeout = '1500ms'"))
        form = parse_form(body)
        try:
            payload = json.loads(form.get("payload", "null")) if interactive else None
        except (ValueError, RecursionError) as exc:
            raise ServiceError(status_code=422, error="Slack payload is invalid", where="slack") from exc
        if interactive and (not isinstance(payload, dict) or not isinstance(payload.get("team"), dict)):
            raise ServiceError(status_code=422, error="Slack payload requires an app and team", where="slack")
        account = (
            self.installation(payload.get("api_app_id"), payload.get("team", {}).get("id"))
            if isinstance(payload, dict)
            else self.installation(form.get("api_app_id"), form.get("team_id"))
        )
        # Serialize requests per installation so concurrent retries cannot execute twice.
        self.account(account.connection_id)
        previous = self.session.get(SlackInboundReceipt, request_hash)
        if previous and aware(previous.expires_at) > now():
            return previous.acknowledgement
        try:
            with self.session.begin_nested():
                result = await self.interaction(payload) if interactive else await self.command(form)
        except (ServiceError, ValidationError, ValueError, TypeError, AttributeError, KeyError) as exc:
            safe = (
                exc.detail["error"]
                if isinstance(exc, ServiceError)
                else "This form could not be validated; reopen it and review the current data"
            )
            if interactive:
                if isinstance(payload, dict) and payload.get("type") == "view_submission":
                    values = payload.get("view", {}).get("state", {}).get("values", {})
                    block = "title" if "title" in values else "item"
                    result = {"response_action": "errors", "errors": {block: safe[:200]}}
                else:
                    result = message(safe)
            else:
                result = message(safe)
        self.session.execute(delete(SlackInboundReceipt).where(SlackInboundReceipt.expires_at <= now()))
        self.session.execute(
            delete(SlackInteractionContext).where(SlackInteractionContext.expires_at <= now())
        )
        self.session.execute(delete(SlackLinkChallenge).where(SlackLinkChallenge.expires_at <= now()))
        self.session.add(
            SlackInboundReceipt(
                request_hash=request_hash, acknowledgement=result, expires_at=now() + timedelta(minutes=10)
            )
        )
        self.session.commit()
        return result
