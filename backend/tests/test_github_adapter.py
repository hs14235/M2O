import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr

import app.github as github
from app.github import AmbiguousWrite, GitHubAdapter
from app.services.errors import ServiceError
from app.settings import settings

REPO = "synthetic/demo"
MARKER = "<!-- synthetic-delivery-marker -->"


@pytest.fixture(autouse=True)
def synthetic_credentials(monkeypatch):
    monkeypatch.setattr(settings, "github_token", SecretStr("synthetic-provider-token"))


def issue(number=12, body=MARKER):
    return {"number": number, "html_url": f"https://github.com/{REPO}/issues/{number}", "body": body}


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {"number": True, "html_url": "https://github.com/synthetic/demo/issues/True"},
        {"number": 0, "html_url": "https://github.com/synthetic/demo/issues/0"},
        {"number": -1, "html_url": "https://github.com/synthetic/demo/issues/-1"},
        {"number": 12, "html_url": "https://github.com/other/repo/issues/12"},
        {"number": 12, "html_url": "https://github.com/synthetic/demo/issues/13"},
        {"number": 12, "html_url": "https://github.com/synthetic/demo/pull/12"},
        {"number": 12, "html_url": "https://github.com.evil.test/synthetic/demo/issues/12"},
        {"number": 12, "html_url": "https://user@github.com/synthetic/demo/issues/12"},
        {"number": 12, "html_url": "https://github.com:443/synthetic/demo/issues/12"},
        {"number": 12, "html_url": "https://github.com/synthetic/demo/issues/12?redirect=1"},
        {"number": 12, "html_url": "https://github.com/synthetic/demo/issues/12#fragment"},
        {"number": 12, "html_url": "http://github.com/synthetic/demo/issues/12"},
    ],
)
def test_receipt_must_match_requested_repository_and_positive_issue_number(value):
    with pytest.raises(AmbiguousWrite):
        GitHubAdapter.record(value, repo=REPO)


def test_exact_create_request_and_receipt():
    payload = {"title": "Synthetic reviewed task", "body": MARKER, "labels": ["meeting-action"]}
    requests = []

    def respond(request):
        requests.append(request)
        assert request.method == "POST"
        assert request.url == f"https://api.github.com/repos/{REPO}/issues"
        assert json.loads(request.content) == payload
        assert request.headers["X-GitHub-Api-Version"] == "2022-11-28"
        return httpx.Response(
            201,
            json={
                **issue(),
                "title": payload["title"],
                "labels": [{"name": "meeting-action"}],
                "assignees": [],
            },
        )

    result = asyncio.run(GitHubAdapter(httpx.MockTransport(respond)).create(REPO, payload))
    assert result == {"status": "created", "number": 12, "url": issue()["html_url"]}
    assert len(requests) == 1


@pytest.mark.parametrize("changed", ["title", "body", "labels", "assignees"])
def test_created_issue_with_silently_dropped_or_changed_fields_records_existing_resource(changed):
    payload = {"title": "Reviewed title", "body": MARKER, "labels": ["Meeting"], "assignees": ["Owner"]}
    value = {
        **issue(),
        "title": payload["title"],
        "labels": [{"name": "meeting"}],
        "assignees": [{"login": "owner"}],
    }
    value[changed] = [] if changed in {"labels", "assignees"} else "different returned content"
    calls = []

    def respond(request):
        calls.append(request.method)
        return httpx.Response(201, json=value)

    result = asyncio.run(GitHubAdapter(httpx.MockTransport(respond)).create(REPO, payload))
    assert result["status"] == "conflict" and result["provider_effect"] == "created"
    assert result["number"] == 12 and result["url"] == issue()["html_url"]
    assert calls == ["POST"]


@pytest.mark.parametrize("change", [None, "title", "body", "labels", "assignees", "missing_fields"])
def test_marker_receipt_checks_exact_approved_content_without_overwrite(change):
    expected = {"title": "Approved title", "body": MARKER, "labels": ["Meeting"], "assignees": ["Owner"]}
    found = {
        **issue(),
        "title": expected["title"],
        "labels": [{"name": "meeting"}],
        "assignees": [{"login": "owner"}],
    }
    if change in {"title", "body"}:
        found[change] = found[change] + " externally changed"
    elif change in {"labels", "assignees"}:
        found[change] = []
    elif change == "missing_fields":
        del found["assignees"]
    calls = []

    def respond(request):
        calls.append(request.method)
        return httpx.Response(200, json=[found])

    result = asyncio.run(GitHubAdapter(httpx.MockTransport(respond)).find_marker(REPO, MARKER, expected))
    assert result["status"] == ("existing" if change is None else "conflict")
    assert result["url"] == found["html_url"] and calls == ["GET"]


@pytest.mark.parametrize("status", [200, 202, 204, 301, 302, 307, 500, 503])
def test_unconfirmed_create_response_is_uncertain_and_not_retried(status):
    calls = []

    def respond(request):
        calls.append(request.method)
        return httpx.Response(status, json=issue(), headers={"Location": "https://example.test/redirect"})

    with pytest.raises(AmbiguousWrite):
        asyncio.run(GitHubAdapter(httpx.MockTransport(respond)).create(REPO, {"title": "Synthetic"}))
    assert calls == ["POST"]


@pytest.mark.parametrize("response", [httpx.Response(201, json=[]), httpx.Response(201, text="invalid")])
def test_malformed_create_receipt_is_uncertain(response):
    with pytest.raises(AmbiguousWrite):
        asyncio.run(GitHubAdapter(httpx.MockTransport(lambda request: response)).create(REPO, {}))


@pytest.mark.parametrize(
    ("status", "headers", "message"),
    [
        (403, {}, "permission"),
        (403, {"X-RateLimit-Remaining": "15"}, "permission"),
        (403, {"X-RateLimit-Remaining": "0"}, "rate limit"),
        (403, {"Retry-After": "30"}, "rate limit"),
        (429, {}, "rate limit"),
        (422, {}, "rejected"),
    ],
)
def test_known_rejection_distinguishes_permissions_and_rate_limits(status, headers, message):
    calls = []

    def respond(request):
        calls.append(request.method)
        return httpx.Response(status, headers=headers, json={"message": "Synthetic private detail"})

    with pytest.raises(ServiceError, match=message) as captured:
        asyncio.run(GitHubAdapter(httpx.MockTransport(respond)).create(REPO, {}))
    assert "private detail" not in str(captured.value)
    assert calls == ["POST"]


def paged_scan(duplicate=False):
    calls = []

    def respond(request):
        calls.append(request.method)
        assert request.method == "GET"
        assert request.url.params["state"] == "all"
        assert request.url.params["per_page"] == "100"
        page = int(request.url.params["page"])
        if page == 1:
            return httpx.Response(200, json=[issue(), *[issue(n, "Other") for n in range(100, 199)]])
        assert page == 2
        return httpx.Response(200, json=[issue(13)] if duplicate else [issue(13, "Other")])

    return GitHubAdapter(httpx.MockTransport(respond)), calls


def test_duplicate_markers_on_different_pages_require_manual_reconciliation():
    adapter, calls = paged_scan(duplicate=True)
    with pytest.raises(ServiceError, match="Multiple matching"):
        asyncio.run(adapter.find_marker(REPO, MARKER))
    assert calls == ["GET", "GET"]


def test_unique_marker_is_returned_only_after_complete_bounded_scan():
    adapter, calls = paged_scan()
    result = asyncio.run(adapter.find_marker(REPO, MARKER))
    assert result == {"status": "existing", "number": 12, "url": issue()["html_url"]}
    assert calls == ["GET", "GET"]


def test_scan_limit_does_not_claim_unique_marker(monkeypatch):
    monkeypatch.setattr(github, "MAX_SCAN_PAGES", 1)
    adapter, calls = paged_scan()
    with pytest.raises(ServiceError, match="scan limit"):
        asyncio.run(adapter.find_marker(REPO, MARKER))
    assert calls == ["GET"]


def test_total_scan_deadline_returns_inconclusive_without_any_write(monkeypatch):
    monkeypatch.setattr(github, "MAX_SCAN_SECONDS", 0.01)
    calls = []

    async def respond(request):
        calls.append(request.method)
        await asyncio.sleep(0.1)
        return httpx.Response(200, json=[issue()])

    with pytest.raises(ServiceError, match="time budget"):
        asyncio.run(GitHubAdapter(httpx.MockTransport(respond)).find_marker(REPO, MARKER))
    assert calls == ["GET"]


@pytest.mark.parametrize(
    "rows",
    [
        [1],
        [{"body": True}],
        {"items": []},
        [issue() | {"html_url": "https://github.com/wrong/repo/issues/12"}],
    ],
)
def test_malformed_read_cannot_authorize_publication(rows):
    with pytest.raises(ServiceError, match="Invalid GitHub"):
        asyncio.run(
            GitHubAdapter(httpx.MockTransport(lambda request: httpx.Response(200, json=rows))).find_marker(
                REPO, MARKER
            )
        )


def test_pull_requests_are_not_issue_delivery_receipts():
    row = issue() | {"pull_request": {}}
    result = asyncio.run(
        GitHubAdapter(httpx.MockTransport(lambda request: httpx.Response(200, json=[row]))).find_marker(
            REPO, MARKER
        )
    )
    assert result is None
