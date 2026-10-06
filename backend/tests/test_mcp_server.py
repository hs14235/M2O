import asyncio

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import SecretStr

from app import mcp_server
from app.settings import settings
from app.worker import run_once


def test_mcp_exposes_expected_tools_and_safety_annotations():
    tools = {tool.name: tool for tool in asyncio.run(mcp_server.mcp.list_tools())}
    assert set(tools) == {
        "index_meeting",
        "search_meeting",
        "extract_meeting_tasks",
        "preview_github_issues",
        "create_github_issues",
        "get_meeting",
        "get_job",
        "review_outcome",
    }
    assert tools["search_meeting"].annotations.read_only_hint is True
    assert tools["create_github_issues"].annotations.destructive_hint is True
    assert tools["create_github_issues"].annotations.open_world_hint is True
    assert tools["extract_meeting_tasks"].annotations.read_only_hint is False
    assert tools["preview_github_issues"].annotations.read_only_hint is False


def test_mcp_requires_scoped_auth(engine, monkeypatch):
    monkeypatch.setattr(settings, "mcp_api_token", SecretStr(""))
    with pytest.raises(ToolError, match="workspace-scoped"):
        mcp_server.index_meeting("mcp", "Action: Synthetic test")


def test_mcp_masks_unexpected_failures_and_invalid_changes(engine, seeded, monkeypatch):
    monkeypatch.setattr(settings, "mcp_api_token", SecretStr(seeded["token"]))

    def fail(session, principal):
        raise RuntimeError("synthetic private database detail")

    with pytest.raises(ToolError, match="could not complete") as caught:
        mcp_server.call(fail)
    assert "private" not in str(caught.value)
    with pytest.raises(ToolError, match="failed validation"):
        mcp_server.review_outcome("mcp", "missing", 1, {"unexpected": "synthetic"})


def test_mcp_uses_same_revision_review_services(session, seeded, monkeypatch):
    monkeypatch.setattr(settings, "mcp_api_token", SecretStr(seeded["token"]))
    indexed = mcp_server.index_meeting("mcp", "Action: Alex to verify MCP contracts.")
    assert indexed["job_id"]
    assert asyncio.run(run_once())
    job = mcp_server.extract_meeting_tasks("mcp")
    assert asyncio.run(run_once())
    assert mcp_server.get_job(job["job_id"])["state"] == "completed"
    details = mcp_server.get_meeting("mcp")
    assert len(details["tasks"]) == 1
    item = details["tasks"][0]
    mcp_server.review_outcome("mcp", item["id"], 1, {"status": "approved"})
    preview = mcp_server.preview_github_issues("synthetic/demo", "mcp", [item["id"]])
    with pytest.raises(ToolError, match="Demo mode"):
        mcp_server.create_github_issues(preview["id"], preview["payload_hash"])
