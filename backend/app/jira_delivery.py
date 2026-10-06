"""Bounded Jira metadata discovery and explicit, non-retried issue writes."""

import re
from datetime import date

import httpx

from .jira import JiraAdapter
from .services.errors import ServiceError


class UncertainJiraWrite(Exception):
    """The provider may have accepted a write; absence of a reply is not rejection."""


def document(text: str) -> dict:
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": line}] if line else []}
            for line in text.split("\n")
        ],
    }


def field_contract(raw: dict) -> dict:
    key = raw.get("fieldId", raw.get("key"))
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", key):
        raise ServiceError(status_code=502, error="Jira returned an invalid field identifier", where="jira")
    schema = raw.get("schema", {})
    schema = schema if isinstance(schema, dict) else {}
    options = raw.get("allowedValues", [])
    if not isinstance(options, list) or len(options) > 1000:
        raise ServiceError(
            status_code=502, error="Jira field options exceed the supported limit", where="jira"
        )
    choices = []
    for option in options:
        if isinstance(option, dict) and isinstance(option.get("id"), str):
            choices.append(
                {"id": option["id"], "name": str(option.get("name", option.get("value", option["id"])))[:200]}
            )
    kind = schema.get("type")
    operations = raw.get("operations", [])
    if (
        (kind is not None and not isinstance(kind, str))
        or not isinstance(operations, list)
        or not all(isinstance(value, str) for value in operations)
    ):
        raise ServiceError(status_code=502, error="Jira returned an invalid field contract", where="jira")
    control = "unsupported"
    # Only field contracts we can encode faithfully are accepted. User/parent,
    # cascading options and plugin-specific structures require dedicated mappings.
    if (
        key not in {"project", "issuetype", "parent", "assignee", "reporter", "status"}
        and "set" in operations
    ):
        if kind == "string" and not options:
            control = (
                "textarea"
                if key in {"description", "environment"}
                or str(schema.get("custom", "")).endswith(":textarea")
                else "text"
            )
        elif kind in {"number", "integer", "date"}:
            control = kind
        elif (
            kind in {"option", "priority", "resolution"}
            and choices
            and len(choices) == len(options)
            and not any("children" in o for o in options)
        ):
            control = "select"
        elif kind == "array" and schema.get("items") == "string" and not options:
            control = "strings"
    return {
        "id": key,
        "name": str(raw.get("name", key))[:200],
        "required": raw.get("required") is True,
        "has_default": raw.get("hasDefaultValue") is True,
        "control": control,
        "options": choices,
    }


def encode_fields(metadata: list[dict], values: dict) -> dict:
    available = {field["id"]: field for field in metadata}
    encoded = {}
    for key, value in values.items():
        field = available.get(key)
        if not field or field["control"] == "unsupported":
            raise ServiceError(
                status_code=422,
                error=f"Field {key[:80]} is not supported on this Jira screen",
                where="client",
            )
        control = field["control"]
        valid = False
        if control in {"text", "textarea", "date", "select"}:
            valid = isinstance(value, str) and 0 < len(value) <= 16000
            if control == "date" and valid:
                try:
                    valid = date.fromisoformat(value).isoformat() == value
                except ValueError:
                    valid = False
            if control == "select":
                valid = valid and value in {o["id"] for o in field["options"]}
            encoded[key] = (
                document(value)
                if control == "textarea" and valid
                else {"id": value}
                if control == "select"
                else value
            )
        elif control in {"number", "integer"}:
            valid = type(value) in {int, float} and abs(value) <= 1e12
            if control == "integer":
                valid = type(value) is int
            encoded[key] = value
        elif control == "strings":
            valid = (
                isinstance(value, list)
                and len(value) <= 100
                and all(
                    isinstance(v, str) and 0 < len(v) <= 255 and not any(c.isspace() for c in v)
                    for v in value
                )
            )
            encoded[key] = value
        if not valid:
            raise ServiceError(
                status_code=422, error=f"Check the value for Jira field {field['name']}", where="client"
            )
    for field in metadata:
        if (
            field["id"] not in {"project", "issuetype"}
            and field["required"]
            and not field["has_default"]
            and field["id"] not in encoded
        ):
            raise ServiceError(
                status_code=422,
                error=f"Jira requires {field['name']}; supply a supported value or choose another issue type",
                where="client",
            )
    return encoded


class JiraDeliveryAdapter(JiraAdapter):
    @staticmethod
    def base(destination: dict) -> str:
        return f"https://api.atlassian.com/ex/jira/{destination['resource_id']}/rest/api/3"

    async def pages(self, token: str, url: str, collection: str) -> list[dict]:
        records = []
        start = 0
        for _ in range(20):
            page = await self.request("GET", f"{url}?startAt={start}&maxResults=50", token=token)
            if not isinstance(page, dict):
                break
            rows = page.get(collection, page.get("values"))
            if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
                break
            records.extend(rows)
            if len(records) > 1000:
                break
            start += len(rows)
            total = page.get("total")
            if page.get("isLast") is True or (type(total) is int and start >= total):
                return records
            if not rows or (total is None and len(rows) < 50):
                return records
        raise ServiceError(
            status_code=502,
            error="Jira metadata could not be fully discovered within supported limits",
            where="jira",
        )

    async def types(self, token: str, destination: dict) -> list[dict]:
        rows = await self.pages(
            token,
            self.base(destination) + f"/issue/createmeta/{destination['project_key']}/issuetypes",
            "issueTypes",
        )
        result = []
        for row in rows:
            if row.get("subtask") is True:
                continue
            if (
                not isinstance(row.get("id"), str)
                or not re.fullmatch(r"[0-9]{1,20}", row["id"])
                or not isinstance(row.get("name"), str)
            ):
                raise ServiceError(status_code=502, error="Jira returned invalid issue types", where="jira")
            result.append({"id": row["id"], "name": row["name"][:200]})
        return result

    async def fields(
        self, token: str, destination: dict, issue_type_id: str, issue_key: str | None = None
    ) -> list[dict]:
        if issue_key:
            response = await self.request(
                "GET", self.base(destination) + f"/issue/{issue_key}/editmeta", token=token
            )
            fields = response.get("fields") if isinstance(response, dict) else None
            if (
                not isinstance(fields, dict)
                or len(fields) > 1000
                or not all(isinstance(v, dict) for v in fields.values())
            ):
                raise ServiceError(status_code=502, error="Jira returned invalid edit metadata", where="jira")
            rows = [{**value, "fieldId": key} for key, value in fields.items()]
        else:
            if issue_type_id not in {t["id"] for t in await self.types(token, destination)}:
                raise ServiceError(
                    status_code=422, error="Choose an available Jira issue type", where="client"
                )
            rows = await self.pages(
                token,
                self.base(destination)
                + f"/issue/createmeta/{destination['project_key']}/issuetypes/{issue_type_id}",
                "fields",
            )
        normalized = [field_contract(row) for row in rows]
        if len({field["id"] for field in normalized}) != len(normalized):
            raise ServiceError(
                status_code=502, error="Jira returned duplicate field definitions", where="jira"
            )
        return normalized

    async def issue(self, token: str, destination: dict, key: str) -> dict:
        issue = await self.request(
            "GET",
            self.base(destination) + f"/issue/{key}?fields=project,issuetype,updated,summary,status",
            token=token,
        )
        fields = issue.get("fields") if isinstance(issue, dict) else None
        project = fields.get("project") if isinstance(fields, dict) else None
        issue_type = fields.get("issuetype") if isinstance(fields, dict) else None
        if (
            not isinstance(fields, dict)
            or issue.get("key") != key
            or not isinstance(project, dict)
            or project.get("key") != destination["project_key"]
            or not isinstance(issue_type, dict)
            or not isinstance(issue_type.get("id"), str)
            or not re.fullmatch(r"[0-9]{1,20}", issue_type["id"])
            or not isinstance(fields.get("updated"), str)
            or not 1 <= len(fields["updated"]) <= 100
            or not isinstance(fields.get("summary"), str)
            or len(fields["summary"]) > 255
        ):
            raise ServiceError(
                status_code=409,
                error="The Jira issue does not belong to the selected project or cannot be verified",
                where="jira",
            )
        return {
            "key": key,
            "fields": {
                "project": {"key": project["key"]},
                "issuetype": {"id": issue_type["id"]},
                "updated": fields["updated"],
                "summary": fields["summary"],
            },
        }

    async def write(
        self, token: str, destination: dict, action: str, payload: dict, issue_key: str | None
    ) -> dict:
        method = "POST" if action == "create" else "PUT"
        path = "/issue" if action == "create" else f"/issue/{issue_key}"
        try:
            async with httpx.AsyncClient(
                timeout=15, trust_env=False, follow_redirects=False, transport=self.transport
            ) as client:
                response = await client.request(
                    method,
                    self.base(destination) + path,
                    json=payload,
                    headers={"Authorization": "Bearer " + token},
                )
            if response.status_code in {400, 401, 403, 404, 409, 422, 429}:
                raise ServiceError(
                    status_code=422,
                    error="Jira rejected the reviewed request; check permissions and current fields",
                    where="jira",
                )
            if action == "update" and response.status_code == 204:
                key = issue_key
            elif action == "create" and response.status_code == 201 and len(response.content) <= 10000:
                key = response.json().get("key")
            else:
                raise UncertainJiraWrite()
            if not isinstance(key, str) or not re.fullmatch(
                re.escape(destination["project_key"]) + r"-[1-9][0-9]{0,19}", key
            ):
                raise UncertainJiraWrite()
            return {
                "status": "created" if action == "create" else "updated",
                "issue_key": key,
                "url": destination["resource_url"] + "/browse/" + key,
            }
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            raise UncertainJiraWrite() from exc

    async def verify_receipt(self, token: str, destination: dict, key: str, marker: str) -> dict:
        await self.issue(token, destination, key)
        result = await self.request(
            "GET", self.base(destination) + f"/issue/{key}/properties/m2o.delivery", token=token
        )
        if not isinstance(result, dict) or result.get("value") != {"marker": marker}:
            raise ServiceError(
                status_code=409,
                error="This Jira issue does not confirm the recorded delivery; no resend is permitted",
                where="jira",
            )
        return {
            "status": "reconciled",
            "issue_key": key,
            "url": destination["resource_url"] + "/browse/" + key,
        }
