"""Run the configured MCP adapter against a synthetic transcript in its scoped workspace."""

import asyncio

from app import mcp_server


async def run_demo():
    result = mcp_server.index_meeting(
        "configured-mcp-demo",
        "Alex: Action: Review the synthetic launch checklist.",
        "Synthetic MCP demonstration",
    )
    from app.worker import run_once

    # Only the separately running worker normally executes jobs. This CLI drains
    # one local job at a time for a deterministic, operator-invoked demonstration.
    for _ in range(20):
        status = mcp_server.get_job(result["job_id"])
        if status["state"] in {"completed", "failed", "cancelled"}:
            break
        await run_once()
    queued = mcp_server.extract_meeting_tasks("configured-mcp-demo")
    for _ in range(20):
        status = mcp_server.get_job(queued["job_id"])
        if status["state"] in {"completed", "failed", "cancelled"}:
            break
        await run_once()
    meeting = mcp_server.get_meeting("configured-mcp-demo")
    return {
        "meeting_id": meeting["id"],
        "outcomes": len(meeting["tasks"]),
        "job_state": status["state"],
        "external_writes": 0,
    }


if __name__ == "__main__":
    import json

    print(json.dumps(asyncio.run(run_demo()), indent=2))
