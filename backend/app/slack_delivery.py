"""Bounded Slack message reads and writes; ambiguous effects are never replayed."""

import re

import httpx

from .services.common import fingerprint
from .services.errors import ServiceError
from .slack import BASE, SlackAdapter

TS = r"^[0-9]{10,20}\.[0-9]{6}$"


class UncertainSlackWrite(Exception):
    """Slack did not provide enough evidence to establish the write result."""


def content_hash(message):
    return fingerprint({"text": message.get("text", ""), "blocks": message.get("blocks", [])})


def marker(payload):
    try:
        return payload["blocks"][-1]["elements"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ServiceError(
            status_code=409, error="Slack preview marker is unavailable", where="client"
        ) from exc


def plain(value):
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def message_payload(channel_id, records, reference):
    texts = []
    blocks = []
    for record in records:
        text = record["title"] + "\n" + record["body"] + "\nOutcome: " + record["kind"]
        if record.get("due_date"):
            text += "\nReviewed due date: " + record["due_date"]
        elif record.get("due_hint"):
            text += "\nUnconfirmed date: " + record["due_hint"]
        for evidence in record.get("evidence", []):
            text += f"\nSource line {evidence['start_line']}: {evidence['text']}"
        if not 1 <= len(text) <= 3000:
            raise ServiceError(
                status_code=422,
                error="Shorten the reviewed Slack outcome or omit evidence; section limit is 3000 characters",
                where="client",
            )
        texts.append(text)
        blocks.append(
            {
                "type": "section",
                "block_id": reference + ":" + record["id"],
                "text": {"type": "plain_text", "text": text, "emoji": False},
            }
        )
    footer = "M2O receipt: " + reference
    blocks.append({"type": "context", "elements": [{"type": "plain_text", "text": footer, "emoji": False}]})
    fallback = "\n\n".join(texts) + "\n\n" + footer
    if len(fallback) > 4000 or len(blocks) > 50:
        raise ServiceError(
            status_code=422,
            error="Select fewer or shorter outcomes; Slack handoff exceeds the message limit",
            where="client",
        )
    return {
        "channel": channel_id,
        "text": plain(fallback),
        "blocks": blocks,
        "unfurl_links": False,
        "unfurl_media": False,
        "parse": "none",
    }


class SlackDeliveryAdapter(SlackAdapter):
    async def message(self, token, destination, message_ts):
        if not re.fullmatch(TS, message_ts):
            raise ServiceError(status_code=422, error="Enter a valid Slack message timestamp", where="client")
        raw = await self.request(
            "GET",
            "conversations.history",
            token=token,
            params={
                "channel": destination["channel_id"],
                "oldest": message_ts,
                "latest": message_ts,
                "inclusive": "true",
                "limit": 1,
            },
        )
        rows = raw.get("messages")
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
            raise ServiceError(status_code=409, error="The exact Slack message is unavailable", where="slack")
        message = rows[0]
        if (
            message.get("ts") != message_ts
            or message.get("bot_id") != destination["bot_id"]
            or message.get("user") != destination["bot_user_id"]
            or (message.get("app_id") and message["app_id"] != destination["app_id"])
        ):
            raise ServiceError(
                status_code=409, error="Slack message does not belong to this M2O installation", where="slack"
            )
        if not isinstance(message.get("text"), str) or not isinstance(message.get("blocks"), list):
            raise ServiceError(status_code=502, error="Slack returned invalid message content", where="slack")
        return message

    async def write(self, token, destination, action, payload, message_ts=None):
        endpoint = "chat.postMessage" if action == "create" else "chat.update"
        body = (
            payload
            if action == "create"
            else {key: value for key, value in payload.items() if key not in {"unfurl_links", "unfurl_media"}}
        )
        if action == "update":
            body = {**body, "ts": message_ts}
        try:
            async with httpx.AsyncClient(
                timeout=15, transport=self.transport, trust_env=False, follow_redirects=False
            ) as client:
                response = await client.post(
                    BASE + endpoint, json=body, headers={"Authorization": "Bearer " + token}
                )
            if response.status_code == 429:
                raise ServiceError(
                    status_code=429,
                    error="Slack rejected the write due to rate limiting; retry after waiting",
                    where="slack",
                )
            if response.status_code != 200 or len(response.content) > 1_000_000:
                raise UncertainSlackWrite()
            result = response.json()
            if not isinstance(result, dict):
                raise UncertainSlackWrite()
            if result.get("ok") is not True:
                if result.get("error") in {
                    "invalid_auth",
                    "token_revoked",
                    "account_inactive",
                    "missing_scope",
                    "not_in_channel",
                    "channel_not_found",
                    "is_archived",
                    "cant_update_message",
                    "invalid_blocks",
                    "invalid_arguments",
                    "msg_too_long",
                    "msg_blocks_too_long",
                    "no_permission",
                    "restricted_action",
                    "rate_limited",
                    "ratelimited",
                }:
                    raise ServiceError(
                        status_code=422,
                        error="Slack rejected the write; check channel, scope and message requirements",
                        where="slack",
                    )
                raise UncertainSlackWrite()
            ts = result.get("ts")
            if (
                result.get("channel") != destination["channel_id"]
                or not isinstance(ts, str)
                or not re.fullmatch(TS, ts)
                or (message_ts and ts != message_ts)
            ):
                raise UncertainSlackWrite()
            return {
                "status": "created" if action == "create" else "updated",
                "channel_id": destination["channel_id"],
                "message_ts": ts,
            }
        except (httpx.HTTPError, ValueError) as exc:
            raise UncertainSlackWrite() from exc

    async def verify(self, token, proposal, message_ts):
        message = await self.message(token, proposal.destination, message_ts)
        if marker(message) != marker(proposal.payload):
            raise ServiceError(
                status_code=409,
                error="Slack receipt marker does not match the reviewed delivery",
                where="slack",
            )
        if (
            message.get("blocks") != proposal.payload["blocks"]
            or message.get("text") != proposal.payload["text"]
        ):
            raise ServiceError(
                status_code=409, error="Slack content differs from the exact reviewed message", where="slack"
            )
        return {
            "status": "existing",
            "channel_id": proposal.destination["channel_id"],
            "message_ts": message_ts,
        }
