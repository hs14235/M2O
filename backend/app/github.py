"""GitHub writes use immutable payloads; an ambiguous response is never retried."""

import asyncio
from urllib.parse import urlsplit

import httpx

from .services.errors import ServiceError
from .settings import settings

BASE = "https://api.github.com"
MAX_SCAN_PAGES = 100
MAX_SCAN_SECONDS = 30


class AmbiguousWrite(Exception):
    pass


class GitHubAdapter:
    def __init__(self, transport=None):
        self.transport = transport

    def client(self):
        token = settings.github_token.get_secret_value()
        if not token:
            raise ServiceError(status_code=503, error="GitHub credentials are not configured")
        return httpx.AsyncClient(
            base_url=BASE,
            timeout=15,
            trust_env=False,
            transport=self.transport,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    @staticmethod
    def check(response):
        if response.status_code >= 400:
            limited = response.status_code == 429 or (
                response.status_code == 403
                and (
                    response.headers.get("X-RateLimit-Remaining") == "0" or "Retry-After" in response.headers
                )
            )
            code = (
                "GitHub rate limit reached"
                if limited
                else "GitHub permission was denied"
                if response.status_code == 403
                else "GitHub rejected the request"
            )
            raise ServiceError(status_code=502, error=code, where="github")

    async def find_marker(self, repo: str, marker: str, expected_payload: dict | None = None):
        try:
            async with asyncio.timeout(MAX_SCAN_SECONDS):
                return await self._scan_marker(repo, marker, expected_payload)
        except TimeoutError as exc:
            raise ServiceError(
                status_code=409,
                error="GitHub reconciliation exceeded its time budget; no write attempted",
                where="github",
            ) from exc

    async def _scan_marker(self, repo: str, marker: str, expected_payload: dict | None = None):
        found = None
        async with self.client() as client:
            # Includes closed issues and avoids relying on search indexing latency.
            for page in range(1, MAX_SCAN_PAGES + 1):
                response = await client.get(
                    f"/repos/{repo}/issues", params={"state": "all", "per_page": 100, "page": page}
                )
                self.check(response)
                if response.status_code != 200:
                    raise ServiceError(status_code=502, error="Invalid GitHub response", where="github")
                try:
                    rows = response.json()
                except ValueError as exc:
                    raise ServiceError(
                        status_code=502, error="Invalid GitHub response", where="github"
                    ) from exc
                if (
                    not isinstance(rows, list)
                    or len(rows) > 100
                    or any(
                        not isinstance(row, dict)
                        or (row.get("body") is not None and not isinstance(row["body"], str))
                        for row in rows
                    )
                ):
                    raise ServiceError(status_code=502, error="Invalid GitHub response", where="github")
                matches = [
                    row for row in rows if "pull_request" not in row and marker in (row.get("body") or "")
                ]
                if len(matches) > 1 or (matches and found is not None):
                    raise ServiceError(
                        status_code=409,
                        error="Multiple matching issues require manual reconciliation",
                        where="github",
                    )
                if matches:
                    try:
                        found = self.record(matches[0], "existing", repo)
                        if expected_payload is not None and not self.matches_payload(
                            matches[0], expected_payload
                        ):
                            found = {
                                **found,
                                "status": "conflict",
                                "provider_effect": "existing",
                                "error": "Existing issue content differs from the approved payload; inspect it before proceeding",
                            }
                    except AmbiguousWrite as exc:
                        raise ServiceError(
                            status_code=502, error="Invalid GitHub issue receipt", where="github"
                        ) from exc
                if len(rows) < 100:
                    return found
        raise ServiceError(
            status_code=409, error="Repository exceeds the reconciliation scan limit", where="github"
        )

    @staticmethod
    def matches_payload(value: dict, expected: dict) -> bool:
        if value.get("title") != expected.get("title") or value.get("body") != expected.get("body"):
            return False
        for field, key in (("labels", "name"), ("assignees", "login")):
            observed, requested = value.get(field), expected.get(field, [])
            if (
                not isinstance(observed, list)
                or not isinstance(requested, list)
                or any(not isinstance(name, str) for name in requested)
                or any(not isinstance(row, dict) or not isinstance(row.get(key), str) for row in observed)
            ):
                return False
            if {row[key].casefold() for row in observed} != {name.casefold() for name in requested}:
                return False
        return True

    @staticmethod
    def record(value, status="created", repo: str | None = None):
        if not isinstance(value, dict):
            raise AmbiguousWrite("Issue response could not be verified")
        number, url = value.get("number"), value.get("html_url")
        if type(number) is not int or number <= 0 or not isinstance(url, str):
            raise AmbiguousWrite("Issue response could not be verified")
        try:
            parsed = urlsplit(url)
            parts = parsed.path.split("/")
            valid = (
                parsed.scheme == "https"
                and parsed.netloc.casefold() == "github.com"
                and not parsed.query
                and not parsed.fragment
                and len(parts) == 5
                and bool(parts[1])
                and bool(parts[2])
                and parts[3] == "issues"
                and parts[4] == str(number)
                and (repo is None or "/".join(parts[1:3]).casefold() == repo.casefold())
            )
        except ValueError as exc:
            raise AmbiguousWrite("Issue response could not be verified") from exc
        if not valid:
            raise AmbiguousWrite("Issue response could not be verified")
        return {"status": status, "number": number, "url": url}

    async def create(self, repo: str, payload: dict):
        try:
            async with self.client() as client:
                response = await client.post(f"/repos/{repo}/issues", json=payload)
                if response.status_code >= 500:
                    raise AmbiguousWrite("GitHub did not confirm the write")
                self.check(response)
                if response.status_code != 201:
                    raise AmbiguousWrite("GitHub did not confirm the write")
                value = response.json()
                receipt = self.record(value, repo=repo)
                if not self.matches_payload(value, payload):
                    return {
                        **receipt,
                        "status": "conflict",
                        "provider_effect": "created",
                        "error": "GitHub created an issue whose content differs from the approved payload; inspect it before proceeding",
                    }
                return receipt
        except (httpx.TransportError, ValueError) as exc:
            raise AmbiguousWrite("GitHub did not confirm the write") from exc
