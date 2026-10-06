import asyncio
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from sqlalchemy import text

from app.worker import run_once


def test_complete_mcp_workflow_over_stdio(engine, seeded):
    env = dict(
        os.environ,
        DATABASE_URL=engine.url.render_as_string(hide_password=False),
        APP_ENVIRONMENT="test",
        MCP_API_TOKEN=seeded["token"],
        PUBLIC_DEMO_MODE="true",
        GITHUB_TOKEN="",
        OLLAMA_MODEL="",
        EMBED_PROVIDER="hash",
    )
    if engine.dialect.name == "postgresql":
        with engine.connect() as connection:
            schema = connection.execute(text("SHOW search_path")).scalar()
        env["PGOPTIONS"] = "-csearch_path=" + schema
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.mcp_server"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
    )

    async def journey():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client:
                init = await client.initialize()
                assert init.server_info.name == "meeting-to-tasks"
                assert init.server_info.version == "1.0.0"
                result = await client.call_tool(
                    "index_meeting",
                    {
                        "meeting_id": "stdio-demo",
                        "transcript": "Action: Alex to validate protocol boundaries.",
                    },
                )
                assert not result.is_error
                assert result.structured_content["job_id"]
                assert await run_once()
                result = await client.call_tool(
                    "search_meeting", {"meeting_id": "stdio-demo", "query": "protocol boundaries", "k": 1}
                )
                assert not result.is_error and result.structured_content["results"]
                result = await client.call_tool("extract_meeting_tasks", {"meeting_id": "stdio-demo"})
                assert not result.is_error
                assert await run_once()
                details = (
                    await client.call_tool("get_meeting", {"meeting_id": "stdio-demo"})
                ).structured_content
                item = details["tasks"][0]
                reviewed = await client.call_tool(
                    "review_outcome",
                    {
                        "meeting_id": "stdio-demo",
                        "item_id": item["id"],
                        "expected_version": 1,
                        "changes": {"status": "approved"},
                    },
                )
                assert not reviewed.is_error
                proposal = (
                    await client.call_tool(
                        "preview_github_issues",
                        {"repo": "synthetic/demo", "meeting_id": "stdio-demo", "task_ids": [item["id"]]},
                    )
                ).structured_content
                assert "meeting-to-tasks:" in proposal["would_create"][0]["body"]
                blocked = await client.call_tool(
                    "create_github_issues",
                    {"proposal_id": proposal["id"], "payload_hash": proposal["payload_hash"]},
                )
                assert blocked.is_error

    asyncio.run(journey())
