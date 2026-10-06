"""Google Meet read-only OAuth and bounded structured transcript retrieval."""

import asyncio
import hashlib
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import NoReturn
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from .access_policy import aware, require_private_account, require_private_scope, workspace_access
from .auth import Principal, digest, require_role
from .models import (
    AuthSession,
    GoogleMeetAccount,
    GoogleMeetPreview,
    IntegrationOAuthState,
    Membership,
    ProviderConnection,
    ProviderDestination,
    User,
    Workspace,
    now,
    uid,
)
from .provider_credentials import seal, unseal
from .services.common import audit
from .services.errors import ServiceError
from .settings import settings

SCOPE = "https://www.googleapis.com/auth/meetings.space.readonly"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://meet.googleapis.com/v2/"
RESOURCE = r"[A-Za-z0-9_-]{1,128}"


def fail(message: str, status: int = 502) -> NoReturn:
    raise ServiceError(status_code=status, error=message, where="google_meet")


class Token(BaseModel):
    model_config = ConfigDict(extra="ignore")
    access_token: str = Field(min_length=1, max_length=16000)
    refresh_token: str | None = Field(default=None, min_length=1, max_length=16000)
    expires_in: int = Field(strict=True, ge=1, le=86400)
    scope: str | None = Field(default=None, max_length=2000)
    token_type: str = "Bearer"


def connection_query(principal: Principal):
    return select(ProviderConnection).where(
        ProviderConnection.user_id == principal.user_id, ProviderConnection.provider == "google_meet"
    )


class GoogleMeetAdapter:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self.transport = transport

    def authority(self, session: Session, principal: Principal, *, lock: bool = False):
        require_private_scope(session, principal)
        require_role(principal, {"owner", "reviewer", "editor"})
        if settings.public_demo_mode:
            fail("Live imports are disabled in public demo mode", 403)
        if lock:
            if session.get_bind().dialect.name == "postgresql":
                session.execute(text("SET LOCAL lock_timeout = '2s'"))
                session.execute(text("SET LOCAL statement_timeout = '5s'"))
            for model, predicate in (
                (User, User.id == principal.user_id),
                (
                    Membership,
                    (Membership.user_id == principal.user_id) & (Membership.workspace_id == principal.scope),
                ),
                (Workspace, Workspace.id == principal.scope),
            ):
                session.scalar(
                    select(model).where(predicate).with_for_update().execution_options(populate_existing=True)
                )
            workspace_access(session, principal)
        if not settings.google_meet_configured:
            fail("The operator must configure Google Meet OAuth before connecting", 503)

    def status(self, session: Session, principal: Principal) -> dict:
        user, workspace, member = workspace_access(session, principal)
        eligible = (
            not user.is_visitor
            and not workspace.is_demo
            and member.role in {"owner", "reviewer", "editor"}
            and not settings.public_demo_mode
        )
        binding = (
            session.scalar(
                select(ProviderDestination)
                .join(ProviderConnection, ProviderConnection.id == ProviderDestination.connection_id)
                .where(
                    ProviderDestination.workspace_id == principal.scope,
                    ProviderConnection.user_id == principal.user_id,
                    ProviderConnection.provider == "google_meet",
                )
            )
            if eligible
            else None
        )
        row = session.scalar(connection_query(principal)) if binding else None
        configured = settings.google_meet_configured and eligible
        return {
            "configured": configured,
            "state": row.state if row else "disconnected",
            "can_import": configured and row is not None and row.state == "connected",
            "setup_required": not settings.google_meet_configured,
            "source_format": "meet_api_entries",
            "transcription_required": True,
        }

    def begin(self, session: Session, principal: Principal) -> dict:
        self.authority(session, principal, lock=True)
        browser = session.get(AuthSession, principal.session_hash) if principal.session_hash else None
        user = session.get(User, principal.user_id)
        if (
            not browser
            or not user
            or browser.user_id != user.id
            or browser.auth_version != user.auth_version
            or aware(browser.expires_at) <= now()
        ):
            fail("Connect Google Meet from a signed-in browser", 403)
        state = secrets.token_urlsafe(32)
        session.execute(
            delete(IntegrationOAuthState).where(
                IntegrationOAuthState.user_id == principal.user_id,
                IntegrationOAuthState.provider == "google_meet",
            )
        )
        session.add(
            IntegrationOAuthState(
                state_hash=digest(state),
                user_id=principal.user_id,
                workspace_id=principal.scope,
                provider="google_meet",
                session_hash=browser.token_hash,
                expires_at=now() + timedelta(minutes=10),
            )
        )
        return {
            "url": "https://accounts.google.com/o/oauth2/v2/auth?"
            + urlencode(
                {
                    "client_id": settings.google_meet_client_id,
                    "redirect_uri": settings.google_meet_redirect_uri,
                    "response_type": "code",
                    "scope": SCOPE,
                    "state": state,
                    "access_type": "offline",
                    "prompt": "consent",
                    "include_granted_scopes": "false",
                }
            )
        }

    async def request(
        self,
        method: str,
        url: str,
        *,
        token: str | None = None,
        params: dict | None = None,
        data: dict | None = None,
    ) -> dict:
        if url != TOKEN_URL and not url.startswith(API):
            fail("Invalid Google endpoint")
        try:
            async with httpx.AsyncClient(
                timeout=10, trust_env=False, follow_redirects=False, transport=self.transport
            ) as client:
                async with client.stream(
                    method,
                    url,
                    params=params,
                    data=data,
                    headers={"Authorization": "Bearer " + token} if token else {},
                ) as response:
                    if response.status_code == 429:
                        fail("Google Meet is rate limiting reads; try again later", 429)
                    if response.status_code in {401, 403}:
                        fail("Google access was denied; reconnect or check meeting access", 403)
                    if response.status_code == 404:
                        fail("Google Meet artifact is unavailable or expired", 404)
                    chunks, size = [], 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > 2_000_000:
                            fail("Google response exceeds the safe import limit", 413)
                        chunks.append(chunk)
                    import json

                    payload = json.loads(b"".join(chunks))
                    if (
                        response.status_code == 400
                        and isinstance(payload, dict)
                        and payload.get("error") == "invalid_grant"
                    ):
                        fail("Google consent expired or was revoked; reconnect", 409)
                    response.raise_for_status()
                    if not isinstance(payload, dict):
                        raise ValueError("Expected object")
                    return payload
        except (httpx.HTTPError, ValueError) as exc:
            raise ServiceError(
                status_code=502,
                error="Google did not return a valid response; no transcript was imported",
                where="google_meet",
            ) from exc

    async def exchange(self, grant: dict) -> Token:
        payload = await self.request(
            "POST",
            TOKEN_URL,
            data={
                **grant,
                "client_id": settings.google_meet_client_id,
                "client_secret": settings.google_meet_client_secret.get_secret_value(),
            },
        )
        try:
            token = Token.model_validate(payload)
            if token.token_type.lower() != "bearer":
                raise ValueError("Invalid token type")
            return token
        except (ValidationError, ValueError) as exc:
            raise ServiceError(
                status_code=502, error="Google did not return a usable credential", where="google_meet"
            ) from exc

    async def complete(
        self, session: Session, principal: Principal, state: str, code: str | None, denied: bool = False
    ) -> str:
        session.scalar(
            select(User)
            .where(User.id == principal.user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        stored = session.scalar(
            select(IntegrationOAuthState)
            .where(IntegrationOAuthState.state_hash == digest(state))
            .with_for_update()
        )
        if (
            not stored
            or stored.provider != "google_meet"
            or stored.user_id != principal.user_id
            or stored.session_hash != principal.session_hash
            or aware(stored.expires_at) <= now()
        ):
            fail("Google connection request is invalid or expired", 400)
        member = session.get(Membership, (stored.workspace_id, principal.user_id))
        scoped = Principal(
            principal.user_id,
            stored.workspace_id,
            member.role if member else None,
            principal.session_hash,
            auth_version=principal.auth_version,
        )
        workspace_id = stored.workspace_id
        session.delete(stored)
        try:
            self.authority(session, scoped, lock=True)
            if denied or not code:
                session.commit()
                return workspace_id
            token = await self.exchange(
                {
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": settings.google_meet_redirect_uri,
                }
            )
            if token.scope is None or set(token.scope.split()) != {SCOPE} or not token.refresh_token:
                fail("Google must grant only renewable read-only Meet access; reconnect with consent", 403)
            self.authority(session, scoped, lock=True)
            row = session.scalar(
                connection_query(scoped).with_for_update().execution_options(populate_existing=True)
            )
            if row is None:
                row = ProviderConnection(id=uid(), user_id=scoped.user_id, provider="google_meet")
                session.add(row)
            row.state, row.scopes, row.expires_at, row.updated_at = (
                "connected",
                [SCOPE],
                now() + timedelta(seconds=token.expires_in),
                now(),
            )
            row.encrypted_credentials = seal(
                row, {"access_token": token.access_token, "refresh_token": token.refresh_token}
            )
            session.flush()
            account = session.get(GoogleMeetAccount, row.id)
            if account is None:
                account = GoogleMeetAccount(connection_id=row.id)
                session.add(account)
            account.generation = uid()
            session.execute(delete(GoogleMeetPreview).where(GoogleMeetPreview.connection_id == row.id))
            self.bind(session, scoped, row)
            audit(session, scoped, "google_meet.connected", row.id)
            session.commit()
            return workspace_id
        except ServiceError:
            session.rollback()
            session.execute(
                delete(IntegrationOAuthState).where(
                    IntegrationOAuthState.state_hash == digest(state),
                    IntegrationOAuthState.user_id == principal.user_id,
                    IntegrationOAuthState.provider == "google_meet",
                )
            )
            session.commit()
            raise

    @staticmethod
    def bind(session: Session, principal: Principal, row: ProviderConnection):
        binding = session.scalar(
            select(ProviderDestination).where(
                ProviderDestination.workspace_id == principal.scope,
                ProviderDestination.connection_id == row.id,
            )
        )
        if binding is None:
            session.add(
                ProviderDestination(
                    connection_id=row.id, user_id=principal.user_id, workspace_id=principal.scope
                )
            )

    async def access(self, session: Session, principal: Principal) -> tuple[str, str, str]:
        self.authority(session, principal, lock=True)
        row = session.scalar(
            connection_query(principal).with_for_update().execution_options(populate_existing=True)
        )
        account = session.get(GoogleMeetAccount, row.id) if row else None
        if (
            not row
            or not account
            or row.state != "connected"
            or row.expires_at is None
            or set(row.scopes) != {SCOPE}
        ):
            fail("Connect Google Meet before importing", 409)
        credentials = unseal(row)
        if aware(row.expires_at) <= now() + timedelta(seconds=60):
            try:
                token = await self.exchange(
                    {"grant_type": "refresh_token", "refresh_token": credentials["refresh_token"]}
                )
                if token.scope is not None and set(token.scope.split()) != {SCOPE}:
                    fail("Google changed the granted read-only permissions; reconnect", 403)
                self.authority(session, principal, lock=True)
                credentials = {
                    "access_token": token.access_token,
                    "refresh_token": token.refresh_token or credentials["refresh_token"],
                }
                row.encrypted_credentials = seal(row, credentials)
                row.expires_at, row.updated_at = now() + timedelta(seconds=token.expires_in), now()
            except ServiceError as exc:
                if exc.status_code in {403, 409}:
                    row.state, row.encrypted_credentials, account.generation = (
                        "reauthorization_required",
                        "",
                        uid(),
                    )
                    session.execute(
                        delete(GoogleMeetPreview).where(GoogleMeetPreview.connection_id == row.id)
                    )
                    session.commit()
                raise
        self.bind(session, principal, row)
        result = row.id, account.generation, credentials["access_token"]
        session.commit()
        return result

    def disconnect(self, session: Session, principal: Principal) -> dict:
        require_private_account(session, principal)
        if not principal.session_hash:
            fail("Disconnect your own Google consent from a browser", 403)
        session.scalar(
            select(User)
            .where(User.id == principal.user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        require_private_account(session, principal)
        row = session.scalar(
            connection_query(principal).with_for_update().execution_options(populate_existing=True)
        )
        if row:
            row.state, row.encrypted_credentials, row.scopes, row.expires_at, row.updated_at = (
                "reauthorization_required",
                "",
                [],
                None,
                now(),
            )
            account = session.get(GoogleMeetAccount, row.id)
            if account:
                account.generation = uid()
            session.execute(delete(GoogleMeetPreview).where(GoogleMeetPreview.connection_id == row.id))
            session.execute(delete(ProviderDestination).where(ProviderDestination.connection_id == row.id))
        session.execute(
            delete(IntegrationOAuthState).where(
                IntegrationOAuthState.user_id == principal.user_id,
                IntegrationOAuthState.provider == "google_meet",
            )
        )
        return {"ok": True, "state": "disconnected", "remote_consent_revoked": False}

    async def pages(self, path: str, key: str, token: str, maximum: int) -> list[dict]:
        rows, seen, cursor = [], set(), None
        for _ in range(50):
            payload = await self.request(
                "GET",
                API + path,
                token=token,
                params={"pageSize": 100, **({"pageToken": cursor} if cursor else {})},
            )
            page = payload.get(key, [])
            if not isinstance(page, list) or any(not isinstance(row, dict) for row in page):
                fail("Google returned malformed transcript data")
            rows.extend(page)
            if len(rows) > maximum:
                fail("Meeting exceeds the safe import limit; no partial transcript was imported", 413)
            cursor = payload.get("nextPageToken")
            if not cursor:
                return rows
            if not isinstance(cursor, str) or len(cursor) > 4000 or cursor in seen:
                fail("Google returned an invalid pagination cursor")
            seen.add(cursor)
        fail("Meeting requires too many read pages; no partial transcript was imported", 413)

    async def fetch_latest(self, token: str) -> tuple[str, dict, list]:
        try:
            async with asyncio.timeout(20):
                return await self._fetch_latest(token)
        except TimeoutError as exc:
            raise ServiceError(
                status_code=504,
                error="Google import timed out; no partial transcript was imported",
                where="google_meet",
            ) from exc

    async def _fetch_latest(self, token: str) -> tuple[str, dict, list]:
        payload = await self.request("GET", API + "conferenceRecords", token=token, params={"pageSize": 1})
        records = payload.get("conferenceRecords", [])
        if not isinstance(records, list) or len(records) > 1:
            fail("Google returned an invalid latest meeting")
        if not records:
            fail("No accessible recent Google Meet meeting was found", 404)
        record = records[0]
        if (
            not isinstance(record, dict)
            or not isinstance(record.get("name"), str)
            or not re.fullmatch("conferenceRecords/" + RESOURCE, record.get("name", ""))
        ):
            fail("Google returned an invalid conference resource")
        name = record["name"]
        start = timestamp(record.get("startTime"))
        if not record.get("endTime"):
            fail("Your latest accessible meeting is still active; try again after it ends", 409)
        end = timestamp(record["endTime"])
        if end < start:
            fail("Google returned invalid meeting timestamps")
        transcripts = await self.pages(name + "/transcripts", "transcripts", token, 50)
        if not transcripts:
            fail("Your latest meeting has no transcript; transcription must already have been enabled", 404)
        names, entries = [], []
        for transcript in transcripts:
            resource = transcript.get("name", "")
            if (
                not isinstance(resource, str)
                or not re.fullmatch(re.escape(name) + "/transcripts/" + RESOURCE, resource)
                or resource in names
            ):
                fail("Google returned invalid transcript sessions")
            if transcript.get("state") != "FILE_GENERATED":
                fail("Your latest meeting transcript is still processing; try again later", 409)
            names.append(resource)
            entries.extend(await self.pages(resource + "/entries", "transcriptEntries", token, 5000))
            if len(entries) > 5000:
                fail("Meeting exceeds the safe entry limit", 413)
        if not entries:
            fail("The latest transcript has no available speech entries", 404)
        people = await self.pages(name + "/participants", "participants", token, 500)
        labels, participants = {}, []
        for person in people:
            resource = person.get("name", "")
            if (
                not isinstance(resource, str)
                or not re.fullmatch(re.escape(name) + "/participants/" + RESOURCE, resource)
                or resource in labels
            ):
                fail("Google returned invalid participant resources")
            identity = (
                person.get("signedinUser") or person.get("anonymousUser") or person.get("phoneUser") or {}
            )
            display = (
                identity.get("displayName", "Participant") if isinstance(identity, dict) else "Participant"
            )
            if not isinstance(display, str):
                fail("Google returned an invalid participant label")
            safe = re.sub(r"[\r\n:\[\]\x00-\x1f]", " ", display).strip()[:85] or "Participant"
            label = safe + " (" + hashlib.sha256(resource.encode()).hexdigest()[:8] + ")"
            labels[resource] = label
            participants.append({"resource": resource, "name": label, "confirmed": False})
        normalized, seen = [], set()
        for entry in entries:
            resource, person = entry.get("name", ""), entry.get("participant", "")
            if (
                not isinstance(resource, str)
                or not any(
                    re.fullmatch(re.escape(parent) + "/entries/" + RESOURCE, resource) for parent in names
                )
                or resource in seen
                or not isinstance(person, str)
                or person not in labels
            ):
                fail("Google returned inconsistent speech entry provenance")
            seen.add(resource)
            spoken, finished = timestamp(entry.get("startTime")), timestamp(entry.get("endTime"))
            text = entry.get("text")
            if (
                spoken < start
                or finished < spoken
                or finished > end
                or not isinstance(text, str)
                or not text.strip()
                or "\x00" in text
            ):
                fail("Google returned invalid speech text or timestamps")
            normalized.append((spoken, resource, labels[person], text))
        normalized.sort(key=lambda row: (row[0], row[1]))
        lines = []
        for spoken, _resource, label, text in normalized:
            seconds = int((spoken - start).total_seconds())
            lines.append(
                f"[{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}] {label}: {text}"
            )
        raw_text = "\n".join(lines)
        if len(raw_text.encode()) > settings.max_upload_bytes:
            fail("Transcript exceeds the upload limit; no text was truncated", 413)
        from .chunking import to_chunk_records

        if len(to_chunk_records(raw_text)) > settings.max_chunks:
            fail("Transcript exceeds the chunk limit; no text was truncated", 413)
        return (
            raw_text,
            {
                "provider": "google_meet",
                "format": "meet_api_entries",
                "conference_record": name,
                "start_time": start.isoformat(),
                "end_time": end.isoformat(),
                "transcript_names": sorted(names),
                "latest_order": "start_time_desc",
            },
            participants,
        )


def timestamp(value) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else None
        if parsed is None or parsed.tzinfo is None:
            raise ValueError("Missing timestamp")
        return parsed.astimezone(UTC)
    except (ValueError, OverflowError) as exc:
        raise ServiceError(
            status_code=502, error="Google returned an invalid timestamp", where="google_meet"
        ) from exc
